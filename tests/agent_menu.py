"""The Claude Code agent menu: --agent-menu reports, --agent-menu-apply fixes, the hook says one line.

Synthetic: a throwaway workbench and a throwaway home folder (HOME / USERPROFILE), so the
real ~/.claude is never touched. No app, account or installation claim.
"""
import json, os, subprocess, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
# never moved: the terminal Chief aibl-bridge-setup renders (#96), the student's own seat, a second workbench's
NOT_OURS = ["aibl-chief-of-staff-lead.md", "aibl-my-own-seat.md", "aibl-other-workbench.md"]
# a real course name (the hook only ever moves names on its allowlist): this fixture's course
# shipped it in edition one and retired it in edition two
RETIRED = "aibl-echo.md"


class AgentMenu(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.wb = base / "workbench"
        self.home = base / "home"
        # the course: its published student branch shipped aibl-echo, then retired it
        course = base / "course"
        (course / ".claude" / "agents").mkdir(parents=True)
        cagents = course / ".claude" / "agents"
        (cagents / "aibl-chief-of-staff.md").write_text("chief v1\n")
        (cagents / "aibl-the-professor.md").write_text("professor\n")
        (cagents / RETIRED).write_text("old seat\n")
        self.git_in(course, "init", "-q", "-b", "student")
        self.commit_in(course, "edition one")
        (cagents / "aibl-chief-of-staff.md").write_text("chief v2\n")
        (cagents / RETIRED).unlink()
        self.commit_in(course, "edition two")
        # the student's workbench, joined to that program
        agents = self.wb / ".claude" / "agents"
        agents.mkdir(parents=True)
        (self.wb / ".aibl").mkdir()
        (self.wb / ".aibl" / "template.json").write_text("{}\n")
        (agents / "aibl-chief-of-staff.md").write_text("chief v2\n")
        (agents / "aibl-the-professor.md").write_text("professor\n")
        (agents / "my-own-helper.md").write_text("not ours to copy\n")
        (agents / "aibl-my-own-seat.md").write_text("the student's own\n")
        (agents / RETIRED).write_text("old seat\n")                          # this workbench is on edition one
        self.git("init", "-q", "-b", "main")
        self.commit_all("workbench")
        (agents / "aibl-my-own-seat.md").unlink()                             # the student retired their own
        self.commit_all("retire my own seat")
        # the official remote; this one fetch reads the local fixture instead (the remote's
        # effective URL stays official, which is what the hook verifies)
        official = "https://github.com/aibuild-lab/agent-workforce.git"
        self.git("remote", "add", "agent-workforce", official)
        self.git("-c", f"url.{course}.insteadOf={official}", "fetch", "-q", "agent-workforce", "student")
        self.menu = self.home / ".claude" / "agents"
        # the hook's own fetch must not reach the network in a test: https is switched off
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_PROJECT_DIR=str(self.wb), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never",
                        GIT_TERMINAL_PROMPT="0")
        # on edition one this workbench put its agents in the menu (and recorded that it did)
        self.run_hook("--agent-menu-apply")
        (agents / RETIRED).unlink()                                           # then took edition two
        self.commit_all("edition two")
        (self.menu / "aibl-the-professor.md").unlink()                        # missing
        (self.menu / "aibl-chief-of-staff.md").write_text("chief v1\n")      # changed
        # RETIRED stays as this workbench placed it: a leftover
        (self.menu / "aibl-other-workbench.md").write_text("theirs\n")      # aibl- but never shipped
        (self.menu / "aibl-my-own-seat.md").write_text("the student's own\n")   # the student's, not ours
        (self.menu / "aibl-chief-of-staff-lead.md").write_text("terminal Chief\n")  # rendered locally (#96)
        (self.menu / "someone-elses.md").write_text("leave me alone\n")     # not aibl-

    def tearDown(self):
        self.temp.cleanup()

    def git_in(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    def commit_in(self, repo, message):
        self.git_in(repo, "add", "-A")
        self.git_in(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def git(self, *args):
        self.git_in(self.wb, *args)

    def commit_all(self, message):
        self.commit_in(self.wb, message)

    def run_hook(self, *args, stdin=""):
        p = subprocess.run(["node", str(HOOK), *args], input=stdin, text=True, capture_output=True,
                           env=self.env, cwd=str(self.wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_report_apply_and_hook_line(self):
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["status"], "out_of_step")
        self.assertEqual(report["missing"], ["aibl-the-professor.md"])
        self.assertEqual(report["changed"], ["aibl-chief-of-staff.md"])
        self.assertEqual(report["leftover"], [RETIRED])
        self.assertEqual(report["not_ours"], NOT_OURS)
        self.assertTrue(Path(report["menu_folder"]).samefile(self.menu))

        # the hook only reports, and says so
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        out = json.loads(self.run_hook(stdin=payload))
        line = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("AIBL agent menu check, nothing was changed", line)
        self.assertIn("aibl-the-professor.md", line)
        self.assertIn(RETIRED, line)
        # chief v1 is a version the course published before this workbench's v2: proven older.
        # A copy is called older only with that proof (tests/older_course_copies.py has a newer one).
        self.assertEqual(report["older"], ["aibl-chief-of-staff.md"])
        self.assertIn("older course versions in the user folder (this workbench has a newer course version): "
                      "aibl-chief-of-staff.md", line)
        self.assertNotIn("course copies in the menu that differ", line)
        self.assertNotIn("aibl-other-workbench.md", line)
        self.assertIn("do not hand them the command", line)
        self.assertFalse((self.menu / "aibl-the-professor.md").exists())

        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["status"], "in_step")
        self.assertEqual((self.menu / "aibl-the-professor.md").read_text(), "professor\n")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "chief v2\n")
        self.assertFalse((self.menu / RETIRED).exists())
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / RETIRED).read_text(), "old seat\n")
        self.assertNotEqual(backup.parent.parent, self.menu.parent / "agents")
        self.assertEqual((self.menu / "someone-elses.md").read_text(), "leave me alone\n")
        self.assertEqual((self.menu / "aibl-other-workbench.md").read_text(), "theirs\n")
        self.assertEqual((self.menu / "aibl-my-own-seat.md").read_text(), "the student's own\n")
        self.assertEqual((self.menu / "aibl-chief-of-staff-lead.md").read_text(), "terminal Chief\n")
        self.assertEqual(applied["applied"]["removed"], [RETIRED])
        self.assertFalse((self.menu / "my-own-helper.md").exists())
        status = subprocess.run(["git", "-C", str(self.wb), "status", "--porcelain"], text=True, capture_output=True)
        self.assertEqual(status.stdout, "")

        # in step: the hook stays quiet about the menu
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        self.assertNotIn("agent menu", self.run_hook(stdin=payload))

    def test_never_writes_through_a_link(self):
        victim = Path(self.temp.name) / "other-workbench-chief.md"
        victim.write_text("another workbench's chief\n")
        dest = self.menu / "aibl-chief-of-staff.md"
        dest.unlink()
        try:
            os.symlink(victim, dest)
        except (OSError, NotImplementedError):
            self.skipTest("this machine cannot create symlinks")
        # a link to bytes the course never made: the student's own, kept and reported
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertIn("aibl-chief-of-staff.md", applied["edited"])
        self.assertTrue(dest.is_symlink())
        self.assertEqual(victim.read_text(), "another workbench's chief\n")
        # on the student's yes the link itself moves to the backup; what it pointed at is untouched
        applied = json.loads(self.run_hook("--agent-menu-apply", "--replace-edited", "aibl-chief-of-staff.md"))
        self.assertEqual(victim.read_text(), "another workbench's chief\n")
        self.assertFalse(dest.is_symlink())
        self.assertEqual(dest.read_text(), "chief v2\n")
        moved = Path(applied["applied"]["removed_to"]) / "replaced" / "aibl-chief-of-staff.md"
        self.assertTrue(moved.is_symlink())

    def test_changed_contents_alone_count(self):
        # every name present, one copy stale: still out of step (another folder open runs the stale copy)
        (self.menu / RETIRED).unlink()
        (self.menu / "aibl-the-professor.md").write_text("professor\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["status"], report["missing"], report["leftover"]), ("out_of_step", [], []))
        self.assertEqual(report["changed"], ["aibl-chief-of-staff.md"])

    def test_never_ours_alone_is_in_step(self):
        # a second workbench's aibl- entry is never a reason to speak up or move anything
        (self.menu / RETIRED).unlink()
        (self.menu / "aibl-chief-of-staff.md").write_text("chief v2\n")
        (self.menu / "aibl-the-professor.md").write_text("professor\n")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["status"], report["not_ours"]), ("in_step", NOT_OURS))

    def test_no_program_ref_means_no_leftovers(self):
        # before the program's branch is fetched, nothing counts as ours to move
        self.git("remote", "remove", "agent-workforce")
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual(report["leftover"], [])
        self.assertIn(RETIRED, report["not_ours"])

    def test_no_agents_left_still_cleans_up_leftovers(self):
        # the workbench has no aibl- agents any more: nothing to copy, but its own retired
        # copy is still found and moved (Codex review of #9, finding 5)
        for f in (self.wb / ".claude" / "agents").glob("aibl-*.md"):
            f.unlink()
        report = json.loads(self.run_hook("--agent-menu"))
        self.assertEqual((report["status"], report["missing"], report["leftover"]), ("out_of_step", [], [RETIRED]))
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["removed"], [RETIRED])
        self.assertEqual(applied["applied"]["copied"], [])
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["status"], "no_agents")


if __name__ == "__main__":
    unittest.main()
