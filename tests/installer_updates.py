"""The installer-and-update fixes (Workforce improvement decisions 40, 41, 42, 44 and 45), template side.

- The session-start line: when the workbench's own core skills are behind, it recommends the update paste,
  not aibl-update (decision 40, WF-60). Tested on the line's own function, because the hook's template fetch
  cannot be pointed at a local fixture without changing the remote check it exists to make.
- The agent menu follows the home workbench (decision 45 A, WF-16): course copies another workbench put in
  the menu are offered once this workbench is the recorded home, and replaced only on their own yes.
- A renamed Chief's title in two shapes is reported read-only (decision 45 B, WF-58).
- The aibl-update and aibl-enroll texts carry the decided rules, the same in both app copies.

Synthetic: throwaway course, workbenches and home folder (HOME / USERPROFILE), so the real ~/.claude and
~/.aibl are never touched. No app, account or installation claim.
"""
import json, os, re, subprocess, sys, tempfile, unittest, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_list  # noqa: E402  (the program's list of its agents, built as the course builds it)

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
OFFICIAL = "https://github.com/aibuild-lab/agent-workforce.git"
CHIEF = "aibl-chief-of-staff.md"
PROFESSOR = "aibl-the-professor.md"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True,
                          capture_output=True).stdout


def commit(repo, message):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class CoreSkillsBehindLine(unittest.TestCase):
    """The hook's describe(), loaded on its own (the hook file with its main() call taken out)."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        source = HOOK.read_text(encoding="utf-8")
        assert "\nmain();\n" in source
        module = Path(cls.temp.name) / "describe.mjs"
        module.write_text(source.replace("\nmain();\n", "\n", 1) + "\nexport { describe };\n", encoding="utf-8")
        cls.module = module.as_uri()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def line(self, report):
        script = f"import {{ describe }} from {json.dumps(self.module)}; process.stdout.write(String(describe(JSON.parse(process.argv[1]))));"
        p = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(report)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def report(self, skills_changed, behind=0, missing_asks=()):
        program = {"remote": "agent-workforce", "label": "Agent Workforce", "behind": behind, "notes": ["edition"] if behind else [],
                   "team_settings": {"status": "would_add", "missing_send_asks": list(missing_asks)}}
        return {"status": "checked", "programs": [program], "skills": {"present": True, "changed": skills_changed, "error": None}}

    def test_core_skills_behind_recommends_the_update_paste(self):
        out = self.line(self.report(True, behind=3))
        self.assertIn("recommend the update paste, not aibl-update", out)
        self.assertIn("Later: update your workbench", out)
        self.assertIn("https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/UPDATE-PROMPT.md", out)
        self.assertIn("Never call a partial update recommended", out)
        self.assertNotIn("offer aibl-update", out)

    def test_core_skills_current_still_offers_aibl_update(self):
        out = self.line(self.report(False, behind=1))
        self.assertIn("offer aibl-update, which shows what changes before merging", out)
        self.assertNotIn("update paste", out)
        out = self.line(self.report(False, missing_asks=["mcp__claude_ai_Gmail__send"]))
        self.assertIn("previews the team settings", out)

    def test_nothing_waiting_says_nothing(self):
        self.assertEqual(self.line(self.report(False)), "null")


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

    def run_hook(self, wb, *args):
        args = list(args)
        if args and args[0] == "--agent-menu-apply" and "--expect" not in args:
            args += ["--expect", json.loads(self.run_hook(wb, "--agent-menu"))["preview_sha256"]]
        p = subprocess.run(["node", str(HOOK), *args], capture_output=True, text=True,
                           env=dict(self.env, CLAUDE_PROJECT_DIR=str(wb)), cwd=str(wb))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def hook_line(self, wb):
        payload = json.dumps({"source": "startup", "session_id": str(uuid.uuid4()), "cwd": str(wb)})
        p = subprocess.run(["node", str(HOOK)], input=payload, capture_output=True, text=True,
                           env=dict(self.env, CLAUDE_PROJECT_DIR=str(wb)), cwd=str(wb))
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"] if p.stdout.strip() else ""


class TheMenuFollowsTheHomeWorkbench(Base):
    """WF-16: a second workbench's enroll left 8 menu entries owned by the first, older one."""

    def setUp(self):
        super().setUp()
        self.course = self.base / "course"
        write(self.course / ".claude" / "agents" / CHIEF, b"chief v1\n")
        write(self.course / ".claude" / "agents" / PROFESSOR, b"professor\n")
        git(self.course, "init", "-q", "-b", "student")
        course_list.write(self.course)
        commit(self.course, "edition one")
        write(self.course / ".claude" / "agents" / CHIEF, b"chief v2\n")
        course_list.write(self.course)
        commit(self.course, "edition two")
        self.first = self.workbench("class-workbench-demo", b"chief v1\n")   # set up first, on edition one
        self.second = self.workbench("workforce-demo", b"chief v2\n")        # the newer one
        self.run_hook(self.first, "--agent-menu-apply")                      # the first workbench filled the menu

    def workbench(self, name, chief):
        wb = self.base / name
        write(wb / ".aibl" / "template.json", b"{}\n")
        write(wb / ".claude" / "agents" / CHIEF, chief)
        write(wb / ".claude" / "agents" / PROFESSOR, b"professor\n")
        git(wb, "init", "-q", "-b", "main")
        commit(wb, "workbench")
        git(wb, "remote", "add", "agent-workforce", OFFICIAL)
        git(wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL}", "fetch", "-q", "agent-workforce", "student")
        course_list.adopt(wb)
        commit(wb, "the course's list of its agents")
        return wb

    def placed(self):
        return json.loads((self.home / ".claude" / "aibl-agent-menu-placed.json").read_text())

    def test_before_the_move_the_other_workbench_keeps_its_copies(self):
        report = json.loads(self.run_hook(self.second, "--agent-menu"))
        self.assertFalse(report["home_workbench"])
        self.assertEqual(report["other_workbench"], [CHIEF])
        self.assertEqual(report["from_other_workbench"], [])

    def test_after_the_move_the_copies_are_offered_and_replaced_only_on_their_own_yes(self):
        self.assertEqual(json.loads(self.run_hook(self.second, "--home-workbench-apply"))["status"], "this_workbench")
        report = json.loads(self.run_hook(self.second, "--agent-menu"))
        self.assertTrue(report["home_workbench"])
        self.assertEqual(report["from_other_workbench"], [CHIEF])
        self.assertEqual(report["other_workbench"], [])
        self.assertEqual([Path(p).name for p in report["from_other_folders"]], ["class-workbench-demo"])
        self.assertEqual(report["status"], "needs_a_decision")

        line = self.hook_line(self.second)
        self.assertIn("Your agent menu is still using labels from your other workbench, **class-workbench-demo**, for 1 agent.", line)
        self.assertIn("Only the short descriptions in the menu are older.", line)
        self.assertIn("--refresh-from-home", line)

        # the ordinary apply leaves them alone
        applied = json.loads(self.run_hook(self.second, "--agent-menu-apply"))
        self.assertEqual(applied["applied"]["taken_from_other_workbench"], [])
        self.assertEqual((self.menu / CHIEF).read_bytes(), b"chief v1\n")

        # the yes to that question replaces them, keeps a backup, and moves ownership in the record
        applied = json.loads(self.run_hook(self.second, "--agent-menu-apply", "--refresh-from-home"))
        self.assertEqual(applied["applied"]["taken_from_other_workbench"], [CHIEF])
        self.assertEqual((self.menu / CHIEF).read_bytes(), b"chief v2\n")
        backups = list((self.home / ".claude" / "aibl-agent-menu-removed").rglob(CHIEF))
        self.assertEqual([b.read_bytes() for b in backups], [b"chief v1\n"])
        holders = self.placed()["agents"][CHIEF]["holders"]
        self.assertEqual([Path(h).name for h in holders], ["workforce-demo"])
        after = json.loads(self.run_hook(self.second, "--agent-menu"))
        self.assertEqual(after["status"], "in_step")

    def test_an_edited_copy_the_other_workbench_holds_is_never_taken(self):
        write(self.first / ".claude" / "agents" / CHIEF, b"chief, my own edits\n")
        write(self.menu / CHIEF, b"chief, my own edits\n")
        self.run_hook(self.second, "--home-workbench-apply")
        report = json.loads(self.run_hook(self.second, "--agent-menu"))
        self.assertEqual(report["from_other_workbench"], [])
        self.assertEqual(report["other_workbench"], [CHIEF])
        self.run_hook(self.second, "--agent-menu-apply", "--refresh-from-home")
        self.assertEqual((self.menu / CHIEF).read_bytes(), b"chief, my own edits\n")


SEAT_TABLE = b"""# Seat names

| Seat | Name | Named on | Your yes |
|---|---|---|---|
| aibl-chief-of-staff | Spyro | 2026-09-20 | Yes, call my Chief Spyro |
"""
OLD_SHAPE_MD = b"---\nname: aibl-chief-of-staff\n---\n# Spyro, your Chief of Staff\n\nHand the job to your Chief of Staff.\n"
NEW_SHAPE_MD = b"---\nname: aibl-chief-of-staff\n---\n# Chief of Staff (Spyro)\n\nHand the job to your Chief of Staff.\n"
NEW_SHAPE_TOML = b'name = "aibl-chief-of-staff"\ndeveloper_instructions = """\n# Chief of Staff (Spyro)\n\nYou are the Chief.\n"""\n'
PROFILE = b'id: aibl-chief-of-staff\ndisplay_name: "Chief of Staff (Spyro)"\n'


class ChiefTitleInTwoShapes(Base):
    """WF-58: a renamed Chief, an update combined by hand, the title left in two shapes."""

    def workbench(self, md, toml=NEW_SHAPE_TOML, table=SEAT_TABLE):
        wb = self.base / "wb"
        write(wb / ".aibl" / "template.json", b"{}\n")
        write(wb / ".claude" / "agents" / CHIEF, md)
        write(wb / ".codex" / "agents" / "aibl-chief-of-staff.toml", toml)
        write(wb / "workforce" / "profiles" / "aibl-chief-of-staff.capability-profile.yaml", PROFILE)
        if table:
            write(wb / "work" / "course" / "staff" / "seat-names.md", table)
        git(wb, "init", "-q", "-b", "main")
        commit(wb, "workbench")
        return wb

    def test_two_shapes_with_a_saved_name_lists_the_old_shape_files_to_fix(self):
        report = json.loads(self.run_hook(self.workbench(OLD_SHAPE_MD), "--seat-titles"))
        self.assertEqual(report["status"], "two_shapes")
        self.assertEqual(report["recorded_name"], "Spyro")
        self.assertEqual(report["fix"], [".claude/agents/aibl-chief-of-staff.md"])
        self.assertIn(".codex/agents/aibl-chief-of-staff.toml", report["new_shape"])

    def test_one_shape_is_quiet(self):
        report = json.loads(self.run_hook(self.workbench(NEW_SHAPE_MD), "--seat-titles"))
        self.assertEqual(report["status"], "one_shape")
        self.assertEqual(report["fix"], [])

    def test_an_older_edition_all_in_the_old_shape_is_one_shape(self):
        toml = NEW_SHAPE_TOML.replace(b"# Chief of Staff (Spyro)", b"# Spyro, your Chief of Staff")
        wb = self.workbench(OLD_SHAPE_MD, toml=toml)
        (wb / "workforce" / "profiles" / "aibl-chief-of-staff.capability-profile.yaml").write_bytes(
            b'display_name: "Spyro, your Chief of Staff"\n')
        self.assertEqual(json.loads(self.run_hook(wb, "--seat-titles"))["status"], "one_shape")

    def test_no_saved_name_never_guesses(self):
        report = json.loads(self.run_hook(self.workbench(OLD_SHAPE_MD, table=None), "--seat-titles"))
        self.assertEqual(report["status"], "two_shapes_no_record")
        self.assertIsNone(report["recorded_name"])
        self.assertEqual(report["fix"], [])

    def test_prose_about_the_chief_is_not_a_title(self):
        md = NEW_SHAPE_MD + b"I'm handing it to your Chief of Staff. Spyro, your Chief of Staff, will reply.\n"
        self.assertEqual(json.loads(self.run_hook(self.workbench(md), "--seat-titles"))["status"], "one_shape")


def skill(name, app=".claude"):
    return (ROOT / app / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def flat(text):
    return re.sub(r"\s+", " ", text)


class SkillTexts(unittest.TestCase):
    UPDATE = flat(skill("aibl-update"))
    ENROLL = flat(skill("aibl-enroll"))

    def test_both_app_copies_match(self):
        for name in ("aibl-update", "aibl-enroll", "aibl-checkpoint", "aibl-personalize"):
            with self.subTest(name=name):
                self.assertEqual(skill(name), skill(name, ".agents"))

    def test_unsaved_lesson_work_is_offered_a_save_and_only_course_folders_stop(self):
        # decision 40 (WF-6)
        self.assertIn("Save it now and continue the update? (yes / no)", self.UPDATE)
        self.assertIn("Save it now and continue? (yes / no)", self.ENROLL)
        self.assertIn("can stay unsaved and is never touched", self.ENROLL)
        self.assertIn("git diff --cached --name-only", self.ENROLL)
        self.assertNotIn("any output stops for the student to checkpoint", self.ENROLL)
        self.assertNotIn("must be empty. Otherwise stop for `aibl-checkpoint`", self.UPDATE)
        self.assertIn('git commit -m "Update workbench skills from the template" -- <paths>', self.UPDATE)

    def test_a_partial_update_is_never_recommended(self):
        # decision 40 (WF-60)
        self.assertIn("**Never call a partial update recommended.**", self.UPDATE)
        self.assertIn("The safe default, and your recommendation, is to hold off", self.UPDATE)
        self.assertNotRegex(self.UPDATE, r"skip the \d+ \(Recommended\)")

    def test_the_recorder_refresh_is_ask_first_and_never_installs(self):
        # decision 41 (WF-63)
        self.assertIn("~/.claude/observability/workforce-langfuse.json", self.UPDATE)
        self.assertIn("install_claude_langfuse.py --check", self.UPDATE)
        self.assertIn("install_codex_langfuse.py --check", self.UPDATE)
        self.assertIn("your Langfuse recorder", self.UPDATE)
        self.assertIn('"sdk_current": false', self.UPDATE)
        self.assertIn("which an update never does", self.UPDATE)
        self.assertIn("the course's own Langfuse recorder when it is already set up", self.UPDATE)

    def test_the_app_stop_messages_come_before_the_save_and_the_scripts(self):
        # decision 42 (WF-56, WF-7)
        for words in ("'Yes, save the course update now.'", "**Auto** to **Accept edits**", "**Allow once**",
                      "**Approve for me** to **Ask for approval**", "prompt injection", "Never hand the student the command instead."):
            with self.subTest(words=words):
                self.assertIn(words, self.UPDATE)
        self.assertIn("give the save message", self.ENROLL)

    def test_a_voice_line_moves_to_the_students_own_record(self):
        # decision 44 (WF-74), update safety
        for words in ("A line the student added to an agent's Voice section", "`work/course/staff/founder-brief.md`",
                      "`work/course/staff/communication-profile.md`", "1. Move my line and take the course's version (recommended)",
                      "Both files under `work/` are the Chief of Staff's to save, never yours",
                      "Never join the student's line to the program's file by hand."):
            with self.subTest(words=words):
                self.assertIn(words, self.UPDATE)

    def test_the_agent_file_conflict_question_is_plain_with_keep_mine_recommended(self):
        # decision 45 C
        self.assertIn("You've changed your **<Writer>** since you got it, and the course has also updated it. "
                      "**My recommendation: keep yours,**", self.UPDATE)
        self.assertIn("1. Keep mine (recommended) 2. Take the course's version (your changes will be replaced) "
                      "3. Show me both side by side", self.UPDATE)

    def test_home_move_and_two_shapes_are_offered(self):
        # decision 45 A and B
        self.assertIn("**The menu follows the home workbench.**", self.UPDATE)
        self.assertIn("--refresh-from-home", self.UPDATE)
        self.assertIn("--refresh-from-home", self.ENROLL)
        self.assertIn("update-check.mjs --seat-titles", self.UPDATE)
        self.assertIn("Fix it now? (yes / no)", self.UPDATE)
        self.assertIn("never guess one", self.UPDATE)

    def test_no_em_dashes(self):
        for name in ("aibl-update", "aibl-enroll"):
            self.assertNotIn("—", skill(name))


if __name__ == "__main__":
    unittest.main()
