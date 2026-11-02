"""aibl-update step 6: a workforce/ROSTER.md conflict takes the program's copy (11-02), like registry.yaml (10-30)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [ROOT / ".claude/skills/aibl-update/SKILL.md", ROOT / ".agents/skills/aibl-update/SKILL.md"]


class RosterConflict(unittest.TestCase):
    def test_both_apps_take_the_programs_roster_and_reapply_the_name(self):
        texts = [p.read_bytes() for p in COPIES]
        self.assertEqual(texts[0], texts[1])
        step6 = next(l for l in texts[0].decode().splitlines() if l.startswith("6. **Approve and merge.**"))
        self.assertIn("A conflict in `workforce/ROSTER.md` also takes the program's copy without asking", step6)
        self.assertIn("step 6.5's `name_seat.py --reapply` puts back from their name record (`work/course/staff/seat-names.md`)", step6)
        # the registry rule it mirrors is still there, and comes first
        self.assertLess(step6.index("A conflict in `workforce/shed/registry.yaml` takes the program's copy without asking"),
                        step6.index("`workforce/ROSTER.md`"))
        step65 = texts[0].decode().split("6.5. **Make the update live.**", 1)[1]
        self.assertIn("name_seat.py --reapply", step65)


if __name__ == "__main__":
    unittest.main()
