"""Week 3 update follow-ups (card W204, 11-17-2026): robot R6-U and the post-publish check.

1. Working notes reached the student ("Now compare the core skill files and gitignore.", "Not asked (v2 run).
   Now the team settings preview.", "I'm checking ..."), one with an internal label. The update's Rules now say
   "Write no sentence before a command. A reply's first words are a result or a question." and no internal
   label ever reaches the student.
2. Claude Code left out the plain line before `--codex-threads-apply`. It is now a required step line in both apps.
3. The @ menu preview was taken in the first look, before the update's own commits, so its `--expect` went stale
   (`changed_since_preview`) and the student said yes twice. The preview is now taken after step 6.5's commits.
4. The team note took two yeses ("Update that note?", then "Add it? I can show you the exact lines"). It now asks
   once, and shows the exact lines only if the student asks.
5. aibl-enroll step 7 still rendered the team note into a temporary folder and compared with `git diff --no-index`.
   It now uses the update's fixed lines: render into `.aibl-local/house`, read both files, copy with a fixed line,
   and never `<ref>:<path>`. Its Git Bash check runs enroll's own fixed reads through Git for Windows' bash.

Text checks always; the Git Bash class runs only on Windows with Git for Windows.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_git_bash_paths import git_bash, git_spans, ref_path_args  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def skill(name):
    a, b = [(ROOT / app / "skills" / name / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b, f"the Claude and Codex copies of {name} must be identical"
    return a


def step(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


class UpdateWords(unittest.TestCase):
    def setUp(self):
        self.text = skill("aibl-update")
        self.rules = self.text[self.text.index("## Rules"):]

    def test_no_sentence_before_a_command(self):
        self.assertIn("- **Write no sentence before a command. A reply's first words are a result or a question.**", self.rules)
        self.assertIn("The only exceptions are a step's own plain line from this skill", self.rules)
        for quoted in ('no "Now compare the core skill files"', 'no "Now the team settings preview"', 'no "I\'m checking ..."'):
            self.assertIn(quoted, self.rules)
        self.assertIn("Never report a check's result unless a step says to", self.rules)

    def test_the_talk_rule_comes_first(self):
        top = self.text[:self.text.index("## In Codex")]
        self.assertIn("## How you talk while you work: no working notes", top)
        self.assertIn("Write no sentence before a command. A reply's first words are a result or a question. Between commands, say nothing.", top)
        for seen in ('"Now compare ..."', "\"Next: the team's settings preview ...\"", "\"I'm now checking ...\"", '"Not asked (v2 run)"'):
            self.assertIn(seen, top)

    def test_placeholders_are_filled_in(self):
        self.assertIn("- **Every `<...>` in a command here is a placeholder.**", self.rules)
        self.assertIn("never run a command that still has `<` or `>` in it", self.rules)
        self.assertIn("Record the starting commit for recovery: the id `git rev-parse HEAD` prints", self.text)
        # 11-17 run 2: the team note was compared with a commit after the merge, so the offer never came
        self.assertIn("never one this update made, such as the merge, the registry's or one with `^` after it", self.rules)
        self.assertIn("with the starting commit from step 1 as the pre-update commit", self.text)

    def test_team_settings_apply_carries_its_expect(self):
        # 11-17 run 3: `settings-merge.mjs --apply` without --expect, a red row
        self.assertIn("never `--apply` alone, which fails", self.text)
        self.assertIn("`node workforce/house/settings-merge.mjs --apply --expect <preview_sha256 from that preview>`", self.text)

    def test_no_internal_label(self):
        self.assertIn("- **No internal label ever reaches the student.**", self.rules)
        for label in ("`v2_run` or \"v2 run\"", "`in_step`", "`returning_v1`", "a skill's folder name"):
            self.assertIn(label, self.rules)

    def test_codex_threads_line_is_required(self):
        s = step(self.text, "**Let Codex run more of the team at once", "Then prove one agent answers.")
        self.assertIn("say this plain line, in both apps, word for word, as the only words right before the apply", s)
        self.assertIn("It is a required step line: never leave it out, also in Claude Code, where no box follows it.", s)
        self.assertLess(s.index("Next I let Codex run more of your agents at once in this workbench."), s.index("--codex-threads-apply"))
        self.assertIn("Write it before you run the apply, never in the same batch of commands as the report or the apply", s)

    def test_agent_menu_preview_after_the_commits(self):
        s = step(self.text, "6.5. **Make the update live.**", "\n7. **Verify what arrived.**")
        menu = s.index("Run `node .claude/hooks/update-check.mjs --agent-menu` yourself")
        self.assertLess(s.index('git commit -m "Rebuild the team registry"'), menu)
        self.assertLess(s.index('git commit -m "Let Codex run more of your agents at once"'), menu)
        self.assertIn("Take this preview here, after this step's reapply and commits", s)
        self.assertIn("never in the first look or any earlier step", s)
        self.assertIn("If one was taken earlier in this update, it is out of date: take it again here and use only this one's `preview_sha256`.", s)
        before = self.text[:self.text.index("6.5. **Make the update live.**")]
        self.assertNotIn("--agent-menu`", before)

    def test_team_note_asks_once(self):
        how = next(l for l in self.text.splitlines() if l.startswith("- **The team note:**"))
        self.assertIn("one question, asked once", how)
        self.assertIn("never an offer to show its lines. Show the exact lines only if the student asks for them.", how)
        self.assertNotIn("offer to show it, then ask", how)
        offer = next(l for l in self.text.splitlines() if l.lstrip().startswith('- **"Tell my assistant about my team"'))
        self.assertIn('Want me to tell it? I recommend yes."', offer)
        self.assertIn('Want me to update it? I recommend yes."', offer)
        self.assertIn("Don't offer to show the lines", offer)
        self.assertEqual(len(re.findall(r'\?\s', offer.replace('?"', '? "'))), 2, "two alternative wordings of the one question, nothing more")


class EnrollStep7(unittest.TestCase):
    def setUp(self):
        self.text = skill("aibl-enroll")
        self.offer = next(l for l in self.text.splitlines() if l.lstrip().startswith('- **"Tell my assistant about my team"**'))

    def test_no_temporary_folder(self):
        self.assertNotIn("mkdtemp", self.text)
        self.assertNotIn("<temp", self.text)
        self.assertNotIn("in a temporary folder", self.text)
        self.assertEqual(self.text.count("temporary folder"), 1)
        self.assertIn("(no temporary folder, no `git diff`, no `git diff --no-index`, no `diff`, no compare script)", self.offer)

    def test_the_fixed_lines(self):
        for line in ("`python3 workforce/house/compile-house.py --out-dir .aibl-local/house`",
                     "`python3 -c \"__import__('shutil').copyfile('.aibl-local/house/AGENTS.md.rendered', 'AGENTS.md')\"`",
                     "`python3 -c \"__import__('shutil').copyfile('.aibl-local/house/CLAUDE.md.rendered', 'CLAUDE.md')\"`",
                     "`git commit -m \"Tell my assistant about my team\" -- AGENTS.md CLAUDE.md`",
                     "compare by reading `AGENTS.md` beside `.aibl-local/house/AGENTS.md.rendered`"):
            self.assertIn(line, self.offer)
        self.assertIn("(in Codex it needs no permission)", self.offer)
        self.assertIn("for the house block's commit (its render and copy stay inside the workbench and need none)", self.text)

    def test_same_lines_as_the_update(self):
        update = next(l for l in skill("aibl-update").splitlines() if l.lstrip().startswith('- **"Tell my assistant about my team"'))
        for span in re.findall(r"`([^`]+)`", self.offer):
            if span.startswith(("python3 ", "git commit")):
                self.assertIn(span, update, span)

    def test_one_yes_and_no_raw_block_unasked(self):
        self.assertIn("That one yes covers the render, the check, the copy and the save", self.offer)
        self.assertNotIn("Show the student that block", self.offer)
        self.assertNotIn("show `git diff`", self.offer)

    def test_no_ref_colon_path_and_no_git_diff_after_the_team_settings(self):
        for line in self.text.splitlines():
            for command in git_spans(line.replace("`<ref>:<path>`", "")):
                if "<remote>/student:.aibl" in command:
                    continue  # the rule names the old shape to forbid it
                self.assertEqual(ref_path_args(command), [], command)
        step7 = self.text[self.text.index("7. **Verify and start.**"):]
        self.assertNotIn("git diff --name-only", step7)
        self.assertIn("`git ls-tree <commit before the merge> -- work/team-hq` and `git ls-tree HEAD -- work/team-hq` print the same id", step7)

    def test_python_on_windows_starts_with_python(self):
        self.assertNotIn("if `python3` is not found", self.text)

    def test_codex_table_has_no_render_row(self):
        table = self.text[self.text.index("| Step |"):self.text.index("A save offered with")]
        self.assertNotIn("compile-house.py", table)
        self.assertNotIn("temporary", table)

    def test_no_dashes(self):
        for name in ("aibl-enroll", "aibl-update"):
            t = skill(name)
            self.assertNotIn("—", t)
            self.assertNotIn("–", t)


@unittest.skipUnless(git_bash(), "Git Bash path rewriting happens only in Git for Windows' bash")
class EnrollInGitBash(unittest.TestCase):
    def setUp(self):
        self.bash = git_bash()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / "wb"
        for rel in ("AGENTS.md", "CLAUDE.md", "work/team-hq/notes.md", ".aibl/course-agents.json", ".gitignore"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("# " + rel + "\n")
        (self.repo / ".gitignore").write_text(".aibl-local/\n")
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(base / "gitconfig"))
        (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n")
        self.env = env
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"], ["branch", "agent-workforce/student"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True, capture_output=True)
        house = self.repo / ".aibl-local" / "house"
        house.mkdir(parents=True)
        (house / "AGENTS.md.rendered").write_text("# AGENTS.md\n<!-- house:begin -->\nteam\n<!-- house:end -->\n")

    def sh(self, line):
        return subprocess.run([self.bash, "-c", line], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_the_old_shape_fails_and_the_reads_pass(self):
        self.assertNotEqual(self.sh("git cat-file -p agent-workforce/student:.aibl/course-agents.json").returncode, 0)
        r = self.sh("git ls-tree agent-workforce/student -- .aibl/course-agents.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.sh(f"git cat-file -p {r.stdout.split()[2]}").returncode, 0)
        before = self.sh("git rev-parse HEAD").stdout.strip()
        a, b = self.sh(f"git ls-tree {before} -- work/team-hq"), self.sh("git ls-tree HEAD -- work/team-hq")
        self.assertEqual((a.returncode, b.returncode), (0, 0))
        self.assertEqual(a.stdout, b.stdout)
        self.assertTrue(a.stdout.strip())

    def test_the_copy_line_runs_and_the_render_folder_stays_out_of_git(self):
        py = shutil.which("python") and "python" or (shutil.which("py") and "py -3")
        if not py:
            self.skipTest("no python on PATH")
        line = next(s for s in re.findall(r"`([^`]+)`", skill("aibl-enroll")) if "copyfile('.aibl-local/house/AGENTS.md.rendered'" in s)
        r = self.sh(line.replace("python3", py, 1))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("house:begin", (self.repo / "AGENTS.md").read_text())
        status = self.sh("git status --porcelain --untracked-files=all").stdout.split()
        self.assertEqual(status, ["M", "AGENTS.md"])


if __name__ == "__main__":
    unittest.main()
