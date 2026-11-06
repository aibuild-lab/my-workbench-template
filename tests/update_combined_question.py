"""aibl-update asks one combined question for what doesn't change how the team works.

Text checks only: the behavior was walked in `codex exec` (see CHANGELOG 2026-11-06). Both copies identical; the fixed words are there;
a customized copy still gets its own question; the update prompt's answer carries over; the course update, team settings and team note
keep their own yes; and the student is never told a skill requires something.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [ROOT / app / "skills" / "aibl-update" / "SKILL.md" for app in (".claude", ".agents")]


class CombinedQuestion(unittest.TestCase):
    def setUp(self):
        self.texts = [p.read_text(encoding="utf-8") for p in COPIES]
        self.text = self.texts[0]
        self.section = self.text.split("## One combined question", 1)[1].split("## Steps", 1)[0]

    def test_copies_identical(self):
        self.assertEqual(self.texts[0], self.texts[1])

    def test_the_words(self):
        self.assertIn("Take all the recommended updates? I can show you the details first. If you say no, everything stays as it is.", self.section)

    def test_customized_copy_keeps_its_own_question(self):
        self.assertIn("gets its own question after this one", self.section)

    def test_the_prompts_answer_carries_over(self):
        self.assertIn("already answered this question in the update prompt, use that answer", self.section)

    def test_what_keeps_its_own_yes(self):
        self.assertIn("The course update's preview in step 6, the team settings and the team note keep their own yes", self.section)

    def test_writes_are_unchanged(self):
        self.assertIn("Only on their yes, append exactly those lines", self.text)
        self.assertIn('as its own commit, "Keep private course records out of save points"', self.text)
        self.assertIn("A yes applies each step exactly as it is written below, with its own commit", self.section)

    def test_a_plain_yes_is_the_one_answer(self):
        self.assertIn('A plain yes, such as "take it", answers the whole list', self.section)

    def test_other_questions_recommend_in_plain_words(self):
        self.assertIn('Every question says in plain words what it does and which answer you recommend', self.text)
        self.assertIn("It's for Claude Code, so it does nothing if you only use Codex", self.text)
        self.assertIn('I recommend yes. Bring it in?', self.text)

    def test_no_quoting_the_skill(self):
        self.assertIn("Never tell the student a skill or a procedure requires something", self.text)


if __name__ == "__main__":
    unittest.main()
