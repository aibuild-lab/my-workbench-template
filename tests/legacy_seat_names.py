"""A seat named by the naming step as published before seat-names.json (agent-workforce 521234a).

The live case, 09-28: a student on the published 521234a named their Chief "Hestia" in Lesson 32.
The published name_seat.py records names only in work/course/staff/seat-names.md and rewrites one
line of the agent file, the title: "# [student names this agent], your Chief of Staff" became
"# Hestia, your Chief of Staff". The agent menu read only seat-names.json, so the named Chief was a
name_conflict and never reached the @ menu. With no seat-names.json, the hook now reads the table: a
listed seat whose file is a published version except for the recorded name in that title line is
`renamed`.

Synthetic (a throwaway course, workbench and HOME), with the published script's exact output for
"Hestia" rebuilt here line for line. The same case against the real published files and the real
published name_seat.py runs when AIBL_PUBLISHED_521234A points at a checkout of that edition.
"""
import json, os, shutil, subprocess, sys, tempfile, unittest, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_list  # noqa: E402  (the program's list of its agents, built as the course builds it)

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"
CHIEF = "aibl-chief-of-staff.md"
PLACEHOLDER = "[student names this agent]"
SHIPPED_CHIEF = (b"---\nname: aibl-chief-of-staff\ndescription: The front door.\nmodel: inherit\n---\n"
                 b"# " + PLACEHOLDER.encode() + b", your Chief of Staff\n\nYou are the Chief of Staff of this organization.\n")
# name_seat.py as published (521234a): exactly the title line changes, and the table is written
NAMED_CHIEF = SHIPPED_CHIEF.replace(PLACEHOLDER.encode(), b"Hestia", 1)
SEAT_NAMES_MD = """# Seat names

The names you gave your seats. This is your record. Gigawatt puts each name into the seat's files when you say yes, and puts it back after a course update. The @ id (for example `aibl-chief-of-staff`) never changes; only the name the seat goes by does.

To change a name, ask Gigawatt. Editing this table by hand does not change the seat's files.

| Seat | Name | Named on | Your yes |
|---|---|---|---|
| aibl-chief-of-staff | Hestia | 2026-09-28 | Yes, call my Chief of Staff Hestia |
"""


def with_preview(run, args):
    args = list(args)
    if args and args[0] == "--agent-menu-apply" and "--expect" not in args and "--raw" not in args:
        args += ["--expect", json.loads(run("--agent-menu"))["preview_sha256"]]
    return [a for a in args if a != "--raw"]


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.menu = self.home / ".claude" / "agents"
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.https.allow", GIT_CONFIG_VALUE_0="never", GIT_TERMINAL_PROMPT="0")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True,
                              capture_output=True).stdout

    def commit(self, repo, message):
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)

    def run_hook(self, wb, *args, stdin=""):
        args = with_preview(lambda *a: self.run_hook(wb, *a), args)
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(wb))
        p = subprocess.run(["node", str(HOOK), *args], input=stdin, text=True, capture_output=True, env=env, cwd=str(wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def report(self, wb):
        return json.loads(self.run_hook(wb, "--agent-menu"))

    def apply(self, wb, *extra):
        return json.loads(self.run_hook(wb, "--agent-menu-apply", *extra))

    def hook_line(self, wb):
        out = self.run_hook(wb, stdin=json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(wb)}))
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out.strip() else ""

    def placed(self):
        f = self.home / ".claude" / "aibl-agent-menu-placed.json"
        return json.loads(f.read_text()) if f.exists() else {"agents": {}}


class ASeatNamedByThePublishedNamingStep(Base):
    def setUp(self):
        super().setUp()
        # the course: its Chief in the published shape, and its list of agents
        self.course = self.base / "course"
        self.write(self.course / ".claude" / "agents" / CHIEF, SHIPPED_CHIEF)
        self.write(self.course / ".claude" / "agents" / "aibl-kansa.md", b"---\nname: aibl-kansa\n---\n# Kansa\n")
        self.git(self.course, "init", "-q", "-b", "student")
        course_list.write(self.course)
        self.commit(self.course, "an edition")
        # the student's workbench on it, with the Chief the published naming step left
        self.wb = self.base / "workbench"
        self.write(self.wb / ".aibl" / "template.json", b"{}\n")
        self.write(self.wb / ".claude" / "agents" / CHIEF, SHIPPED_CHIEF)
        self.write(self.wb / ".claude" / "agents" / "aibl-kansa.md", b"---\nname: aibl-kansa\n---\n# Kansa\n")
        self.write(self.wb / course_list.LIST, self.git(self.course, "show", "student:" + course_list.LIST))
        self.git(self.wb, "init", "-q", "-b", "main")
        self.commit(self.wb, "enrolled")

    def name_hestia(self, line_ending=b"\n"):
        self.write(self.wb / ".claude" / "agents" / CHIEF, NAMED_CHIEF.replace(b"\n", line_ending))
        self.write(self.wb / "work" / "course" / "staff" / "seat-names.md", SEAT_NAMES_MD.encode())
        self.commit(self.wb, "named Hestia")

    def test_with_the_menu_empty_the_named_chief_is_added(self):
        self.name_hestia()
        report = self.report(self.wb)
        self.assertEqual((report["renamed"], report["renamed_missing"], report["name_conflict"]), ([CHIEF], [CHIEF], []))
        self.assertIn("your renamed Chief of Staff (Hestia) is not in the @ agent menu yet", self.hook_line(self.wb))
        self.assertEqual(self.apply(self.wb, "--raw")["refused"], "no_preview")
        applied = self.apply(self.wb)
        self.assertIn(CHIEF, applied["applied"]["copied"])
        self.assertEqual((self.menu / CHIEF).read_bytes(), NAMED_CHIEF)
        self.assertNotIn(CHIEF, self.placed()["agents"])     # the student's file, never a course copy
        self.assertEqual(self.report(self.wb)["status"], "in_step")
        self.assertEqual(self.hook_line(self.wb), "")        # no nag once it is in step

    def test_with_the_menu_holding_the_published_chief_it_is_replaced_behind_a_backup(self):
        self.apply(self.wb)                                   # the course's Chief placed before the naming
        self.assertEqual((self.menu / CHIEF).read_bytes(), SHIPPED_CHIEF)
        self.name_hestia()
        report = self.report(self.wb)
        self.assertEqual((report["renamed"], report["renamed_replace"], report["name_conflict"], report["edited"]),
                         ([CHIEF], [CHIEF], [], []))
        self.assertIn("the @ agent menu still has the course's copy of your renamed Chief of Staff (Hestia)", self.hook_line(self.wb))
        self.assertEqual(self.apply(self.wb, "--raw")["refused"], "no_preview")
        self.assertEqual((self.menu / CHIEF).read_bytes(), SHIPPED_CHIEF)
        applied = self.apply(self.wb)
        self.assertEqual(applied["applied"]["replaced"], [CHIEF])
        self.assertEqual((self.menu / CHIEF).read_bytes(), NAMED_CHIEF)
        self.assertEqual((Path(applied["applied"]["removed_to"]) / "replaced" / CHIEF).read_bytes(), SHIPPED_CHIEF)
        self.assertEqual(self.report(self.wb)["status"], "in_step")
        self.assertEqual(self.hook_line(self.wb), "")

    def test_a_windows_checkout_of_the_named_chief_counts_too(self):
        self.name_hestia(b"\r\n")
        report = self.report(self.wb)
        self.assertEqual((report["renamed"], report["name_conflict"]), ([CHIEF], []))

    def test_a_hand_edited_body_is_still_a_name_conflict(self):
        self.name_hestia()
        self.write(self.wb / ".claude" / "agents" / CHIEF, NAMED_CHIEF + b"\nA rule I added myself.\n")
        self.commit(self.wb, "my own edit")
        report = self.report(self.wb)
        self.assertEqual((report["renamed"], report["name_conflict"]), ([], [CHIEF]))
        self.apply(self.wb)
        self.assertFalse((self.menu / CHIEF).exists())

    def test_a_name_the_table_does_not_hold_is_a_name_conflict(self):
        self.name_hestia()
        self.write(self.wb / "work" / "course" / "staff" / "seat-names.md", SEAT_NAMES_MD.replace("Hestia", "Ada").encode())
        self.commit(self.wb, "a different name in the table")
        self.assertEqual(self.report(self.wb)["name_conflict"], [CHIEF])

    def test_any_other_menu_copy_is_left_alone_and_reported(self):
        self.name_hestia()
        self.write(self.menu / CHIEF, b"a chief of my own\n")
        report = self.report(self.wb)
        self.assertEqual((report["renamed"], report["renamed_menu_conflict"], report["renamed_replace"]), ([CHIEF], [CHIEF], []))
        self.assertIn("neither your named version nor a course version, so it is left alone", self.hook_line(self.wb))
        self.apply(self.wb)
        self.assertEqual((self.menu / CHIEF).read_bytes(), b"a chief of my own\n")

    def test_seat_names_json_rules_when_it_is_there(self):
        # the newer naming step's record exists: the table is not read (only the json's files count)
        self.name_hestia()
        self.write(self.wb / "work" / "course" / "staff" / "seat-names.json",
                   json.dumps({"version": 1, "agents": {}}).encode())
        self.commit(self.wb, "the newer record")
        self.assertEqual(self.report(self.wb)["name_conflict"], [CHIEF])


@unittest.skipUnless(os.environ.get("AIBL_PUBLISHED_521234A"),
                     "set AIBL_PUBLISHED_521234A to a checkout of aibuild-lab/agent-workforce at 521234a")
class TheLiveCaseOnThePublishedEdition(Base):
    """The published edition merged as aibl-enroll does, named by the PUBLISHED name_seat.py, then the hook."""

    def workbench(self):
        published = Path(os.environ["AIBL_PUBLISHED_521234A"])
        wb = self.base / "workbench"
        self.write(wb / ".aibl" / "template.json", b"{}\n")
        self.git(wb, "init", "-q", "-b", "main")
        self.commit(wb, "workbench")
        self.git(wb, "remote", "add", "agent-workforce", OFFICIAL)
        self.git(wb, "-c", f"url.{published}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce", "student")
        self.git(wb, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "merge", "-q", "--allow-unrelated-histories",
                 "--no-ff", "-m", "Add Agent Workforce", "agent-workforce/student")
        return wb

    def name_hestia(self, wb, global_dir):
        p = subprocess.run([sys.executable, str(wb / "workforce/skills/aibl-agent-setup/scripts/name_seat.py"),
                            "--seat", "aibl-chief-of-staff", "--name", "Hestia", "--yes", "Yes, call my Chief of Staff Hestia",
                            "--global-agents", str(global_dir), "--skip-drift"], cwd=str(wb), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.commit(wb, "named Hestia")

    def test_menu_empty(self):
        wb = self.workbench()
        self.menu.mkdir(parents=True)
        self.name_hestia(wb, self.menu)
        report = self.report(wb)
        self.assertEqual((report["course_agents_from"], report["renamed_missing"], report["name_conflict"]),
                         ("legacy_edition", [CHIEF], []))
        applied = self.apply(wb)
        self.assertEqual((applied["applied"]["errors"], applied["status"]), ([], "in_step"))
        self.assertEqual((self.menu / CHIEF).read_bytes(), (wb / ".claude" / "agents" / CHIEF).read_bytes())
        self.assertEqual(len([p for p in self.menu.iterdir() if p.suffix == ".md"]), 8)
        self.assertEqual(self.hook_line(wb), "")

    def test_menu_holding_the_published_chief(self):
        wb = self.workbench()
        self.apply(wb)
        self.name_hestia(wb, self.base / "elsewhere")        # a thread whose global folder is not this menu
        report = self.report(wb)
        self.assertEqual((report["renamed_replace"], report["name_conflict"]), ([CHIEF], []))
        applied = self.apply(wb)
        self.assertEqual((applied["applied"]["replaced"], applied["status"]), ([CHIEF], "in_step"))
        self.assertEqual((self.menu / CHIEF).read_bytes(), (wb / ".claude" / "agents" / CHIEF).read_bytes())
        self.assertEqual(self.hook_line(wb), "")


if __name__ == "__main__":
    unittest.main()
