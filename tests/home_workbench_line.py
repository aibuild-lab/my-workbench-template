"""The home workbench offer says only what's true about starting agents from another folder.

From a parent or other folder, Codex doesn't find the workbench's agents, and Claude does only
through the student's ~/.claude/agents copy, without this workbench's rules and checks (found by
launch-bonus, 11-07-2026). So neither aibl-enroll's offer nor aibl-update's question may say the
agents or the bridge work from any folder, or that the record lets them find the team from other
folders. Wording only; nothing here runs an app.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FALSE = ["work from any folder", "find your team from other folders", "agents and the bridge work from"]


def copies(name):
    return [(ROOT / app / "skills" / name / "SKILL.md").read_text(encoding="utf-8") for app in (".claude", ".agents")]


class HomeWorkbenchLine(unittest.TestCase):
    def test_no_skill_copy_says_the_agents_work_from_any_folder(self):
        for name in ("aibl-enroll", "aibl-update"):
            for text in copies(name):
                for phrase in FALSE:
                    self.assertNotIn(phrase, text, f"{name}: {phrase}")

    def test_both_offers_say_to_start_the_agents_in_this_folder(self):
        for name in ("aibl-enroll", "aibl-update"):
            claude, codex = copies(name)
            self.assertEqual(claude, codex, name)
            self.assertIn("Start your agents in this folder", claude, name)

    def test_enroll_says_what_happens_from_another_folder(self):
        self.assertIn("from a parent or other folder, Codex doesn't find them", copies("aibl-enroll")[0])


if __name__ == "__main__":
    unittest.main()
