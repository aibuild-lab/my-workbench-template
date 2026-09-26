"""An older course copy in the user folder is an older course version, not the student's edits.

The 09-26-2026 Windows run: a student enrolled on the 09-21 edition had all eight agents in
~/.claude/agents byte-for-byte as Git for Windows checked them out (CRLF line endings), and
the agent menu called every one of them "your own edits", because it matched only the raw
bytes against the course's LF blobs. Any version the course's student branch ever published
is a course copy, whatever its line endings; only content no version has is the student's.

Synthetic: a throwaway course, workbench and home folder (HOME / USERPROFILE), so the real
~/.claude is never touched. Every file is written as exact bytes, so the test means the same
on a Mac and on Windows. No app, account or installation claim.
"""
import json, os, subprocess, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"
CHIEF = "aibl-chief-of-staff.md"
PROFESSOR = "aibl-the-professor.md"

V1 = b"---\nname: aibl-chief-of-staff\ntools: Read, Agent\n---\nchief, the 09-21 edition\n"
V2 = b"---\nname: aibl-chief-of-staff\ntools: Read, Agent, SendMessage, ToolSearch\n---\nchief, the current edition\n"
V3 = b"---\nname: aibl-chief-of-staff\ntools: Read, Agent, SendMessage, ToolSearch\n---\nchief, a newer edition\n"
PROF = b"professor\n"
BRIDGE_V1 = b"bridge, the 09-21 edition\n"
BRIDGE_V2 = b"bridge, the current edition\n"


def crlf(data):
    return data.replace(b"\n", b"\r\n")


class OlderCourseCopies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.wb = base / "workbench"
        self.home = base / "home"
        # The course's published student branch: the 09-21 edition, then the current one.
        # core.autocrlf off, so its blobs are exactly the LF bytes written here.
        self.course = base / "course"
        self.write(self.course / ".claude" / "agents" / CHIEF, V1)
        self.write(self.course / ".claude" / "agents" / PROFESSOR, PROF)
        self.write(self.course / ".claude" / "skills" / "aibl-bridge" / "SKILL.md", BRIDGE_V1)
        self.git(self.course, "init", "-q", "-b", "student")
        self.commit(self.course, "Student edition, 09-21")
        self.write(self.course / ".claude" / "agents" / CHIEF, V2)
        self.write(self.course / ".claude" / "skills" / "aibl-bridge" / "SKILL.md", BRIDGE_V2)
        self.commit(self.course, "Student edition, current")
        # The student's workbench on the current edition, as Git for Windows checks it out (CRLF).
        self.write(self.wb / ".aibl" / "template.json", b"{}\n")
        self.write(self.wb / ".claude" / "agents" / CHIEF, crlf(V2))
        self.write(self.wb / ".claude" / "agents" / PROFESSOR, crlf(PROF))
        self.write(self.wb / ".claude" / "skills" / "aibl-bridge" / "SKILL.md", crlf(BRIDGE_V2))
        self.git(self.wb, "init", "-q", "-b", "main")
        self.commit(self.wb, "workbench")
        self.git(self.wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.fetch()
        self.menu = self.home / ".claude" / "agents"
        self.menu.mkdir(parents=True)
        self.write(self.menu / PROFESSOR, crlf(PROF))
        # the hook's own fetch must not reach the network in a test: https is switched off
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        CLAUDE_PROJECT_DIR=str(self.wb), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never",
                        GIT_TERMINAL_PROMPT="0")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True, capture_output=True)

    def commit(self, repo, message):
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def fetch(self):
        # the remote's effective URL stays official (what the hook verifies); this one fetch
        # reads the local fixture instead
        self.git(self.wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce", "student")

    def run_hook(self, *args, stdin=""):
        p = subprocess.run(["node", str(HOOK), *args], input=stdin, text=True, capture_output=True,
                           env=self.env, cwd=str(self.wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def report(self):
        return json.loads(self.run_hook("--agent-menu"))

    def hook_line(self):
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(self.wb)})
        return json.loads(self.run_hook(stdin=payload))["hookSpecificOutput"]["additionalContext"]

    def test_an_older_course_copy_is_offered_as_an_update(self):
        self.write(self.menu / CHIEF, V1)
        report = self.report()
        self.assertEqual((report["changed"], report["edited"]), ([CHIEF], []))
        self.assertEqual(report.get("older"), [CHIEF])
        line = self.hook_line()
        self.assertIn(f"older course versions in the user folder (this workbench has a newer course version): {CHIEF}", line)
        self.assertIn("is an older course version; update it to the current one? The old copy goes to a backup.", line)
        self.assertNotIn("changes that are not from any course version", line)

    def test_a_windows_checkout_of_an_older_course_copy_is_still_the_course_version(self):
        # the 09-26 run: the 09-21 edition with CRLF line endings
        self.write(self.menu / CHIEF, crlf(V1))
        report = self.report()
        self.assertEqual((report["changed"], report["edited"]), ([CHIEF], []))
        self.assertEqual(report.get("older"), [CHIEF])
        # one yes updates it (no --replace-edited needed), and the old copy goes to a backup
        applied = json.loads(self.run_hook("--agent-menu-apply"))
        self.assertEqual(applied["applied"]["replaced"], [CHIEF])
        self.assertEqual((self.menu / CHIEF).read_bytes(), crlf(V2))
        backup = Path(applied["applied"]["removed_to"])
        self.assertEqual((backup / "replaced" / CHIEF).read_bytes(), crlf(V1))
        self.assertEqual(applied["status"], "in_step")

    def test_a_truly_edited_copy_is_still_the_students(self):
        for data in (V1 + b"my own line\n", crlf(V1 + b"my own line\n")):
            self.write(self.menu / CHIEF, data)
            report = self.report()
            self.assertEqual((report["changed"], report["edited"]), ([], [CHIEF]))
            self.assertEqual(report.get("older"), [])
            line = self.hook_line()
            self.assertIn(f"changes that are not from any course version (never replaced unasked): {CHIEF}", line)
            self.assertNotIn(f"newer course version): {CHIEF}", line)
            # the one yes keeps it; only the student's own yes for this copy replaces it
            self.run_hook("--agent-menu-apply")
            self.assertEqual((self.menu / CHIEF).read_bytes(), data)

    def test_a_newer_course_copy_is_never_called_older(self):
        # the course published an edition this workbench has not taken yet
        self.write(self.course / ".claude" / "agents" / CHIEF, V3)
        self.commit(self.course, "Student edition, newer")
        self.fetch()
        self.write(self.menu / CHIEF, crlf(V3))
        report = self.report()
        self.assertEqual((report["changed"], report["edited"]), ([CHIEF], []))
        self.assertEqual(report.get("older"), [])
        line = self.hook_line()
        self.assertIn(f"course copies in the menu that differ from this workbench's: {CHIEF}", line)
        self.assertNotIn("older course versions in the user folder", line)

    def test_line_endings_alone_are_in_step(self):
        # the current edition with LF endings against this workbench's CRLF checkout
        self.write(self.menu / CHIEF, V2)
        self.write(self.menu / PROFESSOR, PROF)
        self.write(self.home / ".claude" / "skills" / "aibl-bridge" / "SKILL.md", crlf(BRIDGE_V2))
        report = self.report()
        self.assertEqual((report["status"], report["in_step"]), ("in_step", [CHIEF, PROFESSOR]))

    def test_an_older_course_bridge_skill_is_offered_as_an_update(self):
        self.write(self.menu / CHIEF, crlf(V2))
        skill = self.home / ".claude" / "skills" / "aibl-bridge" / "SKILL.md"
        self.write(skill, crlf(BRIDGE_V1))
        skills = self.report()["skills"]
        self.assertEqual((skills["changed"], skills["edited"]), (["aibl-bridge"], []))
        self.assertEqual(skills.get("older"), ["aibl-bridge"])
        self.write(skill, crlf(BRIDGE_V1 + b"my own line\n"))
        skills = self.report()["skills"]
        self.assertEqual((skills["changed"], skills["edited"]), ([], ["aibl-bridge"]))
        self.assertEqual(skills.get("older"), [])


if __name__ == "__main__":
    unittest.main()
