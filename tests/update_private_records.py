"""Private records: untracked ones don't stop an update, and a tracked one gets a way out of the checkpoint's stop (D199).

Text checks only; walked in `codex exec` with a local stand-in origin (see CHANGELOG 2026-11-06).
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(skill):
    a, b = [(ROOT / app / "skills" / skill / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]
    assert a == b, skill
    return a


class PrivateRecords(unittest.TestCase):
    def test_update_leaves_untracked_records_alone(self):
        text = read("aibl-update")
        self.assertIn("apart from untracked paths under `runs/`, `quarantine/`, `logs/` or `library/originals/`", text)
        self.assertIn("leaving those paths out of it", text)

    def test_checkpoint_still_stops_and_offers_a_way_out(self):
        text = read("aibl-checkpoint")
        self.assertIn("stop the checkpoint", text)
        self.assertIn("Stop including them?", text)
        self.assertIn("On a no, the checkpoint stays stopped and nothing changes", text)
        self.assertIn("never `-f` or a folder name", text)
        self.assertIn("its copies go away the next time it pulls", text)

    def test_checkpoint_never_quotes_itself(self):
        self.assertIn("Never tell the student a skill or a procedure requires something", read("aibl-checkpoint"))


if __name__ == "__main__":
    unittest.main()
