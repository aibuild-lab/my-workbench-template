"""aibl-update offers "Tell my assistant about my team" whenever the block is missing, as well as when HOUSE.md changed.

Text checks only: the behavior was walked in `codex exec` from a throwaway workbench without the block (see CHANGELOG 2026-11-06).
Both copies identical; the two conditions and the program's file are in the offer; asks before preparing anything; once per update,
and a no changes nothing; zero pending commits still reaches the offer; step 5's exception says the same.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [ROOT / app / "skills" / "aibl-update" / "SKILL.md" for app in (".claude", ".agents")]


class HouseOffer(unittest.TestCase):
    def setUp(self):
        self.texts = [p.read_text(encoding="utf-8") for p in COPIES]
        self.text = self.texts[0]
        self.offer = next(l for l in self.text.splitlines() if l.lstrip().startswith('- **"Tell my assistant about my team"'))

    def test_copies_identical(self):
        self.assertEqual(self.texts[0], self.texts[1])

    def test_offered_when_missing_or_changed(self):
        self.assertIn("has no `house:begin` line", self.offer)
        self.assertIn("`git ls-tree <pre-update commit> -- workforce/HOUSE.md` and `git ls-tree HEAD -- workforce/HOUSE.md` print different ids", self.offer)
        self.assertIn("workforce/house/compile-house.py", self.offer)

    def test_once_and_a_no_changes_nothing(self):
        self.assertIn("On a no, change nothing and never offer it again in this update", self.offer)

    def test_asks_before_preparing(self):
        self.assertIn("Prepare nothing until the student answers that question", self.offer)
        self.assertIn("`python3 workforce/house/compile-house.py --out-dir .aibl-local/house`", self.offer)
        self.assertIn("(in Codex it needs no permission)", self.offer)
        # robot R6-U and the post-publish check, 11-16-2026: two yeses for one note; now one question, one yes
        self.assertIn("as one question with one yes", self.offer)
        self.assertIn("The student's yes to the question above already covers the copy and the save: ask nothing more about the note.", self.offer)
        self.assertNotIn('ask "Add it?"', self.offer)

    def test_no_temporary_folder_and_no_compare_command(self):
        # robot R4-G, 11-16-2026: a temp folder named to the student, git diff --no-index boxes, a broken compare script
        self.assertNotIn("mkdtemp", self.offer)
        self.assertIn("(no temporary folder, no `git diff`, no `git diff --no-index`, no `diff`, no compare script)", self.offer)
        self.assertIn("with the app's own file reading, and compare them yourself, ignoring line endings", self.offer)

    def test_same_writes_as_enroll(self):
        self.assertIn("follow `aibl-enroll` step 7's checks, with these fixed lines (enroll uses the same ones)", self.offer)
        self.assertIn("`git commit -m \"Tell my assistant about my team\" -- AGENTS.md CLAUDE.md`", self.offer)
        self.assertIn("Any other change stops: say in one plain sentence that their assistant wasn't told about the team", self.offer)

    def test_no_update_still_offers(self):
        step4 = next(l for l in self.text.splitlines() if l.startswith("4. **Check connected programs."))
        self.assertIn('Zero pending commits also still makes step 7\'s "Tell my assistant about my team" offer', step4)

    def test_step5_exception_matches(self):
        self.assertIn("changed `workforce/HOUSE.md` or the block is missing, as its own commit on a separate yes", self.text)


if __name__ == "__main__":
    unittest.main()
