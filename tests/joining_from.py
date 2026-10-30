"""Where the student is joining from: `update-check.mjs --joining-from` and the words aibl-enroll
and aibl-update say with it.

Synthetic only: every test builds a throwaway home folder (HOME and USERPROFILE) and a throwaway
workbench inside it, so the real home folder, the real ~/GitHub and any real Camp or Team HQ setup
are never read. Set AIBL_TEST_SCRATCH to a folder to keep the throwaway folders there while they
exist (they are removed after each test either way). No network, no app, no account.

What it pins:
  - Agent Team HQ graduates are found from the program's stamp, its folders or its remote, and the
    night shift from the hq-schedule skill's default job folder, .aibl-local/schedule/aibl-hq-night-shift.
  - Agent Native Camp alumni are found from Camp's clone (at ~/GitHub, or a few fixed other places)
    holding Camp's descriptor (id repo.agent-native-camp) or a remote naming Camp or a private Camp
    mirror in its own .git/config, or from ~/context-repo holding Camp's marker. A Camp-named folder
    without either mark, ~/context-repo without the marker, and ~/Documents/Agent-Native-Camp are
    only reasons to ask. ~/.hermes is not a sign. Nothing found is "not_seen", never "no".
  - The layouts the Agent Native OS workshop installer and Camp leave on a camper's Mac or Windows
    computer, and on a workshop alum, Team HQ graduate or Essentials student who never took Camp.
  - A Camp folder (the clone or ~/context-repo) opened by mistake is reported as such.
  - The Camp question is asked at most once, ever: camp.next is "say", "ask" or "none", and
    ~/.aibl/camp.json (written by --camp-record, or by the installer's hub_setup.py in the same
    shape) turns it to "none" for good. A strong sign never asks.
  - The report only looks: no file in the home folder or the workbench is added, changed or removed.
  - Both apps' copies of aibl-enroll and aibl-update say the same, and say the agreed words.
"""
import json, os, shutil, stat, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
ENROLL = [ROOT / d / "skills" / "aibl-enroll" / "SKILL.md" for d in (".claude", ".agents")]
UPDATE = [ROOT / d / "skills" / "aibl-update" / "SKILL.md" for d in (".claude", ".agents")]
CAMP = {"schema_version": "aibl.repository-descriptor/v2", "id": "repo.agent-native-camp"}
CAMP_URL = "https://github.com/aibuild-lab/agent-native-camp.git"
MIRROR_URL = "https://github.com/camper-example/agent-native-camp-private.git"


def rmtree(folder):
    # Git marks its object files read only, which Windows refuses to delete
    def writable(func, path, _info):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(folder, onexc=writable)
    else:
        shutil.rmtree(folder, onerror=writable)


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

    def camp_clone(self, descriptor=CAMP, where=("GitHub", "agent-native-camp"), remotes=None):
        folder = self.home.joinpath(*where)
        self.write(folder / "START-HERE.md", "camp\n")
        self.write(folder / "weeks" / "week-01" / "README.md", "week 1\n")
        if descriptor is not None:
            text = descriptor if isinstance(descriptor, str) else json.dumps(descriptor)
            self.write(folder / ".aibl" / "repository.json", text)
        if remotes:
            self.git(folder, "init", "-q")
            for name, url in remotes.items():
                self.git(folder, "remote", "add", name, url)
        return folder

    def record(self, answer):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "AIBL_SKIP_UPDATE_CHECK")}
        env.update({"HOME": str(self.home), "USERPROFILE": str(self.home)})
        done = subprocess.run(["node", str(HOOK), "--camp-record", answer], cwd=self.wb, env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def installer_record(self, **fields):
        """The record the installer's hub_setup.py writes after it said its Camp line."""
        record = {"schema": "aibl.camp-answer/v1", "took_camp": True, "told": True, "by": "aibl-installer",
                  "recorded_at": "2026-10-30T12:00:00+00:00", **fields}
        self.write(self.home / ".aibl" / "camp.json", json.dumps(record))

    def workshop_installer_layout(self):
        """What the Agent Native OS workshop installer leaves, Camp or not: ~/GitHub/agent-native-os
        (private origin, AI Build Lab upstream, .aibl/ safety files), its own clone, its state file
        and the app's safety guard."""
        os_repo = self.home / "GitHub" / "agent-native-os"
        self.write(os_repo / "CLAUDE.md", "workshop\n")
        self.write(os_repo / ".aibl" / "repo-state.md", "# AI Build Lab Repo State\n")
        self.write(os_repo / ".aibl" / "workshop-profile.json", "{}\n")
        self.git(os_repo, "init", "-q")
        self.git(os_repo, "remote", "add", "origin", "https://github.com/camper-example/agent-native-os-private.git")
        self.git(os_repo, "remote", "add", "upstream", "https://github.com/aibuild-lab/agent-native-os.git")
        inst = self.home / "GitHub" / "workshop-installer"
        self.write(inst / ".aibl" / "repository.json", json.dumps({"id": "repo.workshop-installer"}))
        self.write(self.home / ".aibl" / "workshop-installer" / "state.json", "{}\n")
        self.write(self.home / ".claude" / "hooks" / "secrets-guard.js", "// guard\n")

    def context_repo(self, marker=True):
        folder = self.home / "context-repo"
        self.write(folder / "about-me" / "facts.md", "facts\n")
        if marker:
            self.write(folder / ".camp-context-repo", "camp-context-repo-schema=1\n")
        return folder

    def week1_folder(self, *parent):
        self.write(self.home.joinpath(*(parent or ("Documents",)), "Agent-Native-Camp", "week-01-friction-log.md"), "log\n")

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
        for name in ("context-repo", "Documents/Agent-Native-Camp", "OneDrive/Documents/Agent-Native-Camp"):
            with self.subTest(name=name):
                (self.home / name).mkdir(parents=True, exist_ok=True)
                r = self.report()
                self.assertEqual(r["camp"]["found"], "ask")
                self.assertIn(f"~/{name}", r["camp"]["weak_signs"])
                self.assertEqual(r["groups"], [])

    def test_hermes_alone_is_not_a_sign(self):
        (self.home / ".hermes").mkdir(parents=True)
        r = self.report()
        self.assertEqual(r["camp"]["found"], "not_seen")
        self.assertEqual(r["camp"]["weak_signs"], [])

    def test_camp_remote_without_descriptor(self):
        for remotes in ({"origin": CAMP_URL},
                        {"origin": MIRROR_URL, "upstream": CAMP_URL},
                        {"origin": "git@github.com:camper-example/agent-native-camp-private.git"},
                        {"upstream": "ssh://git@github.com/aibuild-lab/agent-native-camp"}):
            with self.subTest(remotes=remotes):
                folder = self.camp_clone(descriptor=None, remotes=remotes)
                try:
                    r = self.report()
                    self.assertEqual(r["camp"]["found"], "yes")
                    self.assertEqual(r["groups"], ["camp"])
                    self.assertEqual(Path(r["camp"]["folder"]).resolve(), folder.resolve())
                    self.assertEqual(r["camp"]["signs"], ["~/GitHub/agent-native-camp with a Camp remote"])
                finally:
                    rmtree(folder)

    def test_lookalike_remotes_are_not_camp(self):
        for url in ("https://github.com/aibuild-lab/agent-native-camp-hq.git",
                    "https://github.com/aibuild-lab/agent-native-os.git",
                    "https://example.com/aibuild-lab/agent-native-camp.git"):
            with self.subTest(url=url):
                folder = self.camp_clone(descriptor=None, remotes={"origin": url})
                try:
                    self.assertEqual(self.report()["camp"]["found"], "ask")
                finally:
                    rmtree(folder)

    def test_context_repo_marker_is_enough(self):
        self.context_repo()
        r = self.report()
        self.assertEqual(r["camp"]["found"], "yes")
        self.assertEqual(r["groups"], ["camp"])
        self.assertIsNone(r["camp"]["folder"])
        self.assertEqual(r["camp"]["signs"], ["~/context-repo with Camp's marker"])

    def test_wrong_marker_text_only_asks(self):
        folder = self.context_repo(marker=False)
        self.write(folder / ".camp-context-repo", "something else\n")
        self.assertEqual(self.report()["camp"]["found"], "ask")

    def test_context_repo_opened_by_mistake(self):
        folder = self.context_repo()
        self.git(folder, "init", "-q")
        r = self.report(cwd=folder)
        self.assertEqual(r["status"], "camp_folder")

    def test_pre_descriptor_camp_clone_opened_by_mistake(self):
        folder = self.camp_clone(descriptor=None, remotes={"origin": MIRROR_URL, "upstream": CAMP_URL})
        self.assertEqual(self.report(cwd=folder)["status"], "camp_folder")

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

    # --- layouts from the Agent Native OS workshop installer and Camp ---------------------------
    # Mac and Windows share these paths under the home folder (Windows: %USERPROFILE%), except
    # where Windows keeps Documents and Desktop in OneDrive.

    def found(self):
        r = self.report()
        self.assertEqual(r["status"], "ok")
        self.assertNotIn("github.com", json.dumps(r))
        return r["camp"]["found"], r["groups"]

    # people who never took Camp: nothing may change for them
    def test_workshop_alum_who_never_took_camp(self):
        self.workshop_installer_layout()
        (self.home / ".hermes").mkdir()  # the workshop teaches a local Hermes here
        self.assertEqual(self.found(), ("not_seen", []))

    def test_team_hq_graduate_from_the_workshop(self):
        self.workshop_installer_layout()
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.assertEqual(self.found(), ("not_seen", ["team_hq"]))

    def test_essentials_only(self):
        self.assertEqual(self.found(), ("not_seen", []))

    # campers
    def test_camper_current_clone(self):
        self.workshop_installer_layout()
        self.camp_clone(remotes={"origin": MIRROR_URL, "upstream": CAMP_URL})
        self.context_repo()
        self.week1_folder()
        self.assertEqual(self.found(), ("yes", ["camp"]))

    def test_camper_clone_from_before_the_descriptor(self):
        self.workshop_installer_layout()
        self.camp_clone(descriptor=None, remotes={"origin": MIRROR_URL, "upstream": CAMP_URL})
        self.assertEqual(self.found(), ("yes", ["camp"]))

    def test_camper_legacy_direct_clone(self):
        self.workshop_installer_layout()
        self.camp_clone(descriptor=None, remotes={"origin": CAMP_URL})
        self.assertEqual(self.found(), ("yes", ["camp"]))

    def test_camper_clone_somewhere_else(self):
        for where in (("Documents", "GitHub", "agent-native-camp"), ("Desktop", "agent-native-camp"),
                      ("agent-native-camp",), ("GitHub", "agent-native-camp-private"),
                      ("OneDrive", "Documents", "agent-native-camp"), ("OneDrive", "Desktop", "agent-native-camp")):
            with self.subTest(where=where):
                folder = self.camp_clone(descriptor=None, where=where, remotes={"origin": MIRROR_URL, "upstream": CAMP_URL})
                try:
                    r = self.report()
                    self.assertEqual((r["camp"]["found"], r["groups"]), ("yes", ["camp"]))
                    self.assertEqual(Path(r["camp"]["folder"]).resolve(), folder.resolve())
                finally:
                    rmtree(folder)

    def test_camper_with_only_context_repo(self):
        # the Camp clone was moved off this computer; Week 2's context-repo is still here
        self.workshop_installer_layout()
        self.context_repo()
        self.assertEqual(self.found(), ("yes", ["camp"]))

    def test_camper_who_stopped_after_week_one_on_a_mac(self):
        self.workshop_installer_layout()
        self.week1_folder()
        self.assertEqual(self.found(), ("ask", []))

    def test_camper_who_stopped_after_week_one_on_windows_onedrive(self):
        self.workshop_installer_layout()
        self.week1_folder("OneDrive", "Documents")
        self.assertEqual(self.found(), ("ask", []))

    def test_camper_with_everything_on_a_server(self):
        # nothing of Camp's on this computer: finding nothing proves nothing, and says nothing
        self.workshop_installer_layout()
        self.assertEqual(self.found(), ("not_seen", []))
    # --- the Camp question, at most once, ever --------------------------------------------------

    def test_strong_sign_says_once_and_never_asks(self):
        self.camp_clone()
        self.assertEqual(self.report()["camp"]["next"], "say")
        r = self.record("yes")
        self.assertTrue(r["applied"])
        saved = json.loads((self.home / ".aibl" / "camp.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["schema"], saved["took_camp"], saved["told"], saved["by"]),
                         ("aibl.camp-answer/v1", True, True, "aibl-enroll"))
        for _ in range(2):  # a second enroll, a third
            self.assertEqual(self.report()["camp"]["next"], "none")

    def test_weak_sign_asks_once_whatever_the_answer(self):
        self.context_repo(marker=False)
        for answer in ("no", "yes"):
            with self.subTest(answer=answer):
                (self.home / ".aibl" / "camp.json").unlink(missing_ok=True)
                self.assertEqual(self.report()["camp"]["next"], "ask")
                self.assertTrue(self.record(answer)["applied"])
                self.assertEqual(self.report()["camp"]["next"], "none")
                self.assertEqual(self.report()["camp"]["record"]["took_camp"], answer == "yes")

    def test_installer_said_it_so_enroll_says_nothing(self):
        self.installer_record()
        for layout in (self.camp_clone, lambda: self.context_repo(marker=False), self.week1_folder):
            layout()
            self.assertEqual(self.report()["camp"]["next"], "none")

    def test_said_no_then_a_strong_sign_says_the_line_but_never_asks(self):
        self.context_repo(marker=False)
        self.record("no")
        self.assertEqual(self.report()["camp"]["next"], "none")
        self.camp_clone()
        self.assertEqual(self.report()["camp"]["next"], "say")

    def test_broken_record_counts_as_answered(self):
        self.context_repo(marker=False)
        for text in ("not json", json.dumps({"schema": "other", "took_camp": True})):
            with self.subTest(text=text):
                self.write(self.home / ".aibl" / "camp.json", text)
                self.assertEqual(self.report()["camp"]["next"], "none")

    def test_no_sign_says_nothing_and_writes_nothing(self):
        r = self.report()["camp"]
        self.assertEqual((r["found"], r["next"], r["record"]), ("not_seen", "none", None))
        self.assertFalse((self.home / ".aibl" / "camp.json").exists())

    def test_record_takes_only_yes_or_no(self):
        for answer in ("maybe", ""):
            r = self.record(answer) if answer else self.record("--json")
            self.assertFalse(r["applied"])
        self.assertFalse((self.home / ".aibl" / "camp.json").exists())

    # --- it only looks ---------------------------------------------------------------------------

    def test_report_changes_nothing(self):
        self.write(self.wb / "work" / "team-hq" / "north-star.md", "mine\n")
        self.write(self.wb / ".aibl-local" / "schedule" / "aibl-hq-night-shift" / "status.txt", "OK\n")
        self.workshop_installer_layout()
        camp = self.camp_clone(remotes={"origin": MIRROR_URL, "upstream": CAMP_URL})
        self.camp_clone(descriptor=None, where=("Desktop", "agent-native-camp"))
        self.context_repo()
        self.week1_folder()
        (self.home / ".hermes").mkdir()
        # git status refreshes Git's own index file, so it runs before the snapshot, not between
        status_before = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=self.wb,
                                       capture_output=True, text=True).stdout
        before = snapshot(self.home)
        self.report()
        self.report(cwd=camp)
        self.report(cwd=self.home / "context-repo")
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
            "read `camp.next`, never `camp.found`, so the Camp question is asked at most once, ever",
            "node .claude/hooks/update-check.mjs --camp-record yes",
            "node .claude/hooks/update-check.mjs --camp-record no",
            "never retry it or ask the question again",
        ):
            self.assertIn(line, text)

    def test_update_asks_a_returning_student_once_from_the_course_check(self):
        # Wade, 10-30: one question, asked once, ever, only for returning_v1; the answer is saved
        # in the course's run file so no update, lesson or agent asks again.
        for path in UPDATE:
            text = path.read_text(encoding="utf-8")
            self.assertIn("python3 workforce/runtime/start_fresh.py check", text)
            self.assertIn("Ask only when its `state` is `returning_v1`", text)
            self.assertIn(
                "\"One question, and I'll only ask it once. This update brings the new version of Agent Workforce, "
                "and the course has changed a lot since your first run: new lessons, in a new order, with new pages "
                "on Learn. Would you like to take it from the beginning? Your first run is saved in a dated folder "
                "first, and nothing is deleted. Or keep going as you are; that's fine too, and the lessons you open "
                "from here on will be the new version either way. "
                "1. Yes, start from the beginning 2. No, keep going as I am\"", text)
            self.assertIn("python3 workforce/runtime/start_fresh.py answer yes --via update", text)
            self.assertIn("python3 workforce/runtime/start_fresh.py answer not-now --via update", text)
            self.assertIn("any answer that is not a clear yes", text)
            self.assertIn("don't run Start fresh here", text)
            self.assertIn("Never bring it up again in this update.", text)
            self.assertNotIn("`ready` or `unsaved_work`", text)
            self.assertNotIn("You did a first run of the course.", text)

    def test_no_em_dashes_in_new_words(self):
        for path in ENROLL + UPDATE:
            self.assertNotIn("—", path.read_text(encoding="utf-8"), path)


if __name__ == "__main__":
    unittest.main()
