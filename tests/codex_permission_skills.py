"""aibl-checkpoint and aibl-enroll in Codex: one permission for each protected write, as in aibl-update.

Same rule as tests/codex_permission.py (read its docstring for why), applied to the other two
template skills that write the workbench's history. These two use the course's Week 1 words for the
box ("If Codex asks you to allow a save to your workbench's history, that's this save; choose to
allow it."), because students meet them in setup and Week 1, where the lessons say it that way;
aibl-update keeps Week 2's fixed line ("Codex may ask you to allow it. If it does, choose Allow."), which
Lesson 1's page quotes.

Text checks: both copies identical; the five rules; every Git verb named is classified, every write
is in the table and its paragraph is marked; every script is classified; each row has a plain line
in the Week 1 words and a waiting line (or says it carries on); no joined command; no dashes. Git
checks: a refused push leaves the save on this computer; a save of tracked files is one command;
a refused enroll merge changes nothing; a refused commit after the merge keeps the program's files
until "try again" runs only the commit.
"""
import re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARK = "Codex: one permission per write"
SECTION = "## In Codex: one permission for each protected write"
SAVE = "If Codex asks you to allow a save to your workbench's history, that's this save; choose to allow it."
STEP = "If Codex asks you to allow it, that's this step; choose to allow it."
AGENT = "If Codex asks you to allow a change to your agent files, that's this step; choose to allow it."
GIT_READS = {"status", "diff", "log", "show", "rev-parse", "rev-list", "ls-tree", "merge-base", "cat-file", "ls-files", "remote get-url"}
GIT_WRITES = {"remote add", "fetch", "checkout", "merge", "commit", "add", "merge --abort", "push", "pull", "config", "rm"}
GH_WRITES = {"gh auth setup-git"}
NEVER = {"reset", "stash"}  # named only to forbid them
SCRIPT_WRITES = ["--camp-record", "--home-workbench-apply", "mark-v2", "name_seat.py --reapply", "compile-house.py",
                 "privacy_check.py untrack", "staged --unstage"]
SCRIPT_NO_PERMISSION = ["--joining-from", "--home-workbench", "settings-merge.mjs",
                        "privacy_check.py gate", "privacy_check.py staged", "privacy_check.py ignore"]
CARRY_ON = ("Then carry on", "carry on.")


def text_of(name):
    texts = [(ROOT / app / "skills" / name / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    return texts


def section(text):
    start = text.index(SECTION)
    return text[start:text.index("\n## ", start + 5)]


def after_section(text):
    start = text.index(SECTION)
    rest = text[text.index("\n## ", start + 5):]
    return re.sub(r"```.*?```", "", rest, flags=re.S)


def spans(text):
    return re.findall(r"`([^`]+)`", re.sub(r"```.*?```", "", text, flags=re.S))


def rows(text):
    out = []
    for line in section(text).splitlines():
        if line.startswith("| ") and not line.startswith(("| Step", "| Part")):
            out.append([c.strip() for c in line.strip().strip("|").split(" | ")])
    return out


def blocks(text):
    """Each numbered step on its own, and each paragraph outside the numbered lists."""
    return re.split(r"\n\s*\n|\n(?=\d+(?:\.\d+)?\. )", after_section(text))


def git_verb(command):
    w = command.split()
    if w[:1] == ["gh"]:
        return " ".join(w[:3])
    if w[:1] != ["git"] or len(w) < 2:
        return None
    if w[1] == "remote" and len(w) > 2:
        return "remote " + w[2]
    if w[1] == "merge" and "--abort" in w:
        return "merge --abort"
    return w[1]


class SkillText:
    name = None

    def setUp(self):
        claude, codex = text_of(self.name)
        self.assertEqual(claude, codex, f"the Claude and Codex copies of {self.name} must be identical")
        self.text = claude

    def test_the_section_states_the_five_rules_in_week_1_words(self):
        s = section(self.text)
        for phrase in ["**One plain line first.**", "the course's Week 1 words for the box", SAVE, STEP,
                       "never joined to another with `&&`, `;` or `|`",
                       "Request the app's permission together with that exact command",
                       "Never try it first and ask only after it fails",
                       "names the same step as your plain line",
                       "**One line and one box per write.**",
                       "**Never a terminal step for the",
                       "**If it isn't allowed, wait.**",
                       "the session's approval policy is never",
                       "that reply is exactly two lines: the step's plain line, then its waiting line, word for word",
                       "never say or suggest the step happened", "On \"try again\""]:
            self.assertIn(phrase, s)

    def test_every_write_named_is_in_the_table_and_marked(self):
        table = " ".join(r[1] for r in rows(self.text))
        table_verbs = {git_verb(c) for c in spans(table)} - {None}
        for para in blocks(self.text):
            for command in spans(para):
                verb = git_verb(command)
                if verb is None or verb in NEVER or verb.startswith("gh") and verb not in GH_WRITES:
                    continue
                self.assertIn(verb, GIT_READS | GIT_WRITES | GH_WRITES, f"classify `{command}` as a read or a write")
                if verb in GIT_WRITES | GH_WRITES:
                    self.assertIn(verb, table_verbs, f"`{command}` writes but is not in the table")
                    self.assertIn(MARK, para, f"`{command}` is in a paragraph with no Codex marker")

    def test_every_script_is_classified(self):
        table = " ".join(r[1] for r in rows(self.text))
        for para in blocks(self.text):
            for command in spans(para):
                if not re.search(r"\.(py|mjs)\b", command) or command.endswith((".py", ".mjs")):
                    continue
                writes = [w for w in SCRIPT_WRITES if w in command]
                if writes and "--check" not in command:
                    self.assertIn(writes[0], table, f"`{command}` writes a protected place")
                    self.assertIn(MARK, para, f"`{command}` is in a paragraph with no Codex marker")
                else:
                    self.assertTrue(any(k in command for k in SCRIPT_NO_PERMISSION),
                                    f"classify `{command}` in SCRIPT_WRITES or SCRIPT_NO_PERMISSION")

    def test_each_row_has_a_week_1_plain_line_and_a_waiting_line(self):
        found = rows(self.text)
        self.assertGreaterEqual(len(found), self.rows_at_least)
        for _, write, plain, waiting in found:
            self.assertTrue(plain.startswith('"Next '), plain)
            self.assertTrue(plain.endswith((SAVE + '"', STEP + '"', AGENT + '"')), plain)
            for line in (plain, waiting.split('" ')[0]):
                self.assertNotIn("`", line)
                self.assertNotRegex(line, r"\b[A-Z]{2,}\b")
                self.assertNotRegex(line, r"\w/\w")
            if any(c in waiting for c in CARRY_ON):
                continue
            self.assertRegex(waiting, r"nothing (else changed|is lost|changed|has changed)")
            self.assertIn('Say "try again"', waiting)

    def test_no_command_is_joined_to_another(self):
        for command in spans(self.text):
            if command.strip() in {"&&", ";", "|"}:
                continue
            if command.startswith('python3 -c "'):
                continue  # one command; step 7's temp folder example has a ; inside its quoted Python
            self.assertNotIn("&&", command)
            self.assertNotRegex(command, r";\s*\S", command)
            self.assertNotRegex(command, r"\s\|\s", command)

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("\u2014", self.text)
        self.assertNotIn("\u2013", self.text)


class CheckpointText(SkillText, unittest.TestCase):
    name = "aibl-checkpoint"
    rows_at_least = 6

    def test_the_save_line_is_week_1s(self):
        commit = [r for r in rows(self.text) if r[1].startswith("`git commit")][0]
        self.assertTrue(commit[2].endswith(SAVE + '"'))
        self.assertIn('"Saved in two places" only after both the save and the push worked', self.text)


class EnrollText(SkillText, unittest.TestCase):
    name = "aibl-enroll"
    rows_at_least = 14

    def test_the_run_note_gets_a_plain_line_and_never_holds_up_enroll(self):
        note = [r for r in rows(self.text) if "mark-v2" in r[1]][0]
        self.assertIn("carry on", note[3])
        self.assertIn("never mention it beyond the one plain line Codex needs before its box", self.text)

    def test_the_agent_file_line_is_week_1s(self):
        seat = [r for r in rows(self.text) if "name_seat.py" in r[1]][0]
        self.assertTrue(seat[2].endswith(AGENT + '"'))


class UpdatePointsAtTheCheckpoint(unittest.TestCase):
    def test_the_update_uses_the_checkpoints_own_lines(self):
        text = (ROOT / ".claude/skills/aibl-update/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("The checkpoint at the end of step 7 is `aibl-checkpoint`'s: its save and its push follow that skill's own \"In Codex\" section", text)


class RefusedWritesChangeNothing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.origin, self.wb, self.course = base / "origin.git", base / "wb", base / "course"
        self.git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        for repo, branch in ((self.wb, "main"), (self.course, "student")):
            repo.mkdir()
            self.git(repo, "init", "-q", "-b", branch)
        (self.wb / "context").mkdir()
        (self.wb / "context/project.md").write_text("first\n")
        self.git(self.wb, "add", "-A")
        self.git(self.wb, "commit", "-qm", "My workbench")
        self.git(self.wb, "remote", "add", "origin", str(self.origin))
        self.git(self.wb, "push", "-q", "origin", "main")
        (self.course / "course/workforce").mkdir(parents=True)
        (self.course / "course/workforce/welcome.md").write_text("Welcome\n")
        (self.course / ".agents/skills/aibl-workforce").mkdir(parents=True)
        (self.course / ".agents/skills/aibl-workforce/SKILL.md").write_text("skill\n")
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "Agent Workforce")
        self.git(self.wb, "remote", "add", "agent-workforce", str(self.course))
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")

    def git(self, repo, *args, check=True):
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                           capture_output=True, text=True, timeout=120)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def head(self, repo, ref="HEAD"):
        return self.git(repo, "rev-parse", ref).stdout.strip()

    def locked(self, path, *args, repo=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        try:
            r = self.git(repo or self.wb, *args, check=False)
        finally:
            path.unlink()
        self.assertNotEqual(r.returncode, 0)
        return r

    def test_a_save_of_tracked_files_is_one_command(self):
        (self.wb / "context/project.md").write_text("first\nsecond\n")
        (self.wb / "context/other.md").write_text("not in this save\n")
        self.git(self.wb, "add", "--", "context/other.md")
        self.git(self.wb, "commit", "-qm", "Project note, second line", "--", "context/project.md")
        self.assertEqual(self.git(self.wb, "show", "--name-only", "--format=", "HEAD").stdout.split(), ["context/project.md"])

    def test_a_refused_push_leaves_the_save_on_this_computer(self):
        (self.wb / "context/project.md").write_text("first\nsecond\n")
        self.git(self.wb, "commit", "-qm", "Project note", "--", "context/project.md")
        saved = self.head(self.wb)
        before = self.head(self.origin, "main")
        self.locked(self.origin / "refs/heads/main.lock", "push", "-q", "origin", "main")
        self.assertEqual(self.head(self.wb), saved)                   # still saved here
        self.assertEqual(self.head(self.origin, "main"), before)      # not on GitHub yet
        self.git(self.wb, "push", "-q", "origin", "main")            # "try again" runs only the push
        self.assertEqual(self.head(self.origin, "main"), saved)

    def test_a_refused_enroll_merge_changes_nothing_and_a_refused_commit_keeps_the_files(self):
        start = self.head(self.wb)
        lock = self.wb / ".git/index.lock"
        self.locked(lock, "merge", "--allow-unrelated-histories", "--no-ff", "--no-commit", "agent-workforce/student")
        self.assertEqual(self.head(self.wb), start)
        self.assertFalse((self.wb / ".git/MERGE_HEAD").exists())
        self.assertFalse((self.wb / "course").exists())
        self.git(self.wb, "merge", "--allow-unrelated-histories", "--no-ff", "--no-commit", "agent-workforce/student")
        self.locked(lock, "commit", "-m", "Add Agent Workforce")
        self.assertEqual(self.head(self.wb), start)
        self.assertTrue((self.wb / ".git/MERGE_HEAD").exists())
        self.assertTrue((self.wb / ".agents/skills/aibl-workforce/SKILL.md").exists())
        self.git(self.wb, "commit", "-qm", "Add Agent Workforce")    # "try again" runs only the commit
        self.assertEqual(len(self.git(self.wb, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()), 3)


if __name__ == "__main__":
    unittest.main()
