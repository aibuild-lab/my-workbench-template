"""aibl-update's last line (WF-119): where the student goes next comes from The Professor, never from what arrived.

Wording only. Nothing here runs an app, so it doesn't show what a model says at the close, or what The Professor
answers after an update.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [ROOT / d / "skills/aibl-update/SKILL.md" for d in (".claude", ".agents")]


class UpdateClose(unittest.TestCase):
    def setUp(self):
        self.text = COPIES[0].read_text(encoding="utf-8")

    def test_both_app_copies_are_identical(self):
        self.assertEqual(COPIES[0].read_bytes(), COPIES[1].read_bytes())

    def test_the_proof_question_is_where_the_student_is(self):
        step = self.text.split("6.5. **Make the update live.**", 1)[1].split("\n7. **Verify what arrived.**", 1)[0]
        self.assertIn('"Where am I in the course, and what\'s next?"', step)

    def test_the_close_never_names_a_lesson_from_what_arrived(self):
        rules = self.text.split("\n7. **Verify what arrived.**", 1)[1].split("\n## Rules", 1)[0]
        self.assertIn("taken from The Professor's reply in step 6.5", rules)
        self.assertIn("Never name a lesson, module or week from what this update brought", rules)
        self.assertIn('"To pick up where you left off, ask The Professor where you are in the course."', rules)
        self.assertIn("A program without The Professor (The Lab today) gets no such line.", rules)
        self.assertIn("A student who said yes to Start fresh in step 6.1", rules)

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("—", self.text)
        self.assertNotIn("–", self.text)


if __name__ == "__main__":
    unittest.main()
