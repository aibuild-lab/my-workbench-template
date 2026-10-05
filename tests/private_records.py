"""Check local-only course records with real Git, including previously tracked files."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

# The root .gitignore lines Week 3's privacy gate requires word for word (agent-native-workforce-internal,
# workforce/runtime/privacy_check.py, PRIVATE_RECORDS). Keep this list in step with that one.
GATE_LINES = (
    '/runs/', '/quarantine/', '/logs/', '*.log', '/library/originals/', '/work/course/staff/voice*',
    '**/*-accounts.yaml', '/.claude/agent-memory-local/', '.aibl-local/', '.env', '.env.*',
    '**/.claude/settings.local.json',
)
# Sample paths each line must cover (a subset of the gate's own probes), and paths that must stay saveable.
STAFF = 'work/course/staff/'
PRIVATE_SAMPLES = (
    'runs/a/b.json', 'runs/inbox/journal.jsonl', 'quarantine/a.pdf', 'quarantine/x/y.docx', 'logs/run.txt',
    'run.log', 'notes/run.log', 'library/originals/gmail/o/m.json', STAFF + 'voice-samples.md',
    STAFF + 'voice-package/a.md', STAFF + 'voice/a/b.md', STAFF + 'mail-accounts.yaml',
    STAFF + 'practice-accounts.yaml', 'a/b/c/bank-accounts.yaml', '.claude/agent-memory-local/chief/n.md',
    '.aibl-local/n.md', '.env', 'sub/.env', '.env.local', '.claude/settings.local.json',
    'sub/.claude/settings.local.json',
)
SAVEABLE = (STAFF + 'owner-profile.yaml', STAFF + 'progress.md', '.env.example', 'context/project.md',
            'library/README.md', '.claude/settings.json')
# The same pathspecs as the course's SKILL_PATHSPECS, quoted the same way.
CHECKPOINT_COMMAND = ('git ls-files -- runs/ quarantine/ logs/ "*.log" library/originals/ "work/course/staff/voice*" '
                      '"*-accounts.yaml" .claude/agent-memory-local/ .aibl-local/ .env ".env.*" .claude/settings.local.json')
# The root .gitignore a workbench made from the template before these rules has (template main at 7a6ba56).
OLDER_GITIGNORE = ('# Local-only files\n.aibl-local/\n.env\n.env.*\n!.env.example\n.claude/settings.local.json\n'
                   '__pycache__/\n*.pyc\n.DS_Store\n')


def missing_template_lines(template_text, workbench_text):
    """aibl-update step 2.5: template lines the workbench lacks word for word, comments included,
    blank lines and ! lines left out, in the template's order."""
    have = set(workbench_text.splitlines())
    return [line for line in template_text.splitlines()
            if line.strip() and not line.startswith('!') and line not in have]


def ignored(work, path):
    """True when the folder's own .gitignore files ignore path (global ignore file left out)."""
    done = subprocess.run(['git', '-c', 'core.excludesFile=', 'check-ignore', '-q', '--no-index', '--', path],
                          cwd=work, capture_output=True)
    if done.returncode not in (0, 1):
        raise AssertionError(done.stderr)
    return done.returncode == 0


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
        self.assertIn(CHECKPOINT_COMMAND, claude.read_text())


    def test_every_line_the_week3_privacy_gate_requires_is_in_the_template(self):
        lines = (ROOT / '.gitignore').read_text().splitlines()
        for line in GATE_LINES:
            self.assertIn(line, lines)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            subprocess.check_call(['git', 'init', '-q'], cwd=work)
            shutil.copyfile(ROOT / '.gitignore', work / '.gitignore')
            for path in PRIVATE_SAMPLES:
                self.assertTrue(ignored(work, path), path)
            for path in SAVEABLE:
                self.assertFalse(ignored(work, path), path)

    def test_checkpoint_stops_on_every_tracked_private_record(self):
        for app in ('.claude', '.agents'):
            text = (ROOT / app / 'skills/aibl-checkpoint/SKILL.md').read_text()
            self.assertIn(CHECKPOINT_COMMAND, text)
            self.assertIn('do not delete files, untrack them or rewrite remote history on their behalf', text)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=work, text=True)
            git('init', '-q')
            for path in (STAFF + 'mail-accounts.yaml', 'quarantine/a.pdf', 'logs/run.txt', STAFF + 'progress.md'):
                (work / path).parent.mkdir(parents=True, exist_ok=True)
                (work / path).write_text('Synthetic.\n')
            git('add', '-A')
            shutil.copyfile(ROOT / '.gitignore', work / '.gitignore')
            listed = git('ls-files', '--', *CHECKPOINT_COMMAND.split(' -- ', 1)[1].replace('"', '').split()).split()
            self.assertEqual(sorted(listed), ['logs/run.txt', 'quarantine/a.pdf', STAFF + 'mail-accounts.yaml'])

    def test_update_brings_the_missing_lines_to_an_older_workbench(self):
        claude = ROOT / '.claude/skills/aibl-update/SKILL.md'
        codex = ROOT / '.agents/skills/aibl-update/SKILL.md'
        self.assertEqual(claude.read_bytes(), codex.read_bytes())
        text = claude.read_text()
        self.assertIn("2.5. **Bring in the template's privacy ignore lines.**", text)
        self.assertIn('follow it from step 2.5', text)
        self.assertIn('do step 2.5 first', text)   # an older copy of this skill says "from step 3"
        template = (ROOT / '.gitignore').read_text()
        missing = missing_template_lines(template, OLDER_GITIGNORE)
        self.assertFalse([line for line in missing if line.startswith('!')])
        merged = OLDER_GITIGNORE + '\n'.join(missing) + '\n'
        self.assertTrue(merged.startswith(OLDER_GITIGNORE))          # nothing already there changes
        for line in GATE_LINES:
            self.assertIn(line, merged.splitlines())
        self.assertEqual(missing_template_lines(template, merged), [])  # a second run adds nothing
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            subprocess.check_call(['git', 'init', '-q'], cwd=work)
            (work / '.gitignore').write_text(merged)
            for path in PRIVATE_SAMPLES:
                self.assertTrue(ignored(work, path), path)
            for path in SAVEABLE:
                self.assertFalse(ignored(work, path), path)


if __name__ == '__main__':
    unittest.main()
