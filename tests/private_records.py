"""Check local-only course records with real Git, including previously tracked files."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PrivateRecords(unittest.TestCase):
    def test_new_private_records_are_ignored_and_existing_tracking_is_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=work, text=True).strip()
            git('init', '-q')
            voice = work / 'work/course/staff/voice-samples.md'
            voice.parent.mkdir(parents=True)
            voice.write_text('Synthetic previously tracked owner writing.\n')
            git('add', str(voice.relative_to(work)))
            shutil.copyfile(ROOT / '.gitignore', work / '.gitignore')
            private = work / 'runs/example/inbound/message.md'
            private.parent.mkdir(parents=True)
            private.write_text('Synthetic customer message.\n')
            progress = work / 'work/course/staff/progress.md'
            progress.write_text('Synthetic saved course return point.\n')
            git('add', '-A')
            staged = git('ls-files').splitlines()
            self.assertNotIn('runs/example/inbound/message.md', staged)
            self.assertIn('work/course/staff/progress.md', staged)
            self.assertEqual(git('ls-files', '--', 'runs/', 'work/course/staff/voice-samples.md'),
                             'work/course/staff/voice-samples.md')
            self.assertTrue(voice.is_file())
            self.assertEqual(git('check-ignore', '--no-index', 'work/course/staff/voice-samples.md'),
                             'work/course/staff/voice-samples.md')
        claude = ROOT / '.claude/skills/aibl-checkpoint/SKILL.md'
        codex = ROOT / '.agents/skills/aibl-checkpoint/SKILL.md'
        self.assertEqual(claude.read_bytes(), codex.read_bytes())
        self.assertIn('git ls-files -- runs/ work/course/staff/voice-samples.md', claude.read_text())


if __name__ == '__main__':
    unittest.main()
