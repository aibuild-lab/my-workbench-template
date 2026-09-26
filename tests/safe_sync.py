"""The course's sync touches only what the course shipped; the bridge skills and the home pointer.

Tyler's ruling (09-24): the agent-menu sync and its cleanup touch ONLY agents the course
itself shipped (the allowlist in update-check.mjs). Never the student's own agents in Claude
Code or Codex, aibl- named or not, and never other course components.

Synthetic: a throwaway workbench and a throwaway home folder (HOME / USERPROFILE), so the
real ~/.claude, ~/.codex and ~/.aibl are never touched. No app, account or installation claim.
"""
import json, os, stat, subprocess, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
WINDOWS = os.name == "nt"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"


def tree(folder):
    """Every file under folder with its bytes and (off Windows) its exec bit."""
    out = {}
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file() or p.is_symlink():
            mode = None if WINDOWS else bool(os.lstat(p).st_mode & stat.S_IXUSR)
            out[str(p.relative_to(folder))] = (os.readlink(p) if p.is_symlink() else p.read_bytes(), mode)
    return out


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.base = base
        self.wb = base / "workbench"
        self.home = base / "home"
        # The course's published branch. Edition one shipped aibl-echo, and (to prove the
        # allowlist is the ceiling) a -lead copy that is NOT on the allowlist; edition two
        # retired both.
        course = base / "course"
        cagents = course / ".claude" / "agents"
        cagents.mkdir(parents=True)
        (cagents / "aibl-chief-of-staff.md").write_text("chief\n")
        (cagents / "aibl-echo.md").write_text("echo\n")
        (cagents / "aibl-chief-of-staff-lead.md").write_text("terminal chief\n")
        self.git(course, "init", "-q", "-b", "student")
        self.commit(course, "edition one")
        (cagents / "aibl-echo.md").unlink()
        (cagents / "aibl-chief-of-staff-lead.md").unlink()
        self.commit(course, "edition two")

        # The student's workbench: the course's Chief, plus the student's own agents and skills.
        agents = self.wb / ".claude" / "agents"
        agents.mkdir(parents=True)
        (self.wb / ".aibl").mkdir()
        (self.wb / ".aibl" / "template.json").write_text("{}\n")
        (agents / "aibl-chief-of-staff.md").write_text("chief\n")
        (agents / "aibl-custom-mine.md").write_text("my own aibl- agent, workbench copy\n")
        (agents / "my-agent.md").write_text("my own agent, workbench copy\n")
        skills = self.wb / ".claude" / "skills"
        bridge = skills / "aibl-bridge"
        (bridge / "scripts" / "windows").mkdir(parents=True)
        (bridge / "SKILL.md").write_text("bridge v2\n")
        (bridge / "scripts" / "bridge-run.sh").write_text("#!/bin/sh\necho run\n")
        (bridge / "scripts" / "windows" / "bridge-run.ps1").write_text("Write-Output run\n")
        os.chmod(bridge / "scripts" / "bridge-run.sh", 0o755)
        (skills / "aibl-bridge-setup").mkdir()
        (skills / "aibl-bridge-setup" / "SKILL.md").write_text("bridge setup\n")
        (skills / "aibl-enroll").mkdir()
        (skills / "aibl-enroll" / "SKILL.md").write_text("template-owned, never synced\n")
        (skills / "aibl-my-skill").mkdir()
        (skills / "aibl-my-skill" / "SKILL.md").write_text("the student's own skill\n")
        self.git(self.wb, "init", "-q", "-b", "main")
        self.commit(self.wb, "workbench")
        self.course = course
        self.git(self.wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.fetch(self.wb)
        # the hook's own fetch must not reach the network in a test: https is switched off
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_PROJECT_DIR=str(self.wb), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never",
                        GIT_TERMINAL_PROMPT="0")
        # On edition one this workbench put aibl-echo in the menu (and recorded that it did);
        # then it took edition two, which retired aibl-echo.
        agents_now = list(agents.iterdir())
        hidden = self.base / "hidden"
        hidden.mkdir()
        for f in agents_now:
            f.rename(hidden / f.name)
        skills.rename(self.base / "hidden-skills")
        (agents / "aibl-echo.md").write_text("echo\n")
        self.run_hook("--agent-menu-apply")
        (agents / "aibl-echo.md").unlink()
        for f in hidden.iterdir():
            f.rename(agents / f.name)
        hidden.rmdir()
        (self.base / "hidden-skills").rename(skills)

        # The student's home folder: their own agents in Claude Code and Codex, a course
        # leftover, an off-list -lead copy the course history once held, and their own skills.
        self.menu = self.home / ".claude" / "agents"
        self.menu.mkdir(parents=True, exist_ok=True)
        (self.menu / "my-agent.md").write_text("my own agent\n")
        (self.menu / "aibl-custom-mine.md").write_text("my own aibl- agent\n")
        (self.menu / "aibl-chief-of-staff-lead.md").write_text("terminal chief\n")
        (self.menu / "aibl-kansa.md").write_text("on the list, but no connected program shipped it\n")
        self.codex = self.home / ".codex" / "agents"
        self.codex.mkdir(parents=True)
        (self.codex / "my-codex-agent.toml").write_text('name = "mine"\n')
        (self.codex / "aibl-chief-of-staff.toml").write_text('name = "an old course copy, Codex is never touched"\n')
        self.hskills = self.home / ".claude" / "skills"
        (self.hskills / "my-skill").mkdir(parents=True)
        (self.hskills / "my-skill" / "SKILL.md").write_text("mine\n")
        (self.hskills / "aibl-custom-skill").mkdir()
        (self.hskills / "aibl-custom-skill" / "SKILL.md").write_text("mine too\n")
        self.aibl = self.home / ".aibl"
        self.aibl.mkdir()
        (self.aibl / "other.json").write_text('{"leave": "me"}\n')


    def tearDown(self):
        self.temp.cleanup()

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def fetch(self, wb):
        # the remote's effective URL stays official (what the hook verifies); this one fetch
        # reads the local fixture instead
        self.git(wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce", "student")

    def commit(self, repo, message):
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def run_hook(self, *args, stdin=""):
        p = subprocess.run(["node", str(HOOK), *args], input=stdin, text=True, capture_output=True,
                           env=self.env, cwd=str(self.wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def student_files(self):
        """Everything of the student's own, in both apps."""
        return {
            "menu": {n: (self.menu / n).read_bytes() for n in
                     ("my-agent.md", "aibl-custom-mine.md", "aibl-chief-of-staff-lead.md", "aibl-kansa.md")},
            "codex": tree(self.codex),
            "skills": {n: tree(self.hskills / n) for n in ("my-skill", "aibl-custom-skill")},
            "aibl": tree(self.aibl),
        }


class StudentsOwnAgentsAreNeverTouched(Fixture):
    def test_report_lists_only_course_names(self):
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["status"], "out_of_step")
        self.assertEqual(report["missing"], ["aibl-chief-of-staff.md"])
        self.assertEqual(report["changed"], [])
        self.assertEqual(report["leftover"], ["aibl-echo.md"])
        # the student's aibl- agent in the workbench is not synced into the menu
        self.assertEqual(report["skipped"], ["aibl-custom-mine.md"])
        # off the list, or on it but never shipped by a connected program: not ours to move
        self.assertEqual(report["not_ours"],
                         ["aibl-chief-of-staff-lead.md", "aibl-custom-mine.md", "aibl-kansa.md"])

    def test_apply_leaves_every_student_file_alone(self):
        before = self.student_files()
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["errors"], [])
        self.assertEqual(self.student_files(), before)
        # the one course agent was copied, the one course leftover moved (not deleted)
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "chief\n")
        self.assertFalse((self.menu / "aibl-echo.md").exists())
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "aibl-echo.md").read_text(), "echo\n")
        self.assertEqual(applied["applied"]["removed"], ["aibl-echo.md"])
        # the student's aibl- agent in the workbench was never copied over their own
        self.assertEqual((self.menu / "aibl-custom-mine.md").read_text(), "my own aibl- agent\n")
        self.assertEqual(sorted(p.name for p in self.menu.iterdir()),
                         ["aibl-chief-of-staff-lead.md", "aibl-chief-of-staff.md", "aibl-custom-mine.md",
                          "aibl-kansa.md", "my-agent.md"])
        # the workbench is untouched
        status = subprocess.run(["git", "-C", str(self.wb), "status", "--porcelain"], text=True, capture_output=True)
        self.assertEqual(status.stdout, "")

    def test_replaced_course_copy_is_kept_not_deleted(self):
        # a copy this workbench placed earlier (so its bytes are recorded as course-made) is refreshed
        chief = self.wb / ".claude" / "agents" / "aibl-chief-of-staff.md"
        chief.write_text("the chief of an earlier edition\n")
        self.run_hook("--agent-menu-apply")
        chief.write_text("chief\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["changed"], report["edited"]), (["aibl-chief-of-staff.md"], []))
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["replaced"], ["aibl-chief-of-staff.md"])
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "replaced" / "aibl-chief-of-staff.md").read_text(), "the chief of an earlier edition\n")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "chief\n")

    def test_a_copy_with_the_students_edits_is_kept_until_they_say_yes(self):
        # finding 4: bytes that match neither a recorded placement nor a course version are the student's
        (self.menu / "aibl-chief-of-staff.md").write_text("my own edits to the chief\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["changed"], report["edited"]), ([], ["aibl-chief-of-staff.md"]))
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "my own edits to the chief\n")
        applied = json.loads(self.run_hook("--agent-menu-apply", "--replace-edited", "aibl-chief-of-staff.md"))
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "chief\n")
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "replaced" / "aibl-chief-of-staff.md").read_text(), "my own edits to the chief\n")

    def test_a_published_course_version_counts_as_course_made(self):
        (self.course / ".claude" / "agents" / "aibl-chief-of-staff.md").write_text("chief, edition three\n")
        self.commit(self.course, "edition three")
        self.fetch(self.wb)
        (self.menu / "aibl-chief-of-staff.md").write_text("chief, edition three\n")
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["changed"], ["aibl-chief-of-staff.md"])

    def test_a_different_case_name_is_never_touched(self):
        # finding 1: on Mac and Windows AIBL-Chief-Of-Staff.md answers to aibl-chief-of-staff.md
        (self.menu / "AIBL-Chief-Of-Staff.md").write_text("the student's own, in capitals\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["case_conflict"], ["AIBL-Chief-Of-Staff.md (in the way of aibl-chief-of-staff.md)"])
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["replaced"], [])
        self.assertEqual(sorted(p.name for p in self.menu.iterdir() if p.name.lower() == "aibl-chief-of-staff.md"), ["AIBL-Chief-Of-Staff.md"])
        self.assertEqual((self.menu / "AIBL-Chief-Of-Staff.md").read_text(), "the student's own, in capitals\n")
        self.assertFalse((self.home / ".claude" / "aibl-agent-menu-removed").exists()
                         and any((self.home / ".claude" / "aibl-agent-menu-removed").rglob("*hief*")))

    def test_hook_line_names_only_course_items(self):
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        line = json.loads(self.run_hook(stdin=payload))["hookSpecificOutput"]["additionalContext"]
        for name in ("aibl-chief-of-staff.md", "aibl-echo.md", "aibl-bridge", "aibl-bridge-setup"):
            self.assertIn(name, line)
        for name in ("aibl-custom-mine", "my-agent", "aibl-chief-of-staff-lead", "aibl-kansa", "my-skill"):
            self.assertNotIn(name, line)
        self.assertIn("do not hand them the command", line)


class BridgeSkillsAreRealCopies(Fixture):
    def test_copies_both_bridge_skills_and_nothing_else(self):
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["skills"]["missing"], ["aibl-bridge", "aibl-bridge-setup"])
        before = self.student_files()
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["skills_copied"], ["aibl-bridge", "aibl-bridge-setup"])
        self.assertEqual(applied["status"], "in_step")
        for name in ("aibl-bridge", "aibl-bridge-setup"):
            dest = self.hskills / name
            self.assertTrue(dest.is_dir() and not dest.is_symlink())
            self.assertEqual(tree(dest), tree(self.wb / ".claude" / "skills" / name))
        if not WINDOWS:
            self.assertTrue(os.stat(self.hskills / "aibl-bridge" / "scripts" / "bridge-run.sh").st_mode & stat.S_IXUSR)
        # template-owned and student-owned skills are never copied or touched
        self.assertFalse((self.hskills / "aibl-enroll").exists())
        self.assertFalse((self.hskills / "aibl-my-skill").exists())
        self.assertEqual(self.student_files(), before)
        self.assertFalse((self.home / ".claude" / "aibl-agent-menu-staging").exists())

    def test_refresh_keeps_the_old_copy_and_the_exec_bit_counts(self):
        self.run_hook("--agent-menu-apply")
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["status"], "in_step")
        if not WINDOWS:
            os.chmod(self.hskills / "aibl-bridge" / "scripts" / "bridge-run.sh", 0o644)  # the 9/23 failure
            self.assertEqual(json.loads(self.run_hook("--agent-menu"))["skills"]["changed"], ["aibl-bridge"])
            os.chmod(self.hskills / "aibl-bridge" / "scripts" / "bridge-run.sh", 0o755)
        # an earlier edition's bridge that this workbench placed (recorded), then a new edition
        src = self.wb / ".claude" / "skills" / "aibl-bridge" / "SKILL.md"
        src.write_text("bridge v1\n")
        self.run_hook("--agent-menu-apply")
        src.write_text("bridge v2\n")
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["skills"]["changed"], ["aibl-bridge"])
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "skills" / "aibl-bridge" / "SKILL.md").read_text(), "bridge v1\n")
        self.assertEqual((self.hskills / "aibl-bridge" / "SKILL.md").read_text(), "bridge v2\n")
        if not WINDOWS:
            self.assertTrue(os.stat(self.hskills / "aibl-bridge" / "scripts" / "bridge-run.sh").st_mode & stat.S_IXUSR)

    def test_a_student_edited_bridge_skill_is_kept_until_they_say_yes(self):
        self.run_hook("--agent-menu-apply")
        (self.hskills / "aibl-bridge" / "SKILL.md").write_text("my own bridge notes\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["skills"]["changed"], report["skills"]["edited"]), ([], ["aibl-bridge"]))
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.hskills / "aibl-bridge" / "SKILL.md").read_text(), "my own bridge notes\n")
        self.run_hook("--agent-menu-apply", "--replace-edited", "aibl-bridge")
        self.assertEqual((self.hskills / "aibl-bridge" / "SKILL.md").read_text(), "bridge v2\n")

    def test_a_linked_skill_becomes_a_real_copy_without_touching_the_target(self):
        elsewhere = self.base / "another-workbench-bridge"
        elsewhere.mkdir()
        (elsewhere / "SKILL.md").write_bytes(b"another workbench's bridge\n")  # exact bytes, on Windows too
        try:
            os.symlink(elsewhere, self.hskills / "aibl-bridge", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        self.assertIn("aibl-bridge", json.loads(self.run_hook("--agent-menu"))["skills"]["changed"])
        self.run_hook("--agent-menu-apply")
        self.assertFalse((self.hskills / "aibl-bridge").is_symlink())
        self.assertEqual((self.hskills / "aibl-bridge" / "SKILL.md").read_text(), "bridge v2\n")
        self.assertEqual(tree(elsewhere), {"SKILL.md": (b"another workbench's bridge\n", tree(elsewhere)["SKILL.md"][1])})

    def test_a_workbench_skill_holding_a_link_is_refused(self):
        link = self.wb / ".claude" / "skills" / "aibl-bridge-setup" / "outside"
        try:
            os.symlink(self.base, link)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["skills"]["missing"], ["aibl-bridge"])
        self.assertTrue(report["skills"]["errors"])
        self.run_hook("--agent-menu-apply")
        self.assertFalse((self.hskills / "aibl-bridge-setup").exists())

    def test_no_course_agents_means_nothing_is_offered(self):
        (self.wb / ".claude" / "agents" / "aibl-chief-of-staff.md").unlink()
        report = json.loads(self.run_hook("--agent-menu"))
        # only the workbench's own retired copy is left to clean up; no skills are offered
        self.assertEqual((report["status"], report["leftover"]), ("out_of_step", ["aibl-echo.md"]))
        self.assertEqual((report["skills"]["missing"], report["skills"]["changed"]), ([], []))
        self.run_hook("--agent-menu-apply")
        self.assertFalse((self.hskills / "aibl-bridge").exists())
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["status"], "no_agents")


class LeftoverNeedsEvidence(Fixture):
    """Codex review of #9, findings 2 to 5: a leftover is moved only when it is provably this
    workbench's own retired copy."""

    def other_workbench(self, agents):
        other = self.base / "workbench-b"
        (other / ".claude" / "agents").mkdir(parents=True)
        (other / ".aibl").mkdir()
        (other / ".aibl" / "template.json").write_text("{}\n")
        for name, body in agents.items():
            (other / ".claude" / "agents" / name).write_text(body)
        self.git(other, "init", "-q", "-b", "main")
        self.commit(other, "workbench b")
        return other

    def run_in(self, wb, *args):
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(wb))
        p = subprocess.run(["node", str(HOOK), *args], text=True, capture_output=True, env=env, cwd=str(wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_the_fixture_leftover_is_ours(self):
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["leftover"], ["aibl-echo.md"])

    def test_not_a_leftover_while_the_current_edition_still_ships_it(self):
        # this workbench is an edition behind: the course brought aibl-echo back in edition three
        (self.course / ".claude" / "agents" / "aibl-echo.md").write_text("echo returns\n")
        self.commit(self.course, "edition three")
        self.fetch(self.wb)
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["leftover"], [])
        self.assertIn("aibl-echo.md", report["not_ours"])
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-echo.md").read_text(), "echo\n")

    def test_never_moves_what_another_workbench_placed_more_recently(self):
        other = self.other_workbench({"aibl-echo.md": "workbench b's echo\n"})
        self.run_in(other, "--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-echo.md").read_text(), "workbench b's echo\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["leftover"], [])
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-echo.md").read_text(), "workbench b's echo\n")

    def test_never_moves_it_while_another_known_workbench_still_has_it(self):
        # identical bytes, so workbench b never had to copy it; it is the recorded home workbench
        other = self.other_workbench({"aibl-echo.md": "echo\n"})
        (self.aibl / "workbench.json").write_text(json.dumps({"schema_version": "aibl.home-workbench/v1", "path": str(other)}))
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["leftover"], [])

    def test_never_moves_a_copy_edited_after_it_was_placed(self):
        (self.menu / "aibl-echo.md").write_text("echo, which the student edited\n")
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["leftover"], [])

    def test_never_replaces_another_workbenchs_newer_copy(self):
        other = self.other_workbench({"aibl-chief-of-staff.md": "workbench b's chief\n"})
        self.run_in(other, "--agent-menu-apply")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["changed"], report["other_workbench"]), ([], ["aibl-chief-of-staff.md"]))
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "workbench b's chief\n")
        # once workbench b is gone, this workbench may refresh it (the old copy is kept)
        import shutil
        for p in Path(other).rglob("*"):  # git's object files are read-only, which Windows refuses to delete
            if p.is_file() and not p.is_symlink():
                os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
        shutil.rmtree(other)
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["changed"], ["aibl-chief-of-staff.md"])

    def test_a_remote_only_named_like_the_program_proves_nothing(self):
        self.git(self.wb, "remote", "set-url", "agent-workforce", str(self.course))
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["leftover"], [])
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-echo.md").read_text(), "echo\n")

    def test_a_workbench_that_only_claimed_its_copy_keeps_it(self):
        # finding 2: workbench b's copy already matched, so it copied nothing, but its apply
        # recorded the claim; this workbench then never moves that entry out from under it
        other = self.other_workbench({"aibl-echo.md": "echo\n"})
        applied = self.run_in(other, "--agent-menu-apply")
        self.assertIn("aibl-echo.md", applied["applied"]["claimed"])
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["leftover"], [])
        self.run_hook("--agent-menu-apply")
        self.assertEqual((self.menu / "aibl-echo.md").read_text(), "echo\n")

    def test_the_home_workbenchs_customized_copy_is_kept_without_a_record(self):
        # finding 3: no record at all, but the bytes match the home workbench's current file
        other = self.other_workbench({"aibl-chief-of-staff.md": "home workbench's own chief\n"})
        (self.aibl / "workbench.json").write_text(json.dumps({"schema_version": "aibl.home-workbench/v1", "path": str(other)}))
        (self.home / ".claude" / "aibl-agent-menu-placed.json").unlink()
        (self.menu / "aibl-chief-of-staff.md").write_text("home workbench's own chief\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["changed"], report["edited"], report["other_workbench"]), ([], [], ["aibl-chief-of-staff.md"]))
        self.run_hook("--agent-menu-apply", "--replace-edited", "aibl-chief-of-staff.md")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "home workbench's own chief\n")

    def test_a_remote_rewritten_away_from_the_official_repository_proves_nothing(self):
        # finding 5: the official spelling, redirected by insteadOf, is not the official repository
        self.git(self.wb, "config", f"url.{self.course}.insteadOf", OFFICIAL)
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["leftover"], [])

    def test_a_running_apply_holds_a_lock(self):
        lock = self.home / ".claude" / "aibl-agent-menu.lock"
        lock.write_text("12345 now\n")
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["status"], "busy")
        self.assertFalse((self.menu / "aibl-chief-of-staff.md").exists())
        lock.unlink()
        self.run_hook("--agent-menu-apply")
        self.assertTrue((self.menu / "aibl-chief-of-staff.md").exists())
        self.assertFalse(lock.exists())

    def test_backup_folders_never_collide(self):
        first = json.loads(self.run_hook("--agent-menu-apply"))["applied"]["removed_to"]
        self.run_hook("--agent-menu-apply")
        (self.menu / "aibl-chief-of-staff.md").write_text("edits\n")
        second = json.loads(self.run_hook("--agent-menu-apply", "--replace-edited", "aibl-chief-of-staff.md"))["applied"]["removed_to"]
        self.assertNotEqual(first, second)
        self.assertRegex(Path(second).name, r"-[0-9a-f]{8}$")

    def test_a_linked_staging_folder_is_refused(self):
        elsewhere = self.base / "elsewhere-staging"
        elsewhere.mkdir()
        try:
            os.symlink(elsewhere, self.home / ".claude" / "aibl-agent-menu-staging", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied.get("refused"), "linked_folder")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_a_linked_agents_folder_is_refused(self):
        other = self.other_workbench({"aibl-chief-of-staff.md": "b's chief\n", "aibl-echo.md": "echo\n"})
        import shutil
        shutil.rmtree(self.menu)
        try:
            os.symlink(other / ".claude" / "agents", self.menu, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        before = tree(other)
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["status"], "linked_folder")
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["refused"], "linked_folder")
        self.assertEqual(tree(other), before)
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        line = json.loads(self.run_hook(stdin=payload))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Do not offer the fix", line)

    def test_a_linked_claude_folder_is_refused(self):
        import shutil
        real = self.base / "elsewhere-claude"
        shutil.move(str(self.home / ".claude"), str(real))
        try:
            os.symlink(real, self.home / ".claude", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        before = tree(real)
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied.get("refused"), "linked_folder")
        self.assertEqual(tree(real), before)


class HomeWorkbenchPointer(Fixture):
    def pointer(self):
        return self.aibl / "workbench.json"

    def test_report_then_record(self):
        report = json.loads(self.run_hook("--home-workbench"))
        self.assertEqual(report["status"], "not_recorded")
        self.assertFalse(self.pointer().exists())  # reporting writes nothing
        applied = json.loads(self.run_hook("--home-workbench-apply"))
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["status"], "this_workbench")
        written = json.loads(self.pointer().read_text())
        self.assertEqual(set(written), {"schema_version", "path"})
        self.assertEqual(written["schema_version"], "aibl.home-workbench/v1")
        self.assertTrue(Path(written["path"]).is_absolute())
        self.assertTrue(Path(written["path"]).samefile(self.wb))
        # nothing else under ~/.aibl
        self.assertEqual(sorted(p.name for p in self.aibl.iterdir()), ["other.json", "workbench.json"])
        self.assertEqual((self.aibl / "other.json").read_text(), '{"leave": "me"}\n')

    def test_another_folder_is_reported_before_it_is_replaced(self):
        other = self.base / "older-workbench"
        other.mkdir()
        self.pointer().write_text(json.dumps({"schema_version": "aibl.home-workbench/v1", "path": str(other)}))
        report = json.loads(self.run_hook("--home-workbench"))
        self.assertEqual((report["status"], report["recorded"]), ("another_folder", str(other)))
        applied = json.loads(self.run_hook("--home-workbench-apply"))
        self.assertEqual(applied["previous"], str(other))
        self.assertTrue(Path(json.loads(self.pointer().read_text())["path"]).samefile(self.wb))

    def test_never_writes_through_a_link(self):
        victim = self.base / "victim.json"
        victim.write_text("do not overwrite\n")
        try:
            os.symlink(victim, self.pointer())
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        self.assertEqual(json.loads(self.run_hook("--home-workbench"))["status"], "pointer_is_a_link")
        self.run_hook("--home-workbench-apply")
        self.assertEqual(victim.read_text(), "do not overwrite\n")
        self.assertFalse(self.pointer().is_symlink())

    def test_a_linked_aibl_folder_is_refused(self):
        import shutil
        real = self.base / "elsewhere-aibl"
        shutil.move(str(self.aibl), str(real))
        try:
            os.symlink(real, self.aibl, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        applied = json.loads(self.run_hook("--home-workbench-apply"))
        self.assertEqual((applied["applied"], applied["error"]), (False, "linked_folder"))
        self.assertFalse((real / "workbench.json").exists())

    def test_unreadable_pointer_is_reported(self):
        self.pointer().write_text("not json")
        self.assertEqual(json.loads(self.run_hook("--home-workbench"))["status"], "unreadable")


if __name__ == "__main__":
    unittest.main()
