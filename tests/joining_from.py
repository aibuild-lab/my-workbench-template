"""Where the student is joining from: `update-check.mjs --joining-from` and the words aibl-enroll
and aibl-update say with it.

Synthetic only: every test builds a throwaway home folder (HOME and USERPROFILE) and a throwaway
workbench inside it, so the real home folder, the real ~/GitHub and any real Camp or Team HQ setup
are never read. Set AIBL_TEST_SCRATCH to a folder to keep the throwaway folders there while they
exist (they are removed after each test either way). No network, no app, no account.

What it pins:
  - Agent Team HQ graduates are found from the program's stamp, its folders or its remote, and the
    night shift from the hq-schedule skill's default job folder, .aibl-local/schedule/aibl-hq-night-shift.
  - Agent Native Camp alumni are found from ~/GitHub/agent-native-camp holding Camp's descriptor
    (id repo.agent-native-camp). ~/context-repo and ~/.hermes, or a Camp-named folder without the
    descriptor, are only reasons to ask. Nothing found is "not_seen", never "no".
  - A Camp folder opened by mistake is reported as such.
  - The report only looks: no file in the home folder or the workbench is added, changed or removed.
  - Both apps' copies of aibl-enroll and aibl-update say the same, and say the agreed words.
"""
import json, os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
ENROLL = [ROOT / d / "skills" / "aibl-enroll" / "SKILL.md" for d in (".claude", ".agents")]
UPDATE = [ROOT / d / "skills" / "aibl-update" / "SKILL.md" for d in (".claude", ".agents")]
CAMP = {"schema_version": "aibl.repository-descriptor/v2", "id": "repo.agent-native-camp"}


def snapshot(base):
    """Every file and folder under base, with size and modification time."""
    seen = {}
    for dirpath, dirnames, filenames in os.walk(base):
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            info = full.lstat()
            seen[full.relative_to(base).as_posix()] = (info.st_size, info.st_mtime_ns, full.is_dir())
    return seen


class JoiningFrom(unittest.TestCase):
    def setUp(self):
        scratch = os.environ.get("AIBL_TEST_SCRATCH")
        if scratch:
            Path(scratch).mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch or None)
        self.home = Path(self.temp.name) / "home"
        self.wb = self.home / "GitHub" / "my-workbench"
        self.write(self.wb / ".aibl" / "template.json", "{}\n")
        self.write(self.wb / "README.md", "workbench\n")
        self.git(self.wb, "init", "-q")
        self.git(self.wb, "add", ".")
        self.git(self.wb, "commit", "-qm", "workbench")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def git(self, cwd, *args):
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
                       cwd=cwd, check=True, capture_output=True)

    def report(self, cwd=None):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "AIBL_SKIP_UPDATE_CHECK")}
        env.update({"HOME": str(self.home), "USERPROFILE": str(self.home)})
        done = subprocess.run(["node", str(HOOK), "--joining-from"], cwd=cwd or self.wb, env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def camp_clone(self, descriptor=CAMP):
        folder = self.home / "GitHub" / "agent-native-camp"
        self.write(folder / "START-HERE.md", "camp\n")
        if descriptor is not None:
            text = descriptor if isinstance(descriptor, str) else json.dumps(descriptor)
            self.write(folder / ".aibl" / "repository.json", text)
        return folder

    # --- everyone else ---------------------------------------------------------------------------

    def test_newcomer_finds_nothing_and_never_says_no(self):
        r = self.report()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["groups"], [])
        self.assertFalse(r["team_hq"]["found"])
        self.assertFalse(r["team_hq"]["night_shift"])
        self.assertEqual(r["camp"]["found"], "not_seen")
        self.assertIsNone(r["camp"]["folder"])

    def test_not_a_workbench(self):
        other = self.home / "somewhere"
        other.mkdir(parents=True)
        self.git(other, "init", "-q")
        self.assertEqual(self.report(cwd=other)["status"], "not_a_workbench")

    # --- Agent Team HQ graduates -----------------------------------------------------------------

    def test_team_hq_with_night_shift(self):
        self.write(self.wb / ".aibl" / "programs" / "agent-team-hq.json", "{}\n")
        self.write(self.wb / "team-hq" / "CONTENTS.md", "# Team HQ\n")
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.write(self.wb / ".aibl-local" / "schedule" / "aibl-hq-night-shift" / "status.txt", "OK\n")
        r = self.report()
        self.assertEqual(r["groups"], ["team_hq"])
        hq = r["team_hq"]
        self.assertTrue(hq["found"])
        self.assertTrue(hq["work_folder"])
        self.assertEqual(hq["signs"], [".aibl/programs/agent-team-hq.json", "team-hq/CONTENTS.md", "work/team-hq/"])
        self.assertTrue(hq["night_shift"])
        self.assertIn(".aibl-local/schedule/aibl-hq-night-shift/", hq["night_shift_signs"])

    def test_team_hq_without_night_shift(self):
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.write(self.wb / ".aibl-local" / "schedule" / "some-other-job" / "status.txt", "OK\n")
        hq = self.report()["team_hq"]
        self.assertTrue(hq["found"])
        self.assertFalse(hq["night_shift"])

    def test_team_hq_from_its_remote_alone(self):
        self.git(self.wb, "remote", "add", "agent-team-hq", "https://github.com/aibuild-lab/agent-team-hq.git")
        r = self.report()
        self.assertEqual(r["groups"], ["team_hq"])
        self.assertEqual(r["team_hq"]["signs"], ["remote agent-team-hq"])
        self.assertFalse(r["team_hq"]["work_folder"])

    # --- Agent Native Camp alumni ----------------------------------------------------------------

    def test_camp_clone_with_descriptor(self):
        folder = self.camp_clone()
        r = self.report()
        self.assertEqual(r["groups"], ["camp"])
        self.assertEqual(r["camp"]["found"], "yes")
        self.assertEqual(Path(r["camp"]["folder"]).resolve(), folder.resolve())

    def test_camp_named_folder_without_descriptor_asks(self):
        self.camp_clone(descriptor=None)
        r = self.report()
        self.assertEqual(r["groups"], [])
        self.assertEqual(r["camp"]["found"], "ask")
        self.assertIsNone(r["camp"]["folder"])

    def test_other_descriptor_or_unreadable_or_oversized_asks(self):
        for text in (json.dumps({"id": "repo.something-else"}), "not json", json.dumps({"id": "x", "pad": "y" * 70000})):
            with self.subTest(text=text[:20]):
                self.camp_clone(descriptor=text)
                self.assertEqual(self.report()["camp"]["found"], "ask")

    def test_weak_signs_ask(self):
        for name in ("context-repo", ".hermes"):
            with self.subTest(name=name):
                (self.home / name).mkdir(parents=True, exist_ok=True)
                r = self.report()
                self.assertEqual(r["camp"]["found"], "ask")
                self.assertIn(f"~/{name}", r["camp"]["weak_signs"])
                self.assertEqual(r["groups"], [])

    def test_camp_folder_opened_by_mistake(self):
        folder = self.camp_clone()
        self.git(folder, "init", "-q")
        r = self.report(cwd=folder)
        self.assertEqual(r["status"], "camp_folder")
        self.assertEqual(Path(r["folder"]).resolve(), folder.resolve())

    def test_both_groups(self):
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.camp_clone()
        self.assertEqual(self.report()["groups"], ["team_hq", "camp"])

    # --- it only looks ---------------------------------------------------------------------------

    def test_report_changes_nothing(self):
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.write(self.wb / ".aibl-local" / "schedule" / "aibl-hq-night-shift" / "status.txt", "OK\n")
        camp = self.camp_clone()
        self.git(camp, "init", "-q")
        (self.home / "context-repo").mkdir()
        (self.home / ".hermes").mkdir()
        # git status refreshes Git's own index file, so it runs before the snapshot, not between
        status_before = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.wb,
                                       capture_output=True, text=True).stdout
        before = snapshot(self.home)
        self.report()
        self.report(cwd=camp)
        after = snapshot(self.home)
        status_after = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.wb,
                                      capture_output=True, text=True).stdout
        self.assertEqual(status_after, status_before)
        self.assertEqual(after, before)


class Words(unittest.TestCase):
    """The words the student sees, the same in both apps."""

    def test_both_copies_match(self):
        for pair in (ENROLL, UPDATE):
            self.assertEqual(pair[0].read_text(encoding="utf-8"), pair[1].read_text(encoding="utf-8"), pair[0])

    def test_enroll_runs_the_report_and_says_the_agreed_words(self):
        text = ENROLL[0].read_text(encoding="utf-8")
        for line in (
            "node .claude/hooks/update-check.mjs --joining-from",
            "This is your Camp folder. Programs never go in here, and I haven't changed anything. Open your my-workbench folder and ask me again.",
            "I can see Agent Team HQ in this workbench. Your night shift rewrites some Team HQ files every morning, so let's save your work now and add Workforce right after.",
            "Your Team HQ work in work/team-hq/, your Team HQ lessons and your night shift stay exactly as they are.",
            "The night shift probably just ran. Let's save, then I'll carry on.",
            "Your Team HQ work in work/team-hq/ and your night shift are untouched.",
            "I can see your Camp folder. I won't touch it, and nothing from <program> goes into it. <program> goes into this workbench only, beside Camp.",
            "did you take Agent Native Camp? 1. Yes 2. No",
            "never tell the student they did not take Camp",
            "never describe how a program works in the Camp lines",
        ):
            self.assertIn(line, text)

    def test_update_offers_start_fresh_only_from_the_course_check(self):
        text = UPDATE[0].read_text(encoding="utf-8")
        self.assertIn("python3 workforce/runtime/start_fresh.py check", text)
        self.assertIn("You did a first run of the course. Want to start run two at Orientation?", text)
        self.assertIn("don't run Start fresh here", text)

    def test_no_em_dashes_in_new_words(self):
        for path in ENROLL + UPDATE:
            self.assertNotIn("—", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main()
