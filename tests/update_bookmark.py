"""The course's bookmarks don't stop an update (11-07-2026, launch-walks route c).

A student with an unsaved `work/course/staff/continuation-*.json` (the Professor's bookmark) or
`work/course/staff/agent-menu.json` was told to save first, and the save then said the course keeps
that bookmark on this computer: a dead end. The course never ships files under `work/course/staff/`,
so a program merge never touches them, and they are the owner's own records, saved like any file.

Text checks on both skills, and a Git check: a program merge with a new bookmark and a changed one in
the tree goes through and leaves both exactly as they were. Synthetic: throwaway repos and HOME.
"""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICE = '"Your saved place in the course stays as it is. This update doesn\'t touch it, and your next save includes it."'


def read(skill):
    a, b = [(ROOT / app / "skills" / skill / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b, skill
    return a


class BookmarkText(unittest.TestCase):
    def test_update_step_1_lets_the_bookmarks_through_with_one_line(self):
        step = read("aibl-update").split("1. **Check location and work.**", 1)[1].split("\n2. **", 1)[0]
        self.assertIn("`work/course/staff/continuation-*.json` and `work/course/staff/agent-menu.json`, new or changed, don't stop it", step)
        self.assertIn(NOTICE, step)
        self.assertIn("Anything else stops for `aibl-checkpoint`", step)

    def test_update_rule_names_the_exception(self):
        self.assertIn("Never merge over a dirty tree (step 1's private records and course bookmarks aside)", read("aibl-update"))

    def test_checkpoint_saves_the_bookmarks(self):
        text = read("aibl-checkpoint")
        self.assertIn("are the owner's own records and are saved like any other file", text)
        self.assertIn("Never tell the owner the course keeps a bookmark on this computer only.", text)


class BookmarkMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(base), USERPROFILE=str(base), GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=str(base / "gitconfig"), GIT_TERMINAL_PROMPT="0")
        (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n[core]\n\tautocrlf = false\n")
        self.course, self.wb = base / "course", base / "wb"
        self.course.mkdir()
        self.git(self.course, "init", "-q", "-b", "student")
        self.write(self.course, "course/workforce/lesson.md", "week 1\n")
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "week 1")
        self.git(base, "clone", "-q", "-o", "agent-workforce", "-b", "student", str(self.course), str(self.wb))
        self.git(self.wb, "checkout", "-q", "-b", "main")
        self.write(self.wb, "work/course/staff/agent-menu.json", '{"answer": "yes"}\n')
        self.git(self.wb, "add", "work/course/staff/agent-menu.json")
        self.git(self.wb, "commit", "-qm", "saved")
        self.write(self.course, "course/workforce/lesson.md", "week 2\n")
        self.write(self.course, "course/workforce/week2.md", "new\n")
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "week 2")
        self.git(self.wb, "fetch", "-q", "agent-workforce", "student")

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True, text=True).stdout

    def write(self, repo, rel, text):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())

    def test_a_merge_goes_through_and_leaves_the_bookmarks_as_they_were(self):
        self.write(self.wb, "work/course/staff/continuation-anw-l01.json", '{"next": "anw-w2-keep"}\n')
        self.write(self.wb, "work/course/staff/agent-menu.json", '{"answer": "no"}\n')
        status = self.git(self.wb, "status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertEqual(sorted(status), [" M work/course/staff/agent-menu.json",
                                          "?? work/course/staff/continuation-anw-l01.json"])
        self.git(self.wb, "merge", "--no-ff", "--no-commit", "agent-workforce/student")
        self.git(self.wb, "commit", "-qm", "Update Agent Workforce")
        self.assertEqual((self.wb / "course/workforce/week2.md").read_bytes(), b"new\n")
        self.assertEqual((self.wb / "work/course/staff/continuation-anw-l01.json").read_bytes(), b'{"next": "anw-w2-keep"}\n')
        self.assertEqual((self.wb / "work/course/staff/agent-menu.json").read_bytes(), b'{"answer": "no"}\n')
        self.assertNotIn("work/course/staff", self.git(self.wb, "show", "--name-only", "--format=", "HEAD"))
        status = self.git(self.wb, "status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertEqual(sorted(status), [" M work/course/staff/agent-menu.json",
                                          "?? work/course/staff/continuation-anw-l01.json"])


if __name__ == "__main__":
    unittest.main()
