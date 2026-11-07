"""aibl-update's last line (WF-119, combined with D160's name-only proof): where the student goes next
is never taken from what arrived.

WF-119 (5fd3a9b, not on main) asked The Professor "Where am I in the course, and what's next?" as the
proof and closed with its reply. D160 (32aa07d) found that an agent called from the update's session
still runs its file from before the update, so the proof asks only the agent's name. This keeps that
proof and WF-119's fallback line as the close (PROVISIONAL, 11-07-2026; undo: revert the commit that
added this file).

Wording only. Nothing here runs an app.
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

    def test_the_proof_asks_only_the_name(self):
        step = self.text.split("6.5. **Make the update live.**", 1)[1].split("\n7. **Verify what arrived.**", 1)[0]
        self.assertIn("only to say its name in one line", step)
        self.assertIn("never ask it about lessons, files or what changed", step)
        self.assertNotIn("Where am I in the course, and what's next?", step)

    def test_the_close_is_the_fallback_line_and_never_names_a_lesson_from_what_arrived(self):
        rules = self.text.split("\n7. **Verify what arrived.**", 1)[1].split("\n## Rules", 1)[0]
        self.assertIn('"To pick up where you left off, open a new conversation with the Professor and ask where you are in the course."', rules)
        self.assertIn("Never name a lesson, module or week as the student's next step from what this update brought", rules)
        self.assertIn("A program without The Professor (The Lab today) gets no such line.", rules)
        self.assertIn("A student who said yes to Start fresh in step 6.1", rules)

    def test_the_agent_menu_step_does_not_say_codex_has_no_menu(self):
        # D174, D182: Codex has an agent list on this version; the step is still Claude Code's alone.
        step = self.text.split("6.5. **Make the update live.**", 1)[1].split("\n7. **Verify what arrived.**", 1)[0]
        self.assertIn("(Claude Code only; skip this in Codex)", step)
        self.assertNotIn("Codex has no such menu", self.text)

    def test_a_refused_menu_copy_is_one_line_and_never_sends_to_permission_settings(self):
        # A walk (11-07) had the update tell the student to add a rule in Claude Code's permission settings.
        step = self.text.split("6.5. **Make the update live.**", 1)[1].split("\n7. **Verify what arrived.**", 1)[0]
        self.assertIn('"I skipped the copy for your agent menu. Nothing is lost, and your agents still work when you ask for them by name."', step)
        self.assertIn("Never send the student to the app's permission settings", step)

    def test_no_em_or_en_dashes(self):
        self.assertNotIn("—", self.text)
        self.assertNotIn("–", self.text)


if __name__ == "__main__":
    unittest.main()
