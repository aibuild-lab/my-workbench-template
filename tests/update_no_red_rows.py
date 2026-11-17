"""aibl-update runs only fixed lines that can't fail on something missing (robot R4-G, 11-16-2026).

A Cohort 1 student's update showed red failed steps from the update's own commands: in Claude Code a
`cat` and an `ls` of files that weren't there, a scratch file inside `.git`, a compare script that broke
and `git diff --no-index` against a temporary folder (each an extra box naming a temp path); in Codex a
`git cat-file -p` of a `workforce/VERSIONS.json` the edition doesn't ship, the recorder's `--check`
exiting 1 for a plain report, and a temporary-folder command typed with a typo. The skill now names a
read that never fails before each optional file, runs report scripts in their exit-0 mode, renders the
team note inside the workbench's local folder with fixed lines, and forbids improvised commands and
scratch files. Text checks; the Git checks prove the replacement reads exit 0 when the path is missing.
"""
import os, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def skill():
    a, b = [(ROOT / app / "skills" / "aibl-update" / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b
    return a


class Words(unittest.TestCase):
    def setUp(self):
        self.text = skill()
        self.rules = self.text[self.text.index("## Rules"):]

    def test_rules_forbid_improvised_commands_and_scratch_files(self):
        for phrase in ["**Run only the lines this skill gives, each as written and on its own.**",
                       "never write your own script",
                       "never make a scratch file (not inside `.git`, not in `/tmp` or another temporary folder",
                       "never run one that can fail on something missing",
                       "`git ls-tree --name-only <commit> -- <path>` for a file in a commit",
                       "`git ls-files --cached --others -- <path>` for a file on disk",
                       "Never `cat`, `ls`, `type` or `Get-Content` a path you haven't seen listed",
                       "A script that only reports runs in its report mode that exits 0",
                       "**Never show the student a temporary folder, a scratch file or a path outside the workbench**",
                       "Never compare with `git diff --no-index`, `diff`, `cmp`, `fc` or a script"]:
            self.assertIn(phrase, self.rules)

    def test_python_on_windows_starts_with_python(self):
        self.assertIn("on Windows run `python`, and `py -3` only if `python` is not found", self.rules)
        self.assertNotIn("if `python3` is not found, use `python`", self.text)

    def test_no_failing_existence_checks(self):
        self.assertNotIn("cat-file -e", self.text)
        self.assertIn("`git ls-tree --name-only <remote>/student -- workforce/VERSIONS.json .aibl/programs/<remote>.json`", self.text)
        self.assertIn("read only a listed file, with `git cat-file -p`", self.text)
        self.assertIn("`git ls-files --cached --others -- workforce/skills/aibl-agent-setup/scripts/name_seat.py", self.text)

    def test_the_recorder_report_runs_in_dry_run(self):
        self.assertIn("`python3 workforce/runtime/observability/install_claude_langfuse.py --dry-run`", self.text)
        self.assertIn("`install_codex_langfuse.py --dry-run`", self.text)
        self.assertIn("Never use `--check` here", self.text)
        self.assertNotRegex(self.text, r"langfuse\.py --check`")

    def test_no_temporary_folder_anywhere_in_the_update(self):
        self.assertNotIn("mkdtemp", self.text)
        self.assertNotIn("temp folder>", self.text)
        section = self.text[:self.text.index("## One combined question")]
        self.assertNotIn("temporary folder", section)


class ReadsThatNeverFail(unittest.TestCase):
    """The replacement reads exit 0 and print nothing when the path is missing; the old ones exit nonzero."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=str(base / "gitconfig"))
        (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n")
        self.repo = base / "wb"
        (self.repo / "work" / "course" / "staff").mkdir(parents=True)
        (self.repo / ".aibl" / "programs").mkdir(parents=True)
        (self.repo / ".aibl" / "programs" / "agent-workforce.json").write_text("{}\n")
        (self.repo / "work" / "course" / "staff" / "seat-names.md").write_text("x\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        (self.repo / "work" / "course" / "staff" / "connectors.yaml").write_text("x\n")  # on disk, untracked

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_ls_tree_lists_what_a_commit_has(self):
        p = self.git("ls-tree", "--name-only", "HEAD", "--", "workforce/VERSIONS.json", ".aibl/programs/agent-workforce.json")
        self.assertEqual((p.returncode, p.stdout.split()), (0, [".aibl/programs/agent-workforce.json"]))
        p = self.git("ls-tree", "--name-only", "HEAD", "--", "workforce/runtime/start_fresh.py")
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertNotEqual(self.git("cat-file", "-e", "HEAD:workforce/runtime/start_fresh.py").returncode, 0)
        self.assertNotEqual(self.git("cat-file", "-p", "HEAD:workforce/VERSIONS.json").returncode, 0)

    def test_ls_files_lists_what_is_on_disk(self):
        p = self.git("ls-files", "--cached", "--others", "--", "workforce/skills/aibl-agent-setup/scripts/name_seat.py",
                     "work/course/staff/seat-names.md", "work/course/staff/connectors.yaml")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(sorted(p.stdout.split()), ["work/course/staff/connectors.yaml", "work/course/staff/seat-names.md"])


if __name__ == "__main__":
    unittest.main()
