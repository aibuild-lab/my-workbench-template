"""Week 4 robot runs (A6, 11-27-2026): five honesty fixes to aibl-update.

1. Codex reported "The Professor answered: "I'm the Professor."" after reading the agent's file; no agent was started.
   Step 6.5 now says only a reply from an agent started in this run counts, quoted word for word; reading the file
   never counts; if no agent can be started, say so plainly and never say it answered.
2. The Codex threads setting applied with no question and the preview never mentioned it (and Claude Code's auto mode
   refused it as unasked). The course update's preview now lists it as one plain change; the main yes covers it.
3. The team note copied the whole rendered AGENTS.md over the student's file. A fixed line now replaces only the
   house:begin ... house:end block (or adds it at the end when missing), in update and in enroll.
4. The agent wrote working lists under runs/ before the student's first yes. The update keeps its notes in the
   conversation and writes nothing before the first yes except what the preview needs.
5. The preview named four of the six agents the update changed. It now names every one.

Text checks on both copies, and the splice line run on real files (directly, and in Git Bash on Windows).
"""
import os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_git_bash_paths import git_bash  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def skill(name):
    a, b = [(ROOT / app / "skills" / name / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b, f"the Claude and Codex copies of {name} must be identical"
    return a


def step(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def splice_line(name):
    # per line: the update's code fences (```) would shift a whole-file backtick pairing
    return next(s for line in skill(name).splitlines() for s in re.findall(r"`([^`]+)`", line)
                if "open('.aibl-local/house/AGENTS.md.rendered'" in s)


class Honesty(unittest.TestCase):
    def setUp(self):
        self.text = skill("aibl-update")
        self.rules = self.text[self.text.index("## Rules"):]

    def test_1_a_reply_only_from_an_agent_started_in_this_run(self):
        s = step(self.text, "Then prove one agent answers", "**Keep Claude Code's agent menu")
        self.assertNotIn("A file that parses is not proof; a reply is.", s)
        self.assertIn("Then prove one agent answers, by starting it.", s)
        self.assertIn("in Claude Code, the Agent tool with the agent's name; in Codex, a sub-agent started as that agent", s)
        self.assertIn("quoting its reply word for word", s)
        self.assertIn("Only a reply from an agent you started in this run is proof.", s)
        self.assertIn("Reading the agent's file, parsing it or quoting its lines never counts", s)
        self.assertIn("never say an agent answered, replied or was called unless you started it here and it replied", s)
        self.assertIn("If you can't start an agent from this conversation", s)
        self.assertIn("don't read its file instead: say plainly, in one line, that you couldn't start one from here", s)
        self.assertIn("If an agent you started gives no reply or an error, say so and stop", s)

    def test_2_codex_threads_setting_is_in_the_preview(self):
        how = next(l for l in self.text.splitlines() if l.startswith("- **The course update:**"))
        self.assertIn('"It also lets Codex run more of your agents at once in this workbench.', how)
        self.assertIn("list it as one plain change of its own, in both apps", how)
        self.assertIn("The student's yes to this question covers it: it gets no question of its own.", how)
        s = step(self.text, "**Let Codex run more of the team at once", "Then prove one agent answers")
        self.assertIn("(Agent Workforce only, in both apps, on the course update's yes)", s)
        self.assertNotIn("Ask no question about it.", s)
        self.assertNotIn("no question).**", s)
        self.assertIn("Decide before that preview whether it goes in", s)
        self.assertIn("`git ls-tree --name-only <remote>/student -- workforce/house/.codex/config.toml`", s)
        self.assertIn("apply it only when the preview listed it and the student said yes to that preview", s)
        self.assertIn("when it wasn't listed (including an update with no course update to preview), skip it and say nothing", s)
        self.assertLess(s.index("Decide before that preview"), s.index("`node .claude/hooks/update-check.mjs --codex-threads-apply`"))
        self.assertIn("stayed as it was", s)

    def test_3_house_block_only(self):
        for name in ("aibl-update", "aibl-enroll"):
            t = skill(name)
            self.assertNotIn("copyfile('.aibl-local/house/AGENTS.md.rendered', 'AGENTS.md')", t, name)
            self.assertIn("Never copy the whole rendered `AGENTS.md` over the student's file.", t, name)
            self.assertIn("replaces only the lines from its `house:begin` line through its `house:end` line", t, name)
        self.assertEqual(splice_line("aibl-update"), splice_line("aibl-enroll"))
        line = splice_line("aibl-update")
        self.assertTrue(line.startswith('python3 -c "') and line.endswith('"'))
        for bad in ("$", "`", '"'):
            self.assertNotIn(bad, line[len('python3 -c "'):-1], f"{bad!r} breaks the line in Bash or PowerShell")

    def test_4_no_working_notes_in_files_before_the_first_yes(self):
        self.assertIn("- **No working notes in files, and nothing written before the first yes.**", self.rules)
        self.assertIn("not under `runs/` (even when you run as an agent whose own instructions keep job notes there)", self.rules)
        self.assertIn("Before the student's first yes in this update, the only writes are the ones the preview needs", self.rules)
        step1 = next(l for l in self.text.splitlines() if l.startswith("1. **Check location and work."))
        self.assertIn("Keep this update's working lists and notes in the conversation too, never in a file", step1)

    def test_5_preview_names_every_agent(self):
        how = next(l for l in self.text.splitlines() if l.startswith("- **The course update:**"))
        self.assertIn("Name every agent whose files this update adds, changes or retires", how)
        self.assertIn('never a few of them, and never "and others"', how)
        step5 = next(l for l in self.text.splitlines() if l.startswith("5. **Explain the program changes."))
        self.assertIn("**Every agent this update touches.**", step5)
        self.assertIn("`.claude/agents/` or `.codex/agents/`", step5)
        self.assertIn("One agent counts once, however many of its files change", step5)
        self.assertIn("The preview names all of them.", step5)

    def test_no_dashes(self):
        for name in ("aibl-update", "aibl-enroll"):
            self.assertNotIn("—", skill(name))
            self.assertNotIn("–", skill(name))


class SpliceRuns(unittest.TestCase):
    """The fixed line, run on real files: only the block changes, line endings kept, a missing block is added."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wb = Path(self.tmp.name)
        (self.wb / ".aibl-local" / "house").mkdir(parents=True)
        self.line = splice_line("aibl-update")

    def write(self, agents, rendered):
        (self.wb / "AGENTS.md").write_bytes(agents)
        (self.wb / ".aibl-local" / "house" / "AGENTS.md.rendered").write_bytes(rendered)

    def run_line(self):
        code = self.line[len('python3 -c "'):-1]
        r = subprocess.run([sys.executable, "-c", code], cwd=self.wb, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.wb / "AGENTS.md").read_bytes()

    def test_replaces_only_the_block_crlf(self):
        mine = b"# Mine\r\nmy own edit\r\n\r\n<!-- house:begin (old) -->\r\nold team\r\n<!-- house:end -->\r\n\r\nafter, my edit\r\n"
        rendered = b"# Mine\r\nstale\r\n\r\n<!-- house:begin (new) -->\r\nnew team\r\n<!-- house:end -->\r\n\r\nstale after\r\n"
        self.write(mine, rendered)
        self.assertEqual(self.run_line(),
                         b"# Mine\r\nmy own edit\r\n\r\n<!-- house:begin (new) -->\r\nnew team\r\n<!-- house:end -->\r\n\r\nafter, my edit\r\n")

    def test_adds_a_missing_block_at_the_end(self):
        self.write(b"# Mine\nno block\n\n\n", b"# Mine\nno block\n\n<!-- house:begin (r) -->\nteam\n<!-- house:end -->\n")
        self.assertEqual(self.run_line(), b"# Mine\nno block\n\n<!-- house:begin (r) -->\nteam\n<!-- house:end -->\n")

    def test_second_run_changes_nothing(self):
        self.write(b"a\n<!-- house:begin x -->\nold\n<!-- house:end -->\nb\n", b"<!-- house:begin y -->\nnew\n<!-- house:end -->\n")
        first = self.run_line()
        self.assertEqual(self.run_line(), first)
        self.assertEqual(first, b"a\n<!-- house:begin y -->\nnew\n<!-- house:end -->\nb\n")

    @unittest.skipUnless(git_bash(), "Git Bash runs the line as the app does on Windows")
    def test_runs_in_git_bash(self):
        py = "python" if subprocess.run(["python", "--version"], capture_output=True).returncode == 0 else "py -3"
        self.write(b"x\r\n<!-- house:begin -->\r\nold\r\n<!-- house:end -->\r\ny\r\n", b"<!-- house:begin -->\r\nnew\r\n<!-- house:end -->\r\n")
        r = subprocess.run([git_bash(), "-c", self.line.replace("python3", py, 1)], cwd=self.wb, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.wb / "AGENTS.md").read_bytes(), b"x\r\n<!-- house:begin -->\r\nnew\r\n<!-- house:end -->\r\ny\r\n")


if __name__ == "__main__":
    unittest.main()
