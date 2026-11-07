"""aibl-update and aibl-checkpoint read Git without `git diff`, `git log` or `git show` (D232, 11-07-2026).

The team's settings (af1cc39) put those three in the ask list, so in Claude each one is an Allow box
for the student; launch-walks claude-P1 still saw two from the update's own steps. The skills now
use `git status --porcelain`, `git rev-parse`, `git rev-list`, `git ls-tree`, `git cat-file -p`,
`git ls-files` and `git merge-base`, and name the three only to forbid them. A Git check proves the
replacement reads find the same things the old ones did.
"""
import os, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASKED = re.compile(r"`git (diff|log|show)\b[^`]*`")
FORBIDS = ("never run `git diff`, `git log` or `git show`", "**Read Git without `git diff`, `git log` or `git show`.**")


def text(skill):
    a, b = [(ROOT / app / "skills" / skill / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b, skill
    return a


class SkillText(unittest.TestCase):
    def test_asked_reads_are_named_only_to_forbid_them(self):
        for skill in ("aibl-update", "aibl-checkpoint"):
            for line in text(skill).splitlines():
                if ASKED.search(line):
                    self.assertTrue(any(f in line for f in FORBIDS), f"{skill}: {line[:120]}")

    def test_the_update_names_its_replacements(self):
        t = text("aibl-update")
        for phrase in ["`git rev-parse HEAD:<path>` and `git rev-parse template/main:<path>`",
                       "`git cat-file -p template/main:.gitignore`",
                       "`git rev-list --format=%s HEAD..<remote>/student`",
                       "`git merge-base HEAD <remote>/student`",
                       "list what is staged with `git status --porcelain`",
                       "read `git cat-file -p :<file>` beside `git cat-file -p HEAD:<file>`",
                       "read both and compare them yourself, ignoring line endings"]:
            self.assertIn(phrase, t)

    def test_the_checkpoint_names_its_replacements(self):
        t = text("aibl-checkpoint")
        self.assertIn("`git rev-list --format=%s HEAD -- <file>`", t)
        self.assertIn("`git cat-file -p <commit>:<file>`", t)


class SameChecks(unittest.TestCase):
    """The replacement reads see what git diff and git log saw, on a throwaway repo."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=str(base / "gitconfig"), GIT_TERMINAL_PROMPT="0")
        (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n[core]\n\tautocrlf = false\n")
        self.repo = base / "wb"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        for rel, body in {"a/one.md": "1\n", "a/two.md": "2\n", "workforce/HOUSE.md": "h\n", "gone.md": "x\n"}.items():
            self.write(rel, body)
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-q", "-b", "student")
        self.write("a/two.md", "2 changed\n")
        self.write("a/three.md", "3\n")
        (self.repo / "gone.md").unlink()
        self.git("add", "-A")
        self.git("commit", "-qm", "Week 2 arrives")
        self.git("checkout", "-q", "main")
        self.write("workforce/HOUSE.md", "h2\n")
        self.git("commit", "-qam", "student edit")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True, capture_output=True, text=True).stdout

    def write(self, rel, body):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode())

    def tree(self, rev):
        out = {}
        for line in self.git("ls-tree", "-r", rev).splitlines():
            meta, path = line.split("\t", 1)
            out[path] = meta.split()[2]
        return out

    def changed(self, a, b):
        ta, tb = self.tree(a), self.tree(b)
        return sorted(p for p in set(ta) | set(tb) if ta.get(p) != tb.get(p))

    def test_incoming_paths_match_diff_three_dots(self):
        base = self.git("merge-base", "HEAD", "student").strip()
        old = sorted(self.git("diff", "--name-only", "HEAD...student").split())
        self.assertEqual(self.changed(base, "student"), old)
        self.assertEqual(old, ["a/three.md", "a/two.md", "gone.md"])

    def test_student_edits_match(self):
        base = self.git("merge-base", "HEAD", "student").strip()
        self.assertEqual(self.changed(base, "HEAD"), sorted(self.git("diff", "--name-only", base, "HEAD").split()))

    def test_messages_match_log(self):
        rl = [l for l in self.git("rev-list", "--format=%s", "HEAD..student").splitlines() if not l.startswith("commit ")]
        self.assertEqual(rl, self.git("log", "--format=%s", "HEAD..student").splitlines())

    def test_history_of_one_file_matches_log(self):
        rl = [l for l in self.git("rev-list", "--format=%s", "HEAD", "--", "workforce/HOUSE.md").splitlines()
              if not l.startswith("commit ")]
        self.assertEqual(rl, self.git("log", "--format=%s", "--", "workforce/HOUSE.md").splitlines())

    def test_house_change_seen_by_rev_parse(self):
        before = self.git("rev-parse", f"{self.base}:workforce/HOUSE.md").strip()
        now = self.git("rev-parse", "HEAD:workforce/HOUSE.md").strip()
        self.assertNotEqual(before, now)
        self.assertEqual(self.git("diff", "--name-only", self.base, "HEAD", "--", "workforce/HOUSE.md").split(),
                         ["workforce/HOUSE.md"])

    def test_staged_merge_listed_by_status(self):
        self.git("merge", "--no-ff", "--no-commit", "student")
        status = sorted(l[3:] for l in self.git("status", "--porcelain").splitlines())
        self.assertEqual(status, sorted(self.git("diff", "--cached", "--name-only").split()))
        self.assertEqual(self.git("cat-file", "-p", ":a/two.md"), "2 changed\n")
        self.assertEqual(self.git("cat-file", "-p", "HEAD:a/two.md"), "2\n")


if __name__ == "__main__":
    unittest.main()
