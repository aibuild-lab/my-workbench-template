"""A returning Cohort 1 student's first update to the new Agent Workforce says what happened, before the preview.

Wade, 11-01 (N4): the first update must say plainly that the course was overhauled from Cohort 1's
feedback, what changed, and what the choice means: start the new version from the beginning, keeping
the agents, the Chief of Staff's name, the connections and the library (recommended; Start fresh by
default), or, partway through a week, finish the first version first and update after. Finishing
first is only possible before the merge, so the three lines come with step 5's preview, and its yes
is a choice with "Not now". Step 6.1's one question then asks without repeating them. Source: the
returning-students proposal of 11-01, section 9 (option B) and the appendix note.

The moment is told apart with read-only checks only: the workbench's commit has no Start fresh
script, the incoming edition has one, and the first version's course notes are there. The Git part
of that is run here on a first-version and a new-version workbench.
"""
import os, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
L1 = "We've overhauled Agent Workforce based on Cohort 1's feedback: new lessons in a new order, new pages on Learn, and updated agents."
L2 = ("Everything you set up carries over: your agents, your Chief of Staff's name, your connections and your library. "
      "After the update I'll ask once whether to start the new version from the beginning (we recommend it) or keep going as you are.")
L3 = "Partway through a week and want to finish the first version first? Choose \"Not now\". That week's pages on Learn stay up until its new version opens."
CHOICE = "1. Update now (recommended) 2. Not now, I'll finish the first version first"
NOTNOW = "Nothing changed. When you've finished, ask me to update, or say yes when I offer it in a new conversation."
SCRIPT = "workforce/runtime/start_fresh.py"
# Student P (11-09): a Cohort 2 first-timer who enrolled on the first version's files and did Week 1 there was
# told the course was overhauled from Cohort 1's feedback and asked to start from the beginning. Only notes
# saved before Cohort 2 opened are Cohort 1's.
COHORT2_CHECK = ("`git rev-list -1 --before=2026-10-26T00:00:00 HEAD -- work/course/staff/progress.md work/course/staff/founder-brief.md "
                 "work/course/staff/before-picture.md ':(glob)work/course/staff/**/continuation*.json' ':(glob)work/course/staff/first-run/**'` prints a commit")
NOTE_SPECS = ["work/course/staff/progress.md", "work/course/staff/founder-brief.md", "work/course/staff/before-picture.md",
              ":(glob)work/course/staff/**/continuation*.json", ":(glob)work/course/staff/first-run/**"]


def skill():
    texts = [(ROOT / app / "skills/aibl-update/SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert texts[0] == texts[1]
    return texts[0]


def step(text, number):
    m = re.search(r"^" + re.escape(number) + r"\. \*\*.*?(?=^\d+(?:\.\d+)?\. \*\*)", text, flags=re.S | re.M)
    return m.group(0)


class Words(unittest.TestCase):
    def test_the_three_lines_come_before_the_preview_with_a_not_now_choice(self):
        five = step(skill(), "5")
        for line in (L1, L2, L3):
            self.assertIn(f"\"{line}\"", five)
        self.assertLess(five.index(L1), five.index(L2))
        self.assertLess(five.index(L2), five.index(L3))
        self.assertIn("as their own message, before the preview", five)
        self.assertIn(f"ask for the yes as this choice: \"{CHOICE}\"", five)
        self.assertIn(f"On 2, change nothing, say \"{NOTNOW}\" and stop this update.", five)
        self.assertIn("Say the three lines once in an update; step 6.1 then asks its question without them.", five)

    def test_the_lines_say_what_wade_asked_and_stay_short(self):
        joined = " ".join((L1, L2, L3))
        for must in ("overhauled", "Cohort 1's feedback", "new lessons", "your agents", "your Chief of Staff's name",
                     "your connections", "your library", "from the beginning (we recommend it)", "finish the first version first"):
            self.assertIn(must, joined)
        for line in (L1, L2, L3):
            self.assertLessEqual(len(line.split()), 45, line)
            self.assertNotRegex(line, r"\b[A-Z]{2,}\b")
            self.assertNotIn("`", line)
        self.assertNotIn("\u2014", joined)
        self.assertNotIn("\u2013", joined)

    def test_only_a_returning_students_first_update_hears_them(self):
        five = step(skill(), "5")
        self.assertIn("`git cat-file -e HEAD:workforce/runtime/start_fresh.py` fails", five)
        self.assertIn("`git cat-file -e <remote>/student:workforce/runtime/start_fresh.py` succeeds", five)
        self.assertIn("holds course notes from the first version's lessons", five)
        self.assertIn("hears none of this", five)

    def test_a_cohort_2_first_timer_is_never_told_to_start_over(self):
        five, six_one = step(skill(), "5"), step(skill(), "6.1")
        self.assertIn("and one of them was saved before Cohort 2 opened: " + COHORT2_CHECK + ".", five)
        self.assertIn("so they are never told to start over", five)
        self.assertIn("a Cohort 2 student whose notes were all saved on or after 10-26-2026) hears none of this.", five)
        self.assertIn("and only when step 5's Cohort 2 check", six_one)
        self.assertIn("A Cohort 2 student is taking the course for the first time, so they are never asked, whatever the state says.", six_one)
        self.assertNotIn("git log", COHORT2_CHECK)  # read-only and off the ask list (D232)

    def test_the_question_recommends_starting_fresh_and_can_open_with_the_first_line(self):
        six_one = step(skill(), "6.1")
        self.assertIn("1. Yes, start from the beginning (recommended) 2. No, keep going as I am\"", six_one)
        self.assertIn("your agents, your Chief of Staff's name, your connections and your library keep working", six_one)
        self.assertIn(f"open the same message with step 5's first line, word for word: \"{L1}\"", six_one)


class TheMoment(unittest.TestCase):
    """The Git half of the check, on a first-version and a new-version workbench."""

    def git(self, repo, *args, check=True):
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                           capture_output=True, text=True, timeout=120)
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def commit(self, repo, files, message, date=None):
        for name, body in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        self.git(repo, "add", "-A")
        if date:
            stamp = date + "T12:00:00"
            r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                                "-c", "commit.gpgsign=false", "commit", "-qm", message], capture_output=True, text=True,
                               timeout=120, env=dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        else:
            self.git(repo, "commit", "-qm", message)

    def is_first_update(self, wb):
        has = lambda ref: self.git(wb, "cat-file", "-e", f"{ref}:{SCRIPT}", check=False).returncode == 0
        notes = any((wb / "work/course/staff" / n).exists() for n in ("progress.md", "founder-brief.md", "before-picture.md"))
        early = self.git(wb, "rev-list", "-1", "--before=2026-10-26T00:00:00", "HEAD", "--", *NOTE_SPECS).stdout.strip()
        return not has("HEAD") and has("agent-workforce/student") and notes and bool(early)

    def test_a_first_version_workbench_with_notes_is_the_moment_and_a_new_version_one_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            course, v1, v2 = base / "course", base / "v1", base / "v2"
            for repo, branch in ((course, "student"), (v1, "main"), (v2, "main")):
                repo.mkdir()
                self.git(repo, "init", "-q", "-b", branch)
            self.commit(course, {"course/workforce/lessons/anw-l01.md": "first version\n"}, "First version")
            for wb in (v1, v2):
                self.git(wb, "remote", "add", "agent-workforce", str(course))
                self.git(wb, "fetch", "-q", "agent-workforce", "student")
                self.git(wb, "merge", "-q", "--allow-unrelated-histories", "-m", "Add Agent Workforce", "agent-workforce/student")
                self.commit(wb, {"work/course/staff/progress.md": "Lesson 3 done\n"}, "Save my work", date="2026-09-25")
            self.commit(course, {SCRIPT: "# start fresh\n"}, "New version")
            for wb in (v1, v2):
                self.git(wb, "fetch", "-q", "agent-workforce", "student")
            self.git(v2, "merge", "-q", "-m", "Bring the new version in", "agent-workforce/student")
            self.assertTrue(self.is_first_update(v1))
            self.assertFalse(self.is_first_update(v2))          # already on the new version
            (v1 / "work/course/staff/progress.md").unlink()       # never saved a lesson: nothing to say
            self.assertFalse(self.is_first_update(v1))

    def test_a_cohort_2_first_timer_on_the_first_version_files_is_not_the_moment(self):
        """Student P: enrolled on the first version's branch, Week 1 saved 11-02 to 11-08: a first run, not a return."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            course, wb = base / "course", base / "wb"
            for repo, branch in ((course, "student"), (wb, "main")):
                repo.mkdir()
                self.git(repo, "init", "-q", "-b", branch)
            self.commit(course, {"course/workforce/lessons/anw-l01.md": "first version\n"}, "First version", date="2026-10-29")
            self.git(wb, "remote", "add", "agent-workforce", str(course))
            self.git(wb, "fetch", "-q", "agent-workforce", "student")
            self.git(wb, "merge", "-q", "--allow-unrelated-histories", "-m", "Add Agent Workforce", "agent-workforce/student")
            self.commit(wb, {"work/course/staff/founder-brief.md": "My recurring job\n",
                             "work/course/staff/continuation-anw-l08.json": "{}\n"}, "Save my work", date="2026-11-08")
            self.commit(course, {SCRIPT: "# start fresh\n"}, "New version", date="2026-11-04")
            self.git(wb, "fetch", "-q", "agent-workforce", "student")
            self.assertFalse(self.is_first_update(wb))
            # the same workbench with one note saved during Cohort 1 is a returning student
            self.commit(wb, {"work/course/staff/first-run/continuation.json": "{}\n"}, "Cohort 1 save", date="2026-10-02")
            self.assertTrue(self.is_first_update(wb))


if __name__ == "__main__":
    unittest.main()
