"""aibl-checkpoint step 2.5 and step 4: a save runs the course's privacy check when the workbench has it (D207),
and refuses on an Agent Workforce workbench whose check is missing (D210).

The text checks always run. The behaviour checks need the course's script, which lives in
agent-native-workforce-internal (workforce/runtime/privacy_check.py) and not in this template:
set AIBL_PRIVACY_CHECK to its path to run them, for example

    AIBL_PRIVACY_CHECK=../agent-native-workforce-internal/student/agent-workforce/workforce/runtime/privacy_check.py \
        python3 tests/checkpoint_privacy_check.py

Each behaviour check copies this template's tracked files into a throwaway folder, makes it a Git
folder, puts the script at workforce/runtime/privacy_check.py and runs the commands the skill tells
the agent to run, in its order: gate, stage the named files, staged, commit.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = os.environ.get('AIBL_PRIVACY_CHECK')
CHECK = 'workforce/runtime/privacy_check.py'
# The course's own enrollment stamps (agent-native-workforce-internal, workforce/runtime/start_fresh.py, STAMPS).
STAMPS = ('.aibl/programs/agent-workforce.json', '.aibl/workforce-student-edition.json')
REFUSAL = ('"I didn\'t save. This workbench has Agent Workforce, but the course\'s privacy check '
           '(workforce/runtime/privacy_check.py) is missing, so I can\'t make sure your customer mail and job records '
           'stay out of the save. To bring it back, run the update paste on Agent Workforce card 0.3, Get your '
           'organization, in Learn. Then ask me to save again. If you see this again after the update, post in the '
           'course channel and the course team will help you bring it back."')


def read():
    a, b = [(ROOT / app / 'skills/aibl-checkpoint/SKILL.md').read_text(encoding='utf-8') for app in ('.claude', '.agents')]
    assert a == b, 'the two aibl-checkpoint copies differ'
    return a


class Text(unittest.TestCase):
    def test_runs_the_course_check_only_on_a_workforce_workbench(self):
        text = read()
        self.assertIn("2.5. **The course's privacy check.** First look whether this is an Agent Workforce workbench: "
                      "it is when either of the course's enrollment stamps exists in this folder, "
                      "`.aibl/programs/agent-workforce.json` or `.aibl/workforce-student-edition.json`, "
                      "or when `workforce/runtime/privacy_check.py` exists.", text)
        self.assertIn("Only look at whether these files exist; don't open them.", text)
        self.assertIn('When none of the three exists (Camp, Essentials, Team HQ, or no program), skip this step and the '
                      'check in step 4.', text)
        self.assertIn('`python3 workforce/runtime/privacy_check.py gate`', text)
        self.assertIn('Only exit 0 with a printed line that starts `Clear:` is a pass', text)
        self.assertIn('`python3 workforce/runtime/privacy_check.py staged`', text)
        self.assertIn('`python3 workforce/runtime/privacy_check.py staged --unstage`', text)
        self.assertIn('`py -3`', text)
        # the gate comes before staging, the staged look before the commit
        self.assertLess(text.index('privacy_check.py gate'), text.index('4. Stage the named files only'))
        self.assertLess(text.index('privacy_check.py staged`'), text.index('Then commit with the label'))

    def test_a_block_stops_the_save_and_never_touches_files(self):
        text = read()
        self.assertIn('Anything else stops the save before anything is staged', text)
        self.assertIn('A check that could not run never counts as a pass', text)
        self.assertIn('Never delete, move or edit their files, never force-add', text)
        self.assertIn('On a no, the save stays stopped and nothing changes', text)
        self.assertIn('make no commit', text)

    def test_never_edits_a_line_that_undoes_the_protection(self):
        text = read()
        self.assertIn('show them the file and the line number, and tell them how to fix it themselves', text)
        self.assertIn('delete that one line (or the odd character), save the file, then say "save" again', text)
        self.assertIn('ask their course companion for help', text)
        self.assertIn('Never edit or remove that line yourself and never offer to, even if they ask you to.', text)
        self.assertIn('The save stays stopped until they have fixed it and the gate passes.', text)
        self.assertNotIn('let them decide; never edit or remove it yourself', text)

    def test_enrolled_without_the_check_refuses(self):
        text = read()
        self.assertIn('When a stamp exists but `workforce/runtime/privacy_check.py` does not, refuse: make no save, '
                      'stage nothing, and say in plain words: ' + REFUSAL, text)
        # An update does not bring back a check the student's own history deleted, unless that update changes
        # the file (then it is a keep-mine or take-the-program's choice), so the refusal also names the course channel.
        self.assertIn('Give no Git commands for bringing the file back.', text)
        self.assertIn("A missing check never counts as a pass: don't fall back to step 2's list alone, and never write, "
                      'copy, download or restore the check yourself. Nothing is deleted or moved.', text)
        self.assertNotIn(chr(0x2014), text)   # no em dash
        self.assertNotIn(chr(0x2013), text)   # no en dash

    def test_step_two_is_unchanged(self):
        # Workbenches without the course check keep today's list check, word for word.
        self.assertIn('If it lists any other path, stop the checkpoint', read())


def python_cmd():
    return [sys.executable]


def step_2_5(work):
    """Step 2.5's first look, as the skill words it: only whether the files exist, never what is in them."""
    if (work / CHECK).exists():
        return 'run'
    return 'refuse' if any((work / stamp).exists() for stamp in STAMPS) else 'skip'


class Workbench(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name) / 'my-workbench'
        files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).split(b'\0')
        for name in (f.decode() for f in files if f):
            source = ROOT / name
            if source.is_file():
                target = self.work / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'Template')

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, check=True):
        done = subprocess.run(['git', *args], cwd=self.work, capture_output=True, text=True)
        if check and done.returncode:
            raise AssertionError(done.stderr)
        return done.stdout

    def stamp(self, path=STAMPS[0]):
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"synthetic": "stamp"}\n', encoding='utf-8')
        self.git('add', path)
        self.git('commit', '-q', '-m', 'Add a program')

    def install(self):
        target = self.work / CHECK
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SCRIPT, target)
        self.git('add', CHECK)
        self.git('commit', '-q', '-m', 'Course check')

    def check(self, *args):
        done = subprocess.run(python_cmd() + [CHECK, *args], cwd=self.work, capture_output=True, text=True)
        return done.returncode, done.stdout + done.stderr

    def note(self):
        path = self.work / 'context/project.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('Synthetic note.\n', encoding='utf-8')
        return 'context/project.md'



class Routing(Workbench):
    """Needs no course script: which way step 2.5 goes, and what a refusal leaves behind."""

    def test_not_enrolled_saves_as_today(self):
        self.assertEqual(step_2_5(self.work), 'skip')
        self.assertEqual(self.git('ls-files', '--', 'runs/', 'quarantine/', 'logs/'), '')
        self.git('add', '--', self.note())
        self.git('commit', '-q', '-m', 'Synthetic note')
        self.assertEqual(self.git('status', '--short'), '')

    def test_team_hq_stamp_alone_is_not_workforce(self):
        self.stamp('.aibl/programs/agent-team-hq.json')
        self.assertEqual(step_2_5(self.work), 'skip')

    def test_enrolled_and_missing_refuses_and_touches_nothing(self):
        for stamp in STAMPS:
            with self.subTest(stamp=stamp):
                self.stamp(stamp)
                self.note()
                before = self.git('status', '--short')
                self.assertEqual(step_2_5(self.work), 'refuse')
                self.assertEqual(self.git('diff', '--cached', '--name-only'), '')
                self.assertEqual(self.git('status', '--short'), before)
                self.assertTrue((self.work / stamp).is_file())
                self.git('rm', '-q', '--', stamp)
                self.git('commit', '-q', '-m', 'Reset')


@unittest.skipUnless(SCRIPT and Path(SCRIPT).is_file(), 'set AIBL_PRIVACY_CHECK to the course privacy_check.py')
class Behaviour(Workbench):
    def test_enrolled_and_present_runs_the_check(self):
        self.stamp()
        self.install()
        self.assertEqual(step_2_5(self.work), 'run')
        code, out = self.check('gate')
        self.assertEqual(code, 0, out)
        self.assertTrue(any(line.startswith('Clear:') for line in out.splitlines()), out)

    def test_clean_workbench_saves(self):
        self.install()
        code, out = self.check('gate')
        self.assertEqual(code, 0, out)
        self.assertTrue(any(line.startswith('Clear:') for line in out.splitlines()), out)
        self.git('add', '--', self.note())
        code, out = self.check('staged')
        self.assertEqual(code, 0, out)
        self.git('commit', '-q', '-m', 'Synthetic note')
        self.assertEqual(self.git('status', '--short'), '')

    def test_tracked_private_record_stops_before_staging(self):
        self.install()
        private = self.work / 'runs/job-1/customer.md'
        private.parent.mkdir(parents=True)
        private.write_text('Synthetic customer message.\n', encoding='utf-8')
        self.git('add', '-f', 'runs/job-1/customer.md')   # an older workbench saved it before the ignore line
        self.git('commit', '-q', '-m', 'Older snapshot')
        self.note()
        code, out = self.check('gate')
        self.assertEqual(code, 3, out)
        self.assertIn('runs/job-1/customer.md', out)
        self.assertNotIn('Synthetic customer message', out)
        self.assertFalse(any(line.startswith('Clear:') for line in out.splitlines()))
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')
        self.assertTrue(private.is_file())

    def test_missing_ignore_line_stops_before_staging(self):
        self.install()
        ignore = self.work / '.gitignore'
        ignore.write_text(''.join(l for l in ignore.read_text(encoding='utf-8').splitlines(True)
                                  if l.strip() != '/quarantine/'), encoding='utf-8')
        code, out = self.check('gate')
        self.assertEqual(code, 3, out)
        self.assertIn('/quarantine/', out)

    @unittest.skipUnless(os.name == 'nt', 'folder junctions are a Windows case')
    def test_private_file_staged_through_a_junction_is_held_back(self):
        self.install()
        mail = self.work / 'runs/inbox/mail.md'
        mail.parent.mkdir(parents=True)
        mail.write_text('Synthetic mail.\n', encoding='utf-8')
        subprocess.check_call(['cmd', '/c', 'mklink', '/J', 'notes', 'runs\\inbox'], cwd=self.work,
                              stdout=subprocess.DEVNULL)
        code, out = self.check('gate')
        self.assertEqual(code, 0, out)
        self.git('add', '--', 'notes/mail.md')
        code, out = self.check('staged')
        self.assertEqual(code, 3, out)
        self.assertIn('notes/mail.md', out)
        code, out = self.check('staged', '--unstage')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')
        self.assertTrue(mail.is_file())
        os.rmdir(self.work / 'notes')    # the junction only; the folder it points to stays


if __name__ == '__main__':
    unittest.main()
