"""aibl-update and unsaved lesson work (WF-6, decision 40).

The wording tests read the skill. The Git tests run the commands the skill names on throwaway repositories, to
show the changed step 1 is safe: lesson output survives a core refresh, a merge and a canceled merge untouched and
stays out of every commit, and Git itself refuses when a file really is in the way. Nothing here runs an app, so
none of this shows how a model reads the new steps.
"""
import shutil, stat, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [ROOT / d / "skills/aibl-update/SKILL.md" for d in (".claude", ".agents")]
CORE = ("aibl-personalize", "aibl-checkpoint", "aibl-enroll", "aibl-update")


def blocks_update(line):
    """Step 1's rule, as written: staged or unmerged, or a path the update itself replaces."""
    path = line[3:]
    if line[0] not in " ?":
        return True
    in_core = any(path.startswith(f"{d}/skills/{s}/") for d in (".claude", ".agents") for s in CORE)
    return in_core or path in (".claude/hooks/update-check.mjs", ".gitignore")


def git(cwd, *args, check=True):
    r = subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "core.autocrlf=false",
                        "-c", "commit.gpgsign=false", *args], cwd=cwd, text=True, capture_output=True)
    if check and r.returncode:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r


def put(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode())


class Wording(unittest.TestCase):
    def setUp(self):
        self.text = COPIES[0].read_text(encoding="utf-8")

    def line(self, start):
        return next(l for l in self.text.splitlines() if l.startswith(start))

    def test_both_app_copies_are_identical(self):
        self.assertEqual(COPIES[0].read_bytes(), COPIES[1].read_bytes())

    def test_step_1_stops_only_where_the_update_would_touch_the_work(self):
        step = self.line("1. **Check location and work.**")
        self.assertNotIn("must be empty", step)
        self.assertIn("not its stop for unsaved work, which this step replaces", step)
        self.assertIn("Save them now and continue the update? (yes / no)", step)
        self.assertIn("with no second paste", step)
        self.assertIn("Never stash, discard, or reset.", step)

    def test_the_offer_comes_after_the_refresh_and_the_privacy_lines(self):
        order = [self.text.index(s) for s in ("\n2. **Refresh core skills", "\n2.5. **Bring in the template's privacy",
                                              "\n2.6. **Offer to save the rest.**", "\n3. **Preserve settings.**")]
        self.assertEqual(order, sorted(order))
        offer = self.line("2.6. **Offer to save the rest.**")
        self.assertIn("You have unsaved lesson work. Save it now and continue the update? (yes / no)", offer)
        self.assertIn("with no second paste", offer)

    def test_an_older_copy_arriving_at_step_3_still_gets_the_offer(self):
        self.assertIn("do steps 2.5 and 2.6 first", self.line("3. **Preserve settings.**"))

    def test_the_merge_still_refuses_what_is_in_the_way(self):
        self.assertIn("git diff --name-only HEAD...<remote>/student", self.line("5. **Explain the program changes.**"))
        self.assertIn("that no unsaved file is one the program changes", self.line("6. **Approve and merge.**"))
        self.assertIn("Never merge with anything staged or over unsaved changes in a file the merge changes", self.text)
        self.assertNotIn("dirty tree", self.text)

    def test_enroll_keeps_its_own_stop(self):
        enroll = (ROOT / ".claude/skills/aibl-enroll/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("any output stops for the student to checkpoint", enroll)

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("—", self.text)
        self.assertNotIn("–", self.text)


class GitSide(unittest.TestCase):
    """A workbench with a program remote and unsaved lesson output, part way through a course."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aibl-unsaved-"))
        self.addCleanup(self.remove)
        self.program, self.template, self.wb = self.tmp / "program", self.tmp / "template", self.tmp / "wb"
        for repo in (self.program, self.template):
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
        put(self.program, "workforce/lesson.md", "lesson one\n")
        put(self.program, "work/course/staff/README.md", "notes go here\n")
        git(self.program, "add", ".")
        git(self.program, "commit", "-qm", "edition 1")
        put(self.template, ".claude/skills/aibl-update/SKILL.md", "new update skill\n")
        put(self.template, ".gitignore", (ROOT / ".gitignore").read_text(encoding="utf-8"))
        git(self.template, "add", ".")
        git(self.template, "commit", "-qm", "template")
        git(self.tmp, "clone", "-q", str(self.program), "wb")
        git(self.wb, "remote", "rename", "origin", "agent-workforce")
        git(self.wb, "remote", "add", "template", str(self.template))
        git(self.wb, "fetch", "-q", "template", "main")
        put(self.wb, ".claude/skills/aibl-update/SKILL.md", "old update skill\n")
        git(self.wb, "add", ".")
        git(self.wb, "commit", "-qm", "my workbench")
        # The unsaved work a student has mid-course.
        put(self.wb, "work/course/staff/progress.md", "lesson 8 done\n")
        put(self.wb, "runs/job-1/receipt.md", "private receipt\n")
        put(self.wb, "workforce/lesson.md", "lesson one\nmy note\n")

    def remove(self):
        def retry(fn, path, _):
            Path(path).chmod(stat.S_IWRITE)
            fn(path)
        shutil.rmtree(self.tmp, onerror=retry)

    def status(self):
        return git(self.wb, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()

    def edition(self, rel="workforce/week2.md", text="week 2\n"):
        put(self.program, rel, text)
        git(self.program, "add", ".")
        git(self.program, "commit", "-qm", "edition 2")
        git(self.wb, "fetch", "-q", "agent-workforce")

    def merge(self, check=True):
        branch = git(self.program, "branch", "--show-current").stdout.strip()
        return git(self.wb, "merge", "--no-ff", "--no-commit", f"agent-workforce/{branch}", check=check)

    def unsaved_files(self):
        return {rel: (self.wb / rel).read_bytes() for rel in
                ("work/course/staff/progress.md", "runs/job-1/receipt.md", "workforce/lesson.md")}

    def test_lesson_output_does_not_block_step_1(self):
        lines = self.status()
        self.assertEqual(len(lines), 3, lines)
        self.assertFalse(any(blocks_update(l) for l in lines), lines)

    def test_step_1_blocks_core_files_staged_files_and_an_unfinished_merge(self):
        self.assertTrue(blocks_update(" M .claude/skills/aibl-update/SKILL.md"))
        self.assertTrue(blocks_update("?? .agents/skills/aibl-enroll/SKILL.md"))
        self.assertTrue(blocks_update(" M .gitignore"))
        self.assertTrue(blocks_update("M  work/course/staff/progress.md"))
        self.assertTrue(blocks_update("UU workforce/lesson.md"))
        self.assertFalse(blocks_update(" M .claude/skills/my-own-skill/SKILL.md"))

    def test_core_refresh_and_its_commit_leave_lesson_output_alone(self):
        before = self.unsaved_files()
        git(self.wb, "checkout", "template/main", "--", ".claude/skills/aibl-update")
        git(self.wb, "commit", "-qm", "Update workbench skills from the template")
        self.assertEqual(git(self.wb, "show", "--name-only", "--format=", "HEAD").stdout.split(),
                         [".claude/skills/aibl-update/SKILL.md"])
        self.assertEqual(self.unsaved_files(), before)

    def test_the_privacy_lines_take_job_folders_out_of_the_offer(self):
        self.assertTrue(any("runs/job-1/receipt.md" in l for l in self.status()))
        put(self.wb, ".gitignore", git(self.wb, "show", "template/main:.gitignore").stdout)
        git(self.wb, "add", ".gitignore")
        git(self.wb, "commit", "-qm", "Keep private course records out of save points")
        lines = self.status()
        self.assertFalse(any("runs/" in l for l in lines), lines)
        self.assertTrue(any("work/course/staff/progress.md" in l for l in lines), lines)

    def test_a_merge_leaves_unsaved_work_out_and_untouched(self):
        before = self.unsaved_files()
        self.edition()
        self.merge()
        git(self.wb, "commit", "-qm", "edition 2")
        self.assertEqual(git(self.wb, "diff", "--name-only", "HEAD^1", "HEAD").stdout.split(), ["workforce/week2.md"])
        self.assertEqual(self.unsaved_files(), before)
        self.assertEqual(len(self.status()), 3)

    def test_a_canceled_merge_leaves_unsaved_work_untouched(self):
        before = self.unsaved_files()
        head = git(self.wb, "rev-parse", "HEAD").stdout
        self.edition()
        self.merge()
        git(self.wb, "merge", "--abort")
        self.assertEqual(git(self.wb, "rev-parse", "HEAD").stdout, head)
        self.assertEqual(self.unsaved_files(), before)
        self.assertFalse((self.wb / "workforce/week2.md").exists())

    def test_a_revert_after_the_merge_leaves_unsaved_work_untouched(self):
        before = self.unsaved_files()
        self.edition()
        self.merge()
        git(self.wb, "commit", "-qm", "edition 2")
        git(self.wb, "revert", "--no-edit", "-m", "1", "HEAD")
        self.assertEqual(self.unsaved_files(), before)
        self.assertFalse((self.wb / "workforce/week2.md").exists())

    def test_step_5_finds_a_file_the_program_changes_and_git_refuses_it(self):
        self.edition("workforce/lesson.md", "lesson one, edition 2\n")
        branch = git(self.program, "branch", "--show-current").stdout.strip()
        changed = git(self.wb, "diff", "--name-only", f"HEAD...agent-workforce/{branch}").stdout.split()
        unsaved = [l[3:] for l in self.status()]
        self.assertEqual(sorted(set(changed) & set(unsaved)), ["workforce/lesson.md"])
        before = self.unsaved_files()
        head = git(self.wb, "rev-parse", "HEAD").stdout
        self.assertNotEqual(self.merge(check=False).returncode, 0)
        self.assertEqual(git(self.wb, "rev-parse", "HEAD").stdout, head)
        self.assertEqual(self.unsaved_files(), before)

    def test_git_refuses_an_unsaved_new_file_the_program_also_adds(self):
        self.edition("work/course/staff/progress.md", "the program's file\n")
        self.assertNotEqual(self.merge(check=False).returncode, 0)
        self.assertEqual((self.wb / "work/course/staff/progress.md").read_bytes(), b"lesson 8 done\n")

    def test_git_refuses_to_merge_with_something_staged(self):
        git(self.wb, "add", "work/course/staff/progress.md")
        self.edition()
        self.assertNotEqual(self.merge(check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
