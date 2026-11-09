"""A Cohort 2 first-timer is never asked to start the course from the beginning (student report, 11-09-2026).

A Cohort 2 student who enrolled on the first version's files (before 11-04) and did Week 1 there read as
returning_v1 in the course's own check, so step 6.1 asked "Would you like to take it from the beginning?".
Step 6.1 now also needs a course note saved before Cohort 2 opened (10-26-2026), read with git rev-list,
which is read only and off the team settings' ask list. Run here on a Cohort 2 and a Cohort 1 workbench.
"""
import os, re, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ["work/course/staff/progress.md", "work/course/staff/founder-brief.md", "work/course/staff/before-picture.md",
         ":(glob)work/course/staff/**/continuation*.json", ":(glob)work/course/staff/first-run/**"]
CHECK = ("`git rev-list -1 --before=2026-10-26T00:00:00 HEAD -- " + " ".join(SPECS[:3]) + " '" + SPECS[3] + "' '" + SPECS[4] + "'` prints a commit")


def skill():
    texts = [(ROOT / app / "skills/aibl-update/SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert texts[0] == texts[1]
    return texts[0]


class Words(unittest.TestCase):
    def test_step_6_1_asks_only_when_a_note_predates_cohort_2(self):
        six_one = re.search(r"^6\.1\. \*\*.*?$", skill(), flags=re.M).group(0)
        self.assertIn("and only when a course note was saved before Cohort 2 opened: " + CHECK + ".", six_one)
        self.assertIn("so they are never asked, whatever the state says.", six_one)
        self.assertNotIn("git log", CHECK)


class TheCheck(unittest.TestCase):
    def git(self, repo, *args, date=None):
        env = dict(os.environ)
        if date:
            env.update(GIT_AUTHOR_DATE=date + "T12:00:00", GIT_COMMITTER_DATE=date + "T12:00:00")
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def save(self, repo, files, date):
        for name, body in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-qm", "Save my work", date=date)

    def early(self, repo):
        return bool(self.git(repo, "rev-list", "-1", "--before=2026-10-26T00:00:00", "HEAD", "--", *SPECS).strip())

    def test_cohort_2_is_not_asked_and_cohort_1_is(self):
        with tempfile.TemporaryDirectory() as d:
            wb = Path(d) / "wb"
            wb.mkdir()
            self.git(wb, "init", "-q", "-b", "main")
            self.save(wb, {"README.md": "# My workbench\n"}, "2026-08-01")
            self.save(wb, {"work/course/staff/founder-brief.md": "My recurring job\n",
                           "work/course/staff/continuation-anw-l08.json": "{}\n"}, "2026-11-08")
            self.assertFalse(self.early(wb))
            self.save(wb, {"work/course/staff/first-run/continuation.json": "{}\n"}, "2026-10-02")
            self.assertTrue(self.early(wb))


if __name__ == "__main__":
    unittest.main()
