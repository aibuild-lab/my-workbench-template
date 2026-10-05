"""Where the ask-before-sending rules end up for a student whose aibl-update predates the settings step.

The student's session loads aibl-update before step 2 refreshes it, so the first update after a
program adds its team-settings step runs the OLD instructions: it merges the program and never adds
the settings. This rehearses that exact path from the published template (main at c72d128, the
last commit before the step existed): the old skill's step 2 takes the template's core files, its
step 6 merges the new edition, and settings stay as they were. The next new conversation's
SessionStart hook (the refreshed update-check.mjs, which the published settings already invoke)
runs the program's read-only preview and tells the student the ask rules are missing; the new
aibl-update, now on disk, adds them on a yes. The program here is a fixture that keeps the preview
contract; the real merge script is tested in agent-native-workforce-internal
(tests/test_program_settings.py).
"""
import io, json, os, subprocess, tarfile, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = "c72d1286b8af64488f62f4bd17b78ee1d75128c3"  # template main before the settings step (#15 merge)
OFFICIAL = {"agent-workforce": "https://github.com/aibuild-lab/agent-workforce.git",
            "template": "https://github.com/aibuild-lab/my-workbench-template.git"}
CORE = [f"{app}/skills/{name}" for app in (".claude", ".agents")
        for name in ("aibl-personalize", "aibl-checkpoint", "aibl-enroll", "aibl-update")] + [".claude/hooks/update-check.mjs"]
SEND = "mcp__fixture__send_message"
# The program's merge script, reduced to the same contract as the real one
# (agent-native-workforce-internal, workforce/house/settings-merge.mjs): no arguments is a read-only
# JSON preview with preview_sha256, the hash of the current bytes and the exact new file; --apply
# writes only with --expect equal to that hash, and otherwise refuses and writes nothing.
FIXTURE_MERGE = r"""
import fs from 'node:fs';
import { createHash } from 'node:crypto';
const sha = (t) => createHash('sha256').update(t).digest('hex');
const file = '.claude/settings.json';
const raw = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
const s = raw ? JSON.parse(raw) : {};
const ask = (s.permissions && s.permissions.ask) || [];
const missing = ask.includes('%s') ? [] : [{ where: 'permissions.ask', value: '%s', why: 'asks before sending' }];
const next = JSON.parse(JSON.stringify(s));
if (missing.length) { next.permissions = next.permissions || {}; next.permissions.ask = [...ask, '%s']; }
const text = JSON.stringify(next, null, 2) + '\n';
const status = missing.length ? 'would_add' : 'in_step';
const preview = status === 'in_step' ? null : sha((raw === null ? 'absent' : sha(raw)) + '\n' + text);
const say = (o, code) => { console.log(JSON.stringify(o)); process.exit(code); };
if (!process.argv.includes('--apply')) say({ status, adds: missing, preview_sha256: preview }, 0);
const i = process.argv.indexOf('--expect');
const expect = i >= 0 ? process.argv[i + 1] : undefined;
if (!expect) say({ status: 'usage' }, 1);
if (status === 'in_step') say({ status }, 0);
if (expect !== preview) say({ status: 'changed_since_preview' }, 1);
fs.writeFileSync(file, text);
say({ status: 'applied', adds: missing }, 0);
""" % (SEND, SEND, SEND)


class PublishedUpdateThenSettings(unittest.TestCase):
    def setUp(self):
        # The published commit is the whole point of this test: a clone without it fetches it, and a
        # failed fetch fails the test (never a skip).
        present = lambda: subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", PUBLISHED + "^{commit}"],
                                         capture_output=True, timeout=60).returncode == 0
        if not present():
            r = subprocess.run(["git", "-C", str(ROOT), "fetch", "-q", "origin", PUBLISHED], capture_output=True, text=True, timeout=300)
            self.assertTrue(present(), f"the published template commit {PUBLISHED} is missing and could not be fetched: {r.stderr}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def git(self, repo, *args):
        r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def repo(self, name, branch):
        p = self.base / name
        p.mkdir()
        self.git(p, "init", "-q", "-b", branch)
        return p

    def write(self, repo, files):
        for name, body in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body if isinstance(body, bytes) else body.encode())

    def extract(self, rev, dest, source=ROOT):
        raw = subprocess.run(["git", "-C", str(source), "archive", "--format=tar", rev], capture_output=True, timeout=120).stdout
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            tar.extractall(dest, filter="data")

    def remote_git(self, *args):
        """Fetch through the official URLs, redirected to the local fixtures for this one command."""
        return self.git(self.wb, "-c", f"url.{self.course}.insteadOf={OFFICIAL['agent-workforce']}",
                        "-c", f"url.{self.template}.insteadOf={OFFICIAL['template']}", *args)

    def hook(self, *args):
        """The SessionStart command the workbench's own settings run, in a new conversation."""
        settings = json.loads((self.wb / ".claude/settings.json").read_text(encoding="utf-8"))
        command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertEqual(command, 'node "$CLAUDE_PROJECT_DIR/.claude/hooks/update-check.mjs"')
        home = self.base / "home"
        home.mkdir(exist_ok=True)
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "CLAUDE_PROJECT_DIR": str(self.wb), "GIT_ALLOW_PROTOCOL": "file", "GIT_TERMINAL_PROMPT": "0",
               "AIBL_UPDATE_CHECK_TIMEOUT_MS": "5000"}
        payload = {"session_id": str(uuid.uuid4()), "source": "startup", "cwd": str(self.wb), "hook_event_name": "SessionStart"}
        r = subprocess.run(["node", str(self.wb / ".claude/hooks/update-check.mjs"), *args], input=json.dumps(payload),
                           cwd=self.wb, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_old_skill_update_then_next_conversation_then_new_skill(self):
        # The template as a remote: this branch's files. The program: edition one, then the edition with settings.
        self.template = self.repo("template", "main")
        self.extract("HEAD", self.template)
        self.git(self.template, "add", "-A")
        self.git(self.template, "commit", "-qm", "template with the settings step")
        self.course = self.repo("course", "student")
        self.write(self.course, {"course/workforce/welcome.md": "Welcome\n", ".claude/agents/aibl-chief-of-staff.md": "# Chief\n"})
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "edition one")

        # A workbench exactly as the published template made it, enrolled on edition one.
        self.wb = self.repo("my-workbench", "main")
        self.extract(PUBLISHED, self.wb)
        self.git(self.wb, "add", "-A")
        self.git(self.wb, "commit", "-qm", "my workbench from the published template")
        for remote, url in OFFICIAL.items():
            self.git(self.wb, "remote", "add", remote, url)
        self.remote_git("fetch", "-q", "agent-workforce", "student")
        self.git(self.wb, "merge", "-q", "--allow-unrelated-histories", "--no-ff", "-m", "Add Agent Workforce", "agent-workforce/student")
        published_settings = (self.wb / ".claude/settings.json").read_bytes()

        # The course publishes the edition with its team settings.
        self.write(self.course, {"workforce/house/settings-merge.mjs": FIXTURE_MERGE})
        self.git(self.course, "add", "-A")
        self.git(self.course, "commit", "-qm", "edition with team settings")

        # The OLD aibl-update runs (its text is the published one, loaded before step 2 replaced it).
        old = (self.wb / ".claude/skills/aibl-update/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("settings-merge", old)
        self.assertNotIn("read the new `SKILL.md` now", old)
        # Its step 2: take the template's core files (the recommended answer for unchanged files).
        self.remote_git("fetch", "-q", "template", "main")
        self.git(self.wb, "checkout", "template/main", "--", *CORE)
        self.git(self.wb, "commit", "-qm", "Refresh workbench skills")
        # Its step 6: merge the new edition. Nothing in the old steps touches settings.
        self.remote_git("fetch", "-q", "agent-workforce", "student")
        self.git(self.wb, "merge", "-q", "--no-ff", "-m", "Update Agent Workforce", "agent-workforce/student")
        self.assertEqual((self.wb / ".claude/settings.json").read_bytes(), published_settings)
        self.assertNotIn(SEND, published_settings.decode())  # after the old skill's update: no ask rule yet

        # The next new conversation (old step 6.5 itself starts one): the refreshed hook says so.
        out = json.loads(self.hook())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Agent Workforce's team settings are not in this workbench's .claude/settings.json yet", out)
        self.assertIn("1 send tool has no ask rule", out)
        self.assertIn("adding them only on a yes", out)
        report = json.loads(self.hook("--json"))
        self.assertEqual(report["programs"][0]["team_settings"], {"status": "would_add", "missing_send_asks": [SEND]})

        # The new aibl-update, now the one on disk, runs its settings step even with nothing pending.
        new = (self.wb / ".claude/skills/aibl-update/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("even when step 4 finds zero pending program commits", new)
        self.assertIn("read the new `SKILL.md` now and follow it from step 2.5", new)
        merge = lambda *a: subprocess.run(["node", "workforce/house/settings-merge.mjs", *a], cwd=self.wb, capture_output=True,
                                          text=True, timeout=60)
        before = (self.wb / ".claude/settings.json").read_bytes()
        # Only what was previewed, with the preview's hash: no --expect, or a wrong one, writes nothing.
        for bad in ((), ("--expect", "0" * 64)):
            r = merge("--apply", *bad)
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertEqual((self.wb / ".claude/settings.json").read_bytes(), before)
        preview = json.loads(merge().stdout)
        self.assertEqual(preview["status"], "would_add")
        r = merge("--apply", "--expect", preview["preview_sha256"])
        self.assertEqual(json.loads(r.stdout)["status"], "applied", r.stdout)
        self.git(self.wb, "commit", "-qm", "Add my team's settings", "--", ".claude/settings.json")
        settings = json.loads((self.wb / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertIn(SEND, settings["permissions"]["ask"])
        self.assertEqual(settings["hooks"], json.loads(published_settings)["hooks"])  # the update check is kept
        after = self.hook()
        self.assertNotIn("team settings", after)
        report = json.loads(self.hook("--json"))
        self.assertEqual(report["programs"][0]["team_settings"], {"status": "in_step", "missing_send_asks": []})

    def test_a_program_without_a_settings_script_says_nothing_about_settings(self):
        self.wb = self.repo("my-workbench", "main")
        self.extract("HEAD", self.wb)
        self.git(self.wb, "add", "-A")
        self.git(self.wb, "commit", "-qm", "workbench")
        self.git(self.wb, "remote", "add", "agent-workforce", OFFICIAL["agent-workforce"])
        report = json.loads(self.hook("--json"))
        self.assertIsNone(report["programs"][0].get("team_settings"))


if __name__ == "__main__":
    unittest.main()
