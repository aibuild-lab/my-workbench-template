"""Synthetic Team HQ Git-route rehearsal; no enrollment publication or learner claim."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TeamHQ(unittest.TestCase):
    def test_candidate_stays_held_and_boundaries_are_explicit(self):
        enroll = (ROOT / '.claude/skills/aibl-enroll/SKILL.md').read_text()
        candidate = enroll.split('## Team HQ candidate contract')[1].split('## Steps')[0]
        for text in ('not a current enrollment destination', 'No other `work/` file is allowed',
                     'ignored/untracked collisions', 'Modified supplied files require explicit choices',
                     'never\nreplace it silently', 'Never fetch the private Internal'):
            self.assertIn(text, candidate)
        table = enroll.split('## Current destinations')[1].split('## Team HQ candidate contract')[0]
        self.assertNotIn('| Team HQ |', table)
        hook = (ROOT / '.claude/hooks/update-check.mjs').read_text()
        self.assertNotIn('"agent-team-hq"', hook.split('const PROGRAMS = ')[1].split(';')[0])
        for skill in ('aibl-enroll', 'aibl-update'):
            self.assertEqual((ROOT / f'.claude/skills/{skill}/SKILL.md').read_bytes(),
                             (ROOT / f'.agents/skills/{skill}/SKILL.md').read_bytes())

    def test_git_route_preserves_foundation_repeats_updates_and_aborts_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            def git(repo, *args, ok=True):
                done = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
                if ok: self.assertEqual(done.returncode, 0, done.stderr)
                return done
            def init(name):
                repo = base / name; repo.mkdir()
                git(repo, 'init', '-q', '-b', 'student')
                git(repo, 'config', 'user.name', 'Synthetic reviewer')
                git(repo, 'config', 'user.email', 'fixture@example.invalid')
                return repo
            def write(repo, path, data):
                file = repo / path; file.parent.mkdir(parents=True, exist_ok=True); file.write_text(data)
            def commit(repo, title):
                git(repo, 'add', '.'); git(repo, 'commit', '-qm', title)
            workbench, program = init('workbench'), init('program')
            foundation = {'context/project.md': 'My project\n', 'library/reference.md': 'My source\n',
                          'work/result.md': 'My result\n', 'AGENTS.md': 'My instructions\n',
                          '.claude/settings.json': '{"student":true}\n',
                          '.aibl/template.json': '{"version":"fixture"}\n'}
            for path, data in foundation.items(): write(workbench, path, data)
            commit(workbench, 'Essentials foundation')
            supplied = 'course/team-hq/README.md'
            write(program, supplied, 'Edition one\n')
            write(program, 'team-hq/workflows/personal-hq.md', 'Approved fixture inputs\n')
            write(program, 'work/team-hq/.gitignore', '*\n!.gitignore\n')
            write(program, '.aibl/programs/agent-team-hq.json', json.dumps({'program': 'agent-team-hq', 'version': 'fixture-one'}))
            commit(program, 'Synthetic reviewed Team HQ edition')
            git(workbench, 'remote', 'add', 'agent-team-hq', str(program))
            git(workbench, 'fetch', '-q', 'agent-team-hq', 'student')
            revision = git(workbench, 'rev-parse', 'agent-team-hq/student').stdout.strip()
            git(workbench, 'merge', '--allow-unrelated-histories', '--no-ff', '--no-commit', revision)
            git(workbench, 'commit', '-qm', 'Approved synthetic enrollment')
            before = git(workbench, 'rev-parse', 'HEAD').stdout
            git(workbench, 'merge', '--no-edit', revision)
            self.assertEqual(git(workbench, 'rev-parse', 'HEAD').stdout, before)
            self.assertEqual(git(workbench, 'check-ignore', '-q', 'work/team-hq/research/report.md').returncode, 0)
            write(program, supplied, 'Edition two\n'); commit(program, 'Synthetic update')
            git(workbench, 'fetch', '-q', 'agent-team-hq', 'student')
            git(workbench, 'merge', '--no-ff', '--no-commit', 'agent-team-hq/student')
            git(workbench, 'commit', '-qm', 'Approved synthetic update')
            self.assertEqual((workbench / supplied).read_text(), 'Edition two\n')
            write(workbench, supplied, 'Student edition\n'); commit(workbench, 'Student customization')
            write(program, supplied, 'Edition three\n'); commit(program, 'Overlapping update')
            git(workbench, 'fetch', '-q', 'agent-team-hq', 'student')
            before = git(workbench, 'rev-parse', 'HEAD').stdout
            self.assertNotEqual(git(workbench, 'merge', '--no-ff', '--no-commit', 'agent-team-hq/student', ok=False).returncode, 0)
            git(workbench, 'merge', '--abort')
            self.assertEqual(git(workbench, 'rev-parse', 'HEAD').stdout, before)
            self.assertEqual((workbench / supplied).read_text(), 'Student edition\n')
            for path, data in foundation.items(): self.assertEqual((workbench / path).read_text(), data)


if __name__ == '__main__': unittest.main()
