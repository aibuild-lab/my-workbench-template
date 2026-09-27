"""A program's settings reach the workbench only through the previewed team-settings step.

The workbench owns .claude/settings.json (this template ships it with the update check). A program
never ships that file; Agent Workforce ships workforce/house/settings-merge.mjs instead, and enroll
and update run its preview after the program merge and apply it on the student's yes. Text checks
only: the merge itself is tested in the program's repository (tests/test_program_settings.py).
"""
import json, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProgramSettings(unittest.TestCase):
    def skill(self, name):
        claude = (ROOT / '.claude/skills' / name / 'SKILL.md').read_text(encoding='utf-8')
        self.assertEqual(claude, (ROOT / '.agents/skills' / name / 'SKILL.md').read_text(encoding='utf-8'))
        return claude

    def test_the_template_settings_hold_only_the_update_check(self):
        settings = json.loads((ROOT / '.claude/settings.json').read_text(encoding='utf-8'))
        self.assertEqual(set(settings), {'hooks'})
        commands = [h['command'] for g in settings['hooks']['SessionStart'] for h in g['hooks']]
        self.assertEqual(commands, ['node "$CLAUDE_PROJECT_DIR/.claude/hooks/update-check.mjs"'])

    def test_enroll_previews_then_applies_exactly_what_was_previewed(self):
        text = self.skill('aibl-enroll')
        self.assertIn('node workforce/house/settings-merge.mjs`; it writes nothing', text)
        self.assertIn('node workforce/house/settings-merge.mjs --apply --expect <preview_sha256', text)
        self.assertIn('git add -- .claude/settings.json', text)
        self.assertIn("run step 6's team-settings part", text)
        self.assertIn('git commit -m "Add my team\'s settings" -- .claude/settings.json', text)
        self.assertIn("A program never ships `.claude/settings.json`", text)
        self.assertIn("change permissions (other than step 6's previewed team settings, on a yes)", text)

    def test_update_runs_the_same_step_on_every_update(self):
        text = self.skill('aibl-update')
        self.assertIn("Then add the team's settings exactly as `aibl-enroll` step 6 describes.", text)
        self.assertIn("Run its preview whenever this skill runs", text)
        self.assertIn("A program's own settings never arrive by merge", text)
        self.assertIn('even when step 4 finds zero pending program commits', text)

    def test_enroll_admits_exactly_the_workforce_starter_files(self):
        # Kept in step by hand with agent-native-workforce-internal tests/test_program_settings.py (ENROLL_EXACT).
        text = self.skill('aibl-enroll')
        for name in ('.aibl/programs/agent-workforce.json', '.aibl/workforce-student-edition.json', 'library/README.md',
                     'library/knowledge/README.md', '.mcp.json'):
            self.assertIn('`' + name + '`', text)


if __name__ == '__main__':
    unittest.main()
