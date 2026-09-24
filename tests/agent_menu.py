"""The Claude Code agent menu: --agent-menu reports, --agent-menu-apply fixes, the hook says one line.

Synthetic: a throwaway workbench and a throwaway home folder (HOME / USERPROFILE), so the
real ~/.claude is never touched. No app, account or installation claim.
"""
import json, os, subprocess, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"


class AgentMenu(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.wb = base / "workbench"
        self.home = base / "home"
        agents = self.wb / ".claude" / "agents"
        agents.mkdir(parents=True)
        (self.wb / ".aibl").mkdir()
        (self.wb / ".aibl" / "template.json").write_text("{}\n")
        (agents / "aibl-chief-of-staff.md").write_text("chief v2\n")
        (agents / "aibl-the-professor.md").write_text("professor\n")
        (agents / "my-own-helper.md").write_text("not ours to copy\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "wb")
        self.menu = self.home / ".claude" / "agents"
        self.menu.mkdir(parents=True)
        (self.menu / "aibl-chief-of-staff.md").write_text("chief v1\n")      # changed
        (self.menu / "aibl-retired-seat.md").write_text("old seat\n")        # leftover
        (self.menu / "someone-elses.md").write_text("leave me alone\n")     # not aibl-
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_PROJECT_DIR=str(self.wb))

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.wb), *args], check=True, capture_output=True)

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
        self.assertEqual(report["leftover"], ["aibl-retired-seat.md"])
        self.assertTrue(Path(report["menu_folder"]).samefile(self.menu))

        # the hook only reports, and says so
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        out = json.loads(self.run_hook(stdin=payload))
        line = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("AIBL agent menu check, nothing was changed", line)
        self.assertIn("aibl-the-professor.md", line)
        self.assertIn("aibl-retired-seat.md", line)
        self.assertFalse((self.menu / "aibl-the-professor.md").exists())

        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["status"], "in_step")
        self.assertEqual((self.menu / "aibl-the-professor.md").read_text(), "professor\n")
        self.assertEqual((self.menu / "aibl-chief-of-staff.md").read_text(), "chief v2\n")
        self.assertFalse((self.menu / "aibl-retired-seat.md").exists())
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "aibl-retired-seat.md").read_text(), "old seat\n")
        self.assertNotEqual(backup.parent.parent, self.menu.parent / "agents")
        self.assertEqual((self.menu / "someone-elses.md").read_text(), "leave me alone\n")
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
        self.run_hook("--agent-menu-apply")
        self.assertEqual(victim.read_text(), "another workbench's chief\n")
        self.assertFalse(dest.is_symlink())
        self.assertEqual(dest.read_text(), "chief v2\n")

    def test_no_agents_means_no_line(self):
        for f in (self.wb / ".claude" / "agents").glob("aibl-*.md"):
            f.unlink()
        self.assertEqual(json.loads(self.run_hook("--agent-menu"))["status"], "no_agents")


if __name__ == "__main__":
    unittest.main()
