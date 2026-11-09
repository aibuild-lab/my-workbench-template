"""In Codex, aibl-update asks one permission for each protected write, and waits when it isn't allowed.

Codex keeps a workbench's `.git`, `.agents` and `.codex` read-only for agents, and everything outside
the workbench, unless the student allows the step (Wade's hand checks, 11-01-2026: the first save
failed with "Unable to create .git/index.lock: Permission denied"; it worked when the agent asked the
app for permission together with the command; through an agent it failed on a command joined with
`;` and worked as two separate commands). So the skill's "In Codex" section lists every write the
update makes, each its own command, with one plain line before it and a waiting line if it isn't
allowed, and every step that writes says so.

Two kinds of check. Text checks: every write command named in the steps is in the section's table,
every step that writes carries the marker, no command is joined to another, and the student lines
are plain. Git checks: the waiting lines are true. A refused write is simulated with the exact
condition Codex's refusal leaves (Git cannot create its lock file), one command at a time, and the
workbench must be exactly as it was; a refused commit after an allowed merge must leave the update's
files in place, unsaved, and a retry of only that commit must finish the update.
"""
import os, re, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = [ROOT / app / "skills" / "aibl-update" / "SKILL.md" for app in (".claude", ".agents")]
MARK = "Codex: one permission per write"
SECTION = "## In Codex: one permission for each protected write"

# Every git verb the skill names, sorted into writes and reads. A verb in neither list fails the test,
# so a new command has to be classified (and, if it writes, put in the table) before it can ship.
GIT_READS = {"status", "log", "diff", "show", "rev-parse", "rev-list", "ls-tree", "merge-base", "cat-file", "ls-files",
             "remote get-url"}
GIT_WRITES = {"remote add", "fetch", "checkout", "merge", "commit", "add", "revert", "merge --abort"}
# Scripts the skill runs: those in the table write a protected place; the others are named here with
# why they need no permission. Anything else fails the test.
SCRIPT_WRITES = ["update-check.mjs --json", "update-check.mjs --home-workbench-apply", "name_seat.py --reapply",
                 "connect_seat.py --reapply", "start_fresh.py answer", "install_codex_langfuse.py",
                 "install_claude_langfuse.py"]
SCRIPT_NO_PERMISSION = {
    "update-check.mjs --agent-menu-apply": "Claude Code only; Codex has no agent menu",
    "update-check.mjs --agent-menu": "read-only preview",
    "update-check.mjs --home-workbench": "read-only preview",
    "start_fresh.py check": "changes nothing",
    "generate-registry.py": "writes workforce/shed/ in the workbench, not a protected folder",
    "recorder_context.py show": "read only",
    "settings-merge.mjs": "writes .claude/settings.json and its backup, not a protected folder; the commit is in the table",
    "--check": "the recorder installers' read-only check",
}


def skill_text():
    texts = [p.read_text(encoding="utf-8") for p in SKILLS]
    return texts[0], texts


def section(text):
    start = text.index(SECTION)
    return text[start:text.index("## Steps", start)]


def steps(text):
    """The numbered steps, each with its indented continuation lines."""
    body = text[text.index("## Steps"):text.index("## Rules")]
    found, current = {}, None
    for line in body.splitlines():
        m = re.match(r"^(\d+(?:\.\d+)?)\. \*\*", line)
        if m:
            current = m.group(1)
            found[current] = line
        elif current:
            found[current] += "\n" + line
    return found


def table_rows(text):
    rows = []
    for line in section(text).splitlines():
        if line.startswith("| ") and not line.startswith("| Step") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            rows.append(cells)
    return rows


def spans(text):
    return re.findall(r"`([^`]+)`", re.sub(r"```.*?```", "", text, flags=re.S))


def git_verb(command):
    words = command.split()
    if words[:1] != ["git"] or len(words) < 2:
        return None
    if words[1] == "remote" and len(words) > 2:
        return "remote " + words[2]
    if words[1] == "merge" and "--abort" in words:
        return "merge --abort"
    return words[1]


class SkillText(unittest.TestCase):
    def setUp(self):
        self.text, texts = skill_text()
        self.assertEqual(texts[0], texts[1], "the Claude and Codex copies of aibl-update must be identical")

    def test_the_section_states_the_five_rules(self):
        s = section(self.text)
        for phrase in ["**One plain line first.**", "Codex may ask you to allow it. If it does, choose Allow.",
                       "Codex may ask to use the network. If it does, choose Allow.",
                       "never joined to another with `&&`, `;` or `|`",
                       "Request the app's permission together with that exact command",
                       "Never try it first and ask only after it fails",
                       "names the same step as your plain line",
                       "**One line and one box per write.**",
                       "**Never a terminal step for the student.**",
                       "**If it isn't allowed, wait.**",
                       "the session's approval policy is never",
                       "never say or suggest the step happened",
                       "that reply is exactly two lines: the step's plain line, then its waiting line, word for word",
                       "Nothing before them and nothing after: no note that a permission is needed or can't be asked, no quote of this skill, no file link",
                       "On \"try again\""]:
            self.assertIn(phrase, s)

    def test_every_git_write_in_the_steps_is_in_the_table(self):
        table = " ".join(r[1] for r in table_rows(self.text))
        table_verbs = {git_verb(c) for c in spans(table)} - {None}
        for name, body in steps(self.text).items():
            for command in spans(body):
                verb = git_verb(command)
                if verb is None:
                    continue
                self.assertIn(verb, GIT_READS | GIT_WRITES, f"step {name}: classify `{command}` as a read or a write")
                if verb in GIT_WRITES:
                    self.assertIn(verb, table_verbs, f"step {name}: `{command}` writes .git but is not in the table")
                    self.assertIn(MARK, body, f"step {name} runs `{command}` but has no Codex marker")

    def test_every_script_the_steps_run_is_classified(self):
        table = " ".join(r[1] for r in table_rows(self.text))
        for name, body in steps(self.text).items():
            for command in spans(body):
                if not re.search(r"\.(py|mjs)\b", command):
                    continue
                if any(w in command for w in SCRIPT_WRITES) and "--check" not in command:
                    key = next(w for w in SCRIPT_WRITES if w in command)
                    self.assertIn(key.split()[0], table, f"step {name}: `{command}` writes a protected place")
                    self.assertIn(MARK, body, f"step {name} runs `{command}` but has no Codex marker")
                else:
                    self.assertTrue(any(k in command for k in SCRIPT_NO_PERMISSION) or command.endswith(".py")
                                    or command.endswith(".mjs"),
                                    f"step {name}: classify `{command}` in SCRIPT_WRITES or SCRIPT_NO_PERMISSION")
        for write in SCRIPT_WRITES:
            self.assertIn(write.split()[0], table, f"{write} is missing from the table")

    def test_every_step_that_writes_carries_the_marker(self):
        found = steps(self.text)
        for name in ["1", "2", "2.5", "3", "4", "6", "6.1", "6.5", "7"]:
            self.assertIn(MARK, found[name], f"step {name}")

    def test_each_row_has_a_plain_line_and_a_waiting_line(self):
        rows = table_rows(self.text)
        self.assertGreaterEqual(len(rows), 16)
        for step, write, plain, waiting in rows:
            self.assertTrue(plain.startswith('"Next '), plain)
            self.assertRegex(plain, r"Codex may ask (you to allow it|to use the network)\. If it does, choose Allow\.\"")
            for line in (plain, waiting):
                self.assertNotIn("`", line)
                self.assertNotRegex(line, r"\b[A-Z]{2,}\b", "no word in capitals in a student line")
                self.assertNotRegex(line, r"\w/\w", "no path in a student line")
            self.assertRegex(waiting, r"nothing (else changed|is lost|changed|has changed)")
            self.assertIn('Say "try again"', waiting)

    def test_the_week_2_line_on_lesson_1s_page_is_the_merge_commit_line(self):
        # copy-a's Lesson 1 "bring Week 2 in" box quotes this line as its example; with <what's new> = Week 2.
        rows = {r[1]: r for r in table_rows(self.text)}
        commit = rows["the merge's `git commit`"]
        self.assertEqual(commit[2].replace("<what's new>", "Week 2"),
                         '"Next I bring Week 2 into your workbench\'s history. Codex may ask you to allow it. If it does, choose Allow."')

    def test_no_command_is_joined_to_another(self):
        blocks = re.findall(r"```[a-z]*\n(.*?)```", self.text, flags=re.S)
        for command in spans(self.text) + [l for b in blocks for l in b.splitlines()]:
            if command.strip() in {"&&", ";", "|"}:
                continue
            self.assertNotIn("&&", command)
            self.assertNotRegex(command, r";\s*\S", f"joined command: {command}")
            self.assertNotRegex(command, r"\s\|\s", f"piped command: {command}")

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("\u2014", self.text)
        self.assertNotIn("\u2013", self.text)


class WaitingLinesAreTrue(unittest.TestCase):
    """Codex's refusal leaves Git unable to create its lock file. Each write, refused alone, changes nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.course = base / "course"
        self.template = base / "template"
        self.wb = base / "wb"
        for repo, branch in ((self.course, "student"), (self.template, "main"), (self.wb, "main")):
            repo.mkdir()
            self.git(repo, "init", "-q", "-b", branch)
        self.write(self.template, {".agents/skills/aibl-update/SKILL.md": "template update\n",
                                   ".claude/skills/aibl-update/SKILL.md": "template update\n"})
        self.git(self.template, "add", "-A")
        self.git(self.template, "commit", "-qm", "template")
        self.write(self.course, {"course/workforce/lessons/week1.md": "Week 1\n"})
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "Week 1")
        self.write(self.wb, {".agents/skills/aibl-update/SKILL.md": "my update\n",
                             ".claude/skills/aibl-update/SKILL.md": "my update\n", "work/notes.md": "mine\n"})
        self.git(self.wb, "add", "-A")
        self.git(self.wb, "commit", "-qm", "my workbench")
        self.git(self.wb, "remote", "add", "agent-workforce", str(self.course))
        self.git(self.wb, "remote", "add", "template", str(self.template))
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")
        self.git(self.wb, "merge", "-q", "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Workforce",
                 "agent-workforce/student")
        self.write(self.course, {"course/workforce/lessons/week2.md": "Week 2\n",
                                 ".agents/skills/aibl-new/SKILL.md": "new skill\n",
                                 ".codex/agents/aibl-new.toml": "name = \"aibl-new\"\n"})
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "Week 2")

    def git(self, repo, *args, check=True):
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                           capture_output=True, text=True, timeout=120)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def write(self, repo, files):
        for name, body in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body.encode())

    def state(self):
        head = self.git(self.wb, "rev-parse", "HEAD").stdout.strip()
        status = self.git(self.wb, "status", "--porcelain", "--untracked-files=all").stdout
        refs = self.git(self.wb, "for-each-ref", "--format=%(refname) %(objectname)").stdout
        files = sorted(str(p.relative_to(self.wb)) for p in self.wb.rglob("*") if p.is_file() and ".git" not in p.parts)
        merging = (self.wb / ".git" / "MERGE_HEAD").exists()
        return head, status, refs, files, merging

    def refused(self, *args, lock=".git/index.lock", message=".lock"):
        """Run one write the way Codex refuses it: Git can't create its lock. Return the result."""
        path = self.wb / lock
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        try:
            r = self.git(self.wb, *args, check=False)
        finally:
            path.unlink()
        self.assertNotEqual(r.returncode, 0, f"git {' '.join(args)} should have been refused")
        self.assertIn(message, r.stderr)
        return r

    def test_a_refused_fetch_changes_nothing(self):
        before = self.state()
        self.refused("fetch", "-q", "agent-workforce", "student",
                     lock=".git/refs/remotes/agent-workforce/student.lock", message="failed")
        self.assertEqual(self.state(), before)
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")  # "try again", allowed
        self.assertNotEqual(self.state()[2], before[2])

    def test_a_refused_checkout_of_the_chosen_paths_changes_nothing(self):
        self.git(self.wb, "fetch", "-q", "template", "main")
        before = self.state()
        paths = [".agents/skills/aibl-update", ".claude/skills/aibl-update"]
        self.refused("checkout", "template/main", "--", *paths)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.wb / ".agents/skills/aibl-update/SKILL.md").read_text(), "my update\n")
        self.git(self.wb, "checkout", "template/main", "--", *paths)  # "try again", allowed
        self.assertEqual((self.wb / ".agents/skills/aibl-update/SKILL.md").read_text(), "template update\n")
        self.assertEqual((self.wb / "work/notes.md").read_text(), "mine\n")

    def test_a_refused_merge_changes_nothing(self):
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")
        before = self.state()
        self.refused("merge", "--no-ff", "--no-commit", "agent-workforce/student")
        self.assertEqual(self.state(), before)
        self.assertFalse(before[4])

    def test_a_refused_commit_after_the_merge_keeps_the_files_and_try_again_saves_only_them(self):
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")
        start = self.git(self.wb, "rev-parse", "HEAD").stdout.strip()
        incoming = self.git(self.wb, "rev-parse", "agent-workforce/student").stdout.strip()
        self.git(self.wb, "merge", "--no-ff", "--no-commit", "agent-workforce/student")
        before = self.state()
        self.refused("commit", "--no-edit")
        after = self.state()
        self.assertEqual(after, before)
        head, status, _, files, merging = after
        self.assertEqual(head, start)                       # not saved in history
        self.assertTrue(merging)                            # the merge is still in progress
        for f in ("course/workforce/lessons/week2.md", ".agents/skills/aibl-new/SKILL.md", ".codex/agents/aibl-new.toml"):
            self.assertIn(f.replace("/", os.sep), files)    # the update's files are in place: nothing is lost
        self.assertEqual((self.wb / "work/notes.md").read_text(), "mine\n")
        self.git(self.wb, "commit", "--no-edit")           # "try again" runs only the commit
        parents = self.git(self.wb, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
        self.assertEqual(parents, [start, incoming])
        self.assertEqual(self.git(self.wb, "status", "--porcelain").stdout, "")

    def test_a_refused_abort_leaves_the_merge_as_it_was(self):
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")
        self.git(self.wb, "merge", "--no-ff", "--no-commit", "agent-workforce/student")
        before = self.state()
        self.refused("merge", "--abort")
        self.assertEqual(self.state(), before)
        self.git(self.wb, "merge", "--abort")              # "try again", allowed
        self.assertFalse(self.state()[4])
        self.assertEqual(self.git(self.wb, "status", "--porcelain").stdout, "")


if __name__ == "__main__":
    unittest.main()
