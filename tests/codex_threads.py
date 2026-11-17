"""aibl-update gives every Codex student the course's agent thread setting, one key and nothing else (11-16-2026).

Codex runs at most 4 agent threads at once in a session unless the workbench's own `.codex/config.toml`
raises it (measured on Codex 0.167.1). Agent Workforce sets its number in
`workforce/house/.codex/config.toml`; before this, a workbench got it only through an optional config
sync. `update-check.mjs --codex-threads` reports, and `--codex-threads-apply` adds just
`[agents] max_concurrent_threads_per_session` with the course's value: a new file when there is none,
under an existing `[agents]` header, or as a new `[agents]` table at the end. Every other byte stays,
any thread ceiling already there is the student's and is left alone, a second run changes nothing, and
a file it can't place the key in safely is left alone with a reason. Each written file must parse as
TOML to the same keys as before plus the one key.
"""
import os, subprocess, sys, tempfile, tomllib, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "update-check.mjs"
COURSE = """# .codex/config.toml for the workbench: defaults and connector prompts.
[agents]
# 32 is a starting number. The owner can change it with their agent.
max_concurrent_threads_per_session = 32

[apps.gmail.tools.gmail_send_email]
approval_mode = "prompt"
"""
SKILLS = [ROOT / app / "skills" / "aibl-update" / "SKILL.md" for app in (".claude", ".agents")]


class CodexThreads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.wb = base / "wb"
        (self.wb / ".aibl").mkdir(parents=True)
        (self.wb / ".aibl" / "template.json").write_text("{}\n")
        (self.wb / "workforce" / "house" / ".codex").mkdir(parents=True)
        (self.wb / "workforce" / "house" / ".codex" / "config.toml").write_text(COURSE)
        self.env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        self.env.update(HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=str(base / "gitconfig"))
        subprocess.run(["git", "init", "-q"], cwd=self.wb, env=self.env, check=True)
        self.config = self.wb / ".codex" / "config.toml"

    def run_hook(self, flag):
        import json
        p = subprocess.run(["node", str(HOOK), flag], cwd=self.wb, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def put(self, data: bytes):
        self.config.parent.mkdir(exist_ok=True)
        self.config.write_bytes(data)

    def parsed(self):
        return tomllib.loads(self.config.read_bytes().decode("utf-8").lstrip("﻿"))

    def apply_twice(self):
        first = self.run_hook("--codex-threads-apply")
        after = self.config.read_bytes()
        second = self.run_hook("--codex-threads-apply")
        self.assertEqual(second["status"], "already_set")
        self.assertFalse(second["applied"])
        self.assertEqual(self.config.read_bytes(), after, "a second run changes nothing")
        return first, after

    # The three cases the PM named

    def test_absent_file_gets_a_new_file_with_only_the_key(self):
        self.assertEqual(self.run_hook("--codex-threads")["status"], "missing")
        first, _ = self.apply_twice()
        self.assertEqual(first["status"], "already_set")
        self.assertTrue(first["applied"])
        self.assertTrue(first["new_file"])
        self.assertEqual(self.parsed(), {"agents": {"max_concurrent_threads_per_session": 32}})

    def test_file_with_other_keys_keeps_every_byte_and_gains_the_table(self):
        old = (b'model = "gpt-5"\n# my note\n[apps.slack.tools.slack_send_message]\napproval_mode = "prompt"\n'
               b'[agents.reviewer]\ndescription = "mine"\n')
        self.put(old)
        before = self.parsed()
        self.assertEqual(self.run_hook("--codex-threads")["adds_to"], "new_agents_table")
        first, after = self.apply_twice()
        self.assertTrue(first["applied"])
        self.assertFalse(first["new_file"])
        self.assertTrue(after.startswith(old), "the student's bytes come first, unchanged")
        want = dict(before)
        want["agents"] = {**before["agents"], "max_concurrent_threads_per_session": 32}
        self.assertEqual(self.parsed(), want)

    def test_key_already_present_is_the_students_choice(self):
        for line in (b"[agents]\nmax_concurrent_threads_per_session = 8\n",
                     b"[agents]\nmax_threads = 6 # older name\n",
                     b"agents.max_concurrent_threads_per_session = 12\n",
                     b"[features.multi_agent_v2]\nmax_concurrent_threads_per_session = 10\n"):
            with self.subTest(line=line):
                self.put(line + b"[apps.gmail]\nx = 1\n")
                report = self.run_hook("--codex-threads")
                self.assertEqual(report["status"], "already_set", report)
                self.assertFalse(self.run_hook("--codex-threads-apply")["applied"])
                self.assertEqual(self.config.read_bytes(), line + b"[apps.gmail]\nx = 1\n")

    def test_the_key_inside_another_table_is_not_the_setting(self):
        self.put(b"[apps.gmail]\nagents.max_concurrent_threads_per_session = 12\n")
        self.apply_twice()
        self.assertEqual(self.parsed()["agents"], {"max_concurrent_threads_per_session": 32})

    # Shapes that keep the merge honest

    def test_existing_agents_table_gets_the_key_under_its_header(self):
        old = b"[agents]\n# mine\nsome_other = true\n\n[apps.gmail]\nx = 1\n"
        self.put(old)
        self.assertEqual(self.run_hook("--codex-threads")["adds_to"], "agents_table")
        self.apply_twice()
        self.assertEqual(self.config.read_bytes(),
                         b"[agents]\nmax_concurrent_threads_per_session = 32\n# mine\nsome_other = true\n\n[apps.gmail]\nx = 1\n")
        self.assertEqual(self.parsed()["agents"], {"some_other": True, "max_concurrent_threads_per_session": 32})

    def test_windows_line_endings_and_a_bom_are_kept(self):
        self.put(b"\xef\xbb\xbfmodel = \"gpt-5\"\r\n[apps.gmail]\r\nx = 1\r\n")
        self.apply_twice()
        data = self.config.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbfmodel"))
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "no bare LF in a CRLF file")
        self.assertEqual(self.parsed()["agents"], {"max_concurrent_threads_per_session": 32})

    def test_no_final_newline_and_header_on_the_last_line(self):
        self.put(b"[agents]")
        self.apply_twice()
        self.assertEqual(self.config.read_bytes(), b"[agents]\nmax_concurrent_threads_per_session = 32\n")
        self.put(b'model = "x"')
        self.apply_twice()
        self.assertEqual(self.parsed(), {"model": "x", "agents": {"max_concurrent_threads_per_session": 32}})

    def test_a_header_inside_a_multiline_string_is_not_a_header(self):
        self.put(b'note = """\n[agents]\nmax_threads = 2\n"""\n')
        self.assertEqual(self.run_hook("--codex-threads")["adds_to"], "new_agents_table")
        self.apply_twice()
        self.assertEqual(self.parsed()["agents"], {"max_concurrent_threads_per_session": 32})
        self.assertIn("[agents]\nmax_threads = 2", self.parsed()["note"])

    def test_agents_defined_another_way_is_left_alone(self):
        for old in (b"agents.reviewer.description = \"mine\"\n", b"agents = { max_depth = 2 }\n", b"[[agents]]\nname = \"x\"\n"):
            with self.subTest(old=old):
                self.put(old)
                report = self.run_hook("--codex-threads-apply")
                self.assertEqual(report["status"], "left_alone", report)
                self.assertFalse(report["applied"])
                self.assertEqual(self.config.read_bytes(), old)

    def test_the_value_comes_from_the_course_file(self):
        (self.wb / "workforce" / "house" / ".codex" / "config.toml").write_text(COURSE.replace("= 32", "= 24"))
        self.run_hook("--codex-threads-apply")
        self.assertEqual(self.parsed()["agents"]["max_concurrent_threads_per_session"], 24)

    def test_no_course_setting_writes_nothing(self):
        (self.wb / "workforce" / "house" / ".codex" / "config.toml").unlink()
        report = self.run_hook("--codex-threads-apply")
        self.assertEqual(report["status"], "no_course_setting")
        self.assertFalse(self.config.exists())

    @unittest.skipIf(sys.platform == "win32", "making a link needs extra rights on Windows")
    def test_a_link_is_never_written_through(self):
        target = Path(self.tmp.name) / "elsewhere.toml"
        target.write_bytes(b"x = 1\n")
        self.config.parent.mkdir(exist_ok=True)
        self.config.symlink_to(target)
        report = self.run_hook("--codex-threads-apply")
        self.assertEqual((report["status"], report.get("reason")), ("left_alone", "link"))
        self.assertEqual(target.read_bytes(), b"x = 1\n")


class SkillRunsIt(unittest.TestCase):
    def setUp(self):
        texts = [p.read_text(encoding="utf-8") for p in SKILLS]
        self.assertEqual(texts[0], texts[1])
        self.text = texts[0]

    def test_step_6_5_previews_then_applies_and_saves(self):
        for phrase in ["`node .claude/hooks/update-check.mjs --codex-threads`",
                       "`node .claude/hooks/update-check.mjs --codex-threads-apply`",
                       "`git commit -m \"Let Codex run more of your agents at once\" -- .codex/config.toml`",
                       "never another key"]:
            self.assertIn(phrase, self.text)

    def test_trust_line_is_one_line_and_not_a_blocker(self):
        self.assertIn("Codex uses this setting only in a folder you trust", self.text)
        self.assertIn("never a blocker", self.text)


if __name__ == "__main__":
    unittest.main()
