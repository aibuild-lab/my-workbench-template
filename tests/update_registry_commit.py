"""The rebuilt registry is saved in its own commit during the update (11-07-2026, Mac walk M5).

Step 6.5 rebuilds workforce/shed/registry.yaml, which rewrites its date every time. The skill said to
include it in the checkpoint at the end, so a student who said no to that save (or whose save
couldn't finish) was left with an unsaved registry, and the next update stopped for a save.
Text checks, and a Git check that the one-file commit leaves the workbench clean.
"""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = 'git commit -m "Rebuild the team registry" -- workforce/shed/registry.yaml'


def update_text():
    a, b = [(ROOT / app / "skills/aibl-update/SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b
    return a


class RegistryText(unittest.TestCase):
    def setUp(self):
        self.step = update_text().split("6.5. **Make the update live.**", 1)[1].split("\n7. **Verify what arrived.**", 1)[0]

    def test_the_rebuild_is_saved_right_away_in_its_own_commit(self):
        self.assertIn("save that one file right away in its own commit, `" + COMMIT + "`, even when only its date changed", self.step)
        self.assertIn("Don't leave it for the checkpoint", self.step)
        self.assertNotIn("include it in the checkpoint at the end of this step", self.step)

    def test_codex_marker_counts_the_commit(self):
        self.assertIn("its commit is one more write after its own plain line", self.step)


class RegistryCommit(unittest.TestCase):
    def test_a_date_only_rebuild_committed_by_path_leaves_the_workbench_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = dict(os.environ, HOME=tmp, USERPROFILE=tmp, GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=str(base / "gitconfig"), GIT_TERMINAL_PROMPT="0")
            (base / "gitconfig").write_text("[user]\n\tname = test\n\temail = test@example.invalid\n")
            wb = base / "wb"
            reg = wb / "workforce/shed/registry.yaml"
            reg.parent.mkdir(parents=True)
            reg.write_bytes(b"generated_on: 2026-10-27\nseats: []\n")
            run = lambda *a: subprocess.run(["git", *a], cwd=wb, env=env, check=True, capture_output=True, text=True).stdout
            run("init", "-q", "-b", "main")
            run("add", "-A")
            run("commit", "-qm", "start")
            (wb / "work/course/staff").mkdir(parents=True)
            (wb / "work/course/staff/continuation-anw-l01.json").write_bytes(b"{}\n")
            reg.write_bytes(b"generated_on: 2026-11-07\nseats: []\n")
            run(*COMMIT.split()[1:3], "Rebuild the team registry", "--", "workforce/shed/registry.yaml")
            self.assertEqual(run("status", "--porcelain", "--untracked-files=all").splitlines(),
                             ["?? work/course/staff/continuation-anw-l01.json"])
            self.assertEqual(run("show", "--name-only", "--format=", "HEAD").split(), ["workforce/shed/registry.yaml"])


if __name__ == "__main__":
    unittest.main()
