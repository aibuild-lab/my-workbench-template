"""aibl-update never writes `<ref>:<path>`, and never shows step numbers or working notes (robot R5-U, 11-16-2026).

Claude Code on Windows runs commands in Git Bash, which rewrites an argument shaped `<ref with a slash>:<path
starting with a dot>` as a Windows path list: `template/main:.gitignore` reaches Git as `template\\main;.gitignore`
and fails with exit 128, a red row for the student. The update read `.gitignore`, `.claude/...` and `.agents/...`
from `template/main` that way in steps 2, 2.5 and 6.5. It now gets each id with `git ls-tree <ref> -- <path>` (the
staged one with `git ls-files -s -- <path>`) and reads it with `git cat-file -p <id>`, and its Rules forbid the old
shape. The Git Bash check runs the skill's own fixed read lines through Git for Windows' bash (skipped elsewhere)
and shows the old shape failing there, so a return of it would be caught by the text check and explained here.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEVER = "- **Never write `<ref>:<path>`**"


def skill():
    a, b = [(ROOT / app / "skills" / "aibl-update" / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b
    return a


def git_spans(text):
    return [s for s in re.findall(r"`([^`]+)`", text) if s.startswith("git ")]


def ref_path_args(command):
    """Arguments shaped <ref>:<path> (a colon inside a word that isn't a URL, an option or a pathspec magic)."""
    out = []
    for word in command.split()[1:]:
        word = word.strip("'\"")
        if word.startswith(("-", ":(", "http", "ssh")) or "://" in word or "=" in word:
            continue
        if ":" in word:
            out.append(word)
    return out


def git_bash():
    if os.name != "nt":
        return None
    try:
        exec_path = subprocess.run(["git", "--exec-path"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    for parent in Path(exec_path).parents:
        candidate = parent / "usr" / "bin" / "bash.exe"
        if candidate.exists():
            return str(candidate)
    return None


class Words(unittest.TestCase):
    def setUp(self):
        self.text = skill()

    def test_no_ref_colon_path_in_any_git_command(self):
        for line in self.text.splitlines():
            if line.startswith(NEVER):
                continue  # the rule names the old shape to forbid it
            for command in git_spans(line):
                self.assertEqual(ref_path_args(command), [], f"`{command}`: use git ls-tree and git cat-file -p <id>")

    def test_the_old_shape_is_caught(self):
        for old in ("git cat-file -p template/main:.gitignore", "git rev-parse HEAD:.claude/hooks/update-check.mjs",
                    "git cat-file -p :<file>", "git rev-parse <pre-update commit>:workforce/HOUSE.md"):
            self.assertNotEqual(ref_path_args(old), [], old)
        for fine in ("git ls-tree template/main -- .gitignore", "git ls-files -s -- <path>", "git cat-file -p <id>",
                     "git rev-list -1 --before=2026-10-26T00:00:00 HEAD -- ':(glob)work/**'"):
            self.assertEqual(ref_path_args(fine), [], fine)

    def test_rules_forbid_the_shape_and_working_notes(self):
        rules = self.text[self.text.index("## Rules"):]
        self.assertIn(NEVER, rules)
        self.assertIn("Git Bash rewrites it as a Windows path when the ref has a slash and the path starts with a dot", rules)
        self.assertIn("**Say nothing between commands except a step's own plain line.**", rules)
        self.assertIn("Never show the owner a step number, a step's heading or name from this skill, or a working note", rules)

    def test_the_replacement_reads_are_named(self):
        for phrase in ["`git ls-tree HEAD -- <path>` and `git ls-tree template/main -- <path>` print different ids",
                       "the blob id `git ls-tree template/main -- .gitignore` prints",
                       "taking the staged id from `git ls-files -s -- <path>` and the saved id from `git ls-tree HEAD -- <path>`",
                       "`git ls-tree HEAD -- .claude/hooks/update-check.mjs` and `git ls-tree template/main -- .claude/hooks/update-check.mjs` print the same id",
                       "`git ls-tree <pre-update commit> -- workforce/HOUSE.md` and `git ls-tree HEAD -- workforce/HOUSE.md` print different ids"]:
            self.assertIn(phrase, self.text)


@unittest.skipUnless(git_bash(), "Git Bash path rewriting happens only in Git for Windows' bash")
class InGitBash(unittest.TestCase):
    def setUp(self):
        self.bash = git_bash()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / "wb"
        for rel in (".gitignore", ".claude/hooks/update-check.mjs", "workforce/HOUSE.md", "README.md"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("# " + rel + "\n")  # a comment, so .gitignore ignores nothing
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(base / "gitconfig"))
        (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n")
        self.env = env
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"], ["branch", "template/main"]):
            subprocess.run(["git", *args], cwd=self.repo, env=env, check=True, capture_output=True)

    def sh(self, line):
        return subprocess.run([self.bash, "-c", line], cwd=self.repo, env=self.env, capture_output=True, text=True)

    def test_the_old_shape_fails_in_git_bash(self):
        r = self.sh("git cat-file -p template/main:.gitignore")
        self.assertNotEqual(r.returncode, 0, "Git Bash no longer rewrites it; the rule is still the safe form")

    def test_the_skills_fixed_reads_pass_in_git_bash(self):
        lines = ["git ls-tree HEAD -- .claude/hooks/update-check.mjs",
                 "git ls-tree template/main -- .claude/hooks/update-check.mjs",
                 "git ls-tree template/main -- .gitignore",
                 "git ls-tree HEAD -- workforce/HOUSE.md",
                 "git ls-files -s -- .gitignore",
                 "git ls-tree -r template/main -- .claude"]
        text = skill()
        for line in lines[:4]:
            self.assertIn(line, text)
        ids = set()
        for line in lines:
            r = self.sh(line)
            self.assertEqual(r.returncode, 0, f"{line}: {r.stderr}")
            self.assertTrue(r.stdout.strip(), line)
            ids.add(r.stdout.split()[2] if "ls-tree" in line else r.stdout.split()[1])
        for blob in ids:
            r = self.sh(f"git cat-file -p {blob}")
            self.assertEqual(r.returncode, 0, r.stderr)
        same = {self.sh(l).stdout.split()[2] for l in lines[:2]}
        self.assertEqual(len(same), 1, "HEAD and template/main hold the same hook: the same id")


if __name__ == "__main__":
    unittest.main()
