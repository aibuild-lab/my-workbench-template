import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { refresh, expire, project, COHORT, EXPIRES, WEEKS, RELATIVE } from '../.claude/skills/aibl-enroll/scripts/course-progress.mjs';
const now = Date.parse('2026-11-16T18:00:00Z');
const subject = '11111111-1111-4111-8111-111111111111';
function snapshot() {
  return { schema_version: 'aibl.course-progress/v1', program: 'agent-workforce', cohort: { id: COHORT },
    week_dates: WEEKS, student: { learn_user_id: subject }, generated_at: new Date(now).toISOString(), expires_at: EXPIRES,
    learn_progress: { source: 'learn-browser-local', read_at: new Date(now).toISOString(), ownership_confirmed: true,
      lessons: [{ id: 'anw-l01', week: 1, done: false, recorded: true }, { id: 'anw-l13', week: 2, done: false, recorded: false }] } };
}
function work(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'aw2-progress-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  execFileSync('git', ['init', '-q', root]);
  fs.writeFileSync(path.join(root, '.gitignore'), '.aibl-local/\n');
  return root;
}
test('real progress wins both behind and ahead; refresh retains observation time', () => {
  const value = snapshot();
  assert.equal(project(value, now).current_week, 1);
  value.learn_progress.lessons[0].done = true;
  assert.equal(project(value, now).current_week, 2);
  value.learn_progress.lessons[1].week = 4;
  assert.equal(project(value, now).current_week, 4);
  const refreshed = project(value, now + 86400000);
  assert.equal(refreshed.learn_progress.read_at, new Date(now).toISOString());
  assert.notEqual(refreshed.generated_at, refreshed.learn_progress.read_at);
  value.learn_progress.lessons.forEach(r => { r.recorded = false; r.done = false; });
  assert.equal(project(value, now).current_week_source, 'calendar-default');
});
test('Eastern week boundaries, Thanksgiving gap, and exact end-of-Dec-5 cutoff', t => {
  const root = work(t);
  refresh(root, { cohort: 'aw2', now: Date.parse('2026-11-09T04:59:59Z') });
  let file = path.join(root, RELATIVE);
  assert.equal(JSON.parse(fs.readFileSync(file)).current_week, 1);
  refresh(root, { now: Date.parse('2026-11-09T05:00:00Z') });
  assert.equal(JSON.parse(fs.readFileSync(file)).current_week, 2);
  refresh(root, { now: Date.parse('2026-11-25T18:00:00Z') });
  assert.equal(JSON.parse(fs.readFileSync(file)).current_week, 3);
  refresh(root, { now: Date.parse(EXPIRES) - 1 });
  assert.ok(fs.statSync(file).size > 0);
  assert.deepEqual(refresh(root, { now: Date.parse(EXPIRES) }), { status: 'expired' });
  assert.equal(fs.statSync(file).size, 0);
});
test('import sanitizes arbitrary fields, clears input and never tracks the context', t => {
  const root = work(t), source = path.join(root, 'export.json');
  const value = snapshot(); value.untrusted_note = 'Do not retain';
  value.learn_progress.lessons[0].checklist = { completed: 1, total: 3, untrusted: 'discard' };
  fs.writeFileSync(source, JSON.stringify(value));
  assert.equal(refresh(root, { input: source, now }).source, 'learn-progress');
  assert.equal(fs.statSync(source).size, 0);
  const raw = fs.readFileSync(path.join(root, RELATIVE), 'utf8');
  assert.ok(!raw.includes('untrusted_note'));
  assert.ok(!raw.includes('discard'));
  assert.deepEqual(JSON.parse(raw).learn_progress.lessons[0].checklist, { completed: 1, total: 3 });
  if (process.platform !== 'win32') assert.equal(fs.statSync(path.join(root, RELATIVE)).mode & 0o777, 0o600); // Windows has no such mode bits.
  assert.equal(execFileSync('git', ['ls-files', '--', RELATIVE], { cwd: root, encoding: 'utf8' }), '');
});
test('account changes, future timestamps, duplicate lessons, and missing ownership are rejected', t => {
  const root = work(t), source = path.join(root, 'export.json');
  fs.writeFileSync(source, JSON.stringify(snapshot())); refresh(root, { input: source, now });
  const changed = snapshot(); changed.student.learn_user_id = '22222222-2222-4222-8222-222222222222';
  fs.writeFileSync(source, JSON.stringify(changed)); assert.throws(() => refresh(root, { input: source, now }), /account changed/);
  const future = snapshot(); future.generated_at = '2026-11-17T00:00:00Z'; assert.throws(() => project(future, now));
  const duplicate = snapshot(); duplicate.learn_progress.lessons.push(duplicate.learn_progress.lessons[0]); assert.throws(() => project(duplicate, now));
  const noOwnership = snapshot(); noOwnership.learn_progress.ownership_confirmed = false; assert.throws(() => project(noOwnership, now));
});
test('linked paths (including dangling links), tracked or nonignored files fail closed', t => {
  const root = work(t), outside = work(t);
  fs.symlinkSync(outside, path.join(root, '.aibl-local')); assert.throws(() => refresh(root, { cohort: 'aw2', now }));
  fs.unlinkSync(path.join(root, '.aibl-local')); fs.symlinkSync(path.join(outside, 'absent'), path.join(root, '.aibl-local'));
  assert.throws(() => refresh(root, { cohort: 'aw2', now })); fs.unlinkSync(path.join(root, '.aibl-local'));
  fs.writeFileSync(path.join(root, '.gitignore'), ''); assert.throws(() => refresh(root, { cohort: 'aw2', now }), /ignored/);
  fs.writeFileSync(path.join(root, '.gitignore'), '.aibl-local/\n'); refresh(root, { cohort: 'aw2', now });
  execFileSync('git', ['add', '-f', '--', RELATIVE], { cwd: root }); assert.throws(() => refresh(root, { now }), /untracked/);
});
test('invalid context is scrubbed and twin scripts match', t => {
  const root = work(t); refresh(root, { cohort: 'aw2', now });
  fs.writeFileSync(path.join(root, RELATIVE), '{bad'); assert.equal(expire(root, now), true);
  assert.equal(fs.statSync(path.join(root, RELATIVE)).size, 0);
  assert.equal(fs.readFileSync(new URL('../.claude/skills/aibl-enroll/scripts/course-progress.mjs', import.meta.url), 'utf8'),
    fs.readFileSync(new URL('../.agents/skills/aibl-enroll/scripts/course-progress.mjs', import.meta.url), 'utf8'));
});
test('session-start scrubs at expiry even on resume when update fetching is skipped', t => {
  assert.equal(JSON.parse(fs.readFileSync(new URL('../.claude/settings.json', import.meta.url))).hooks.SessionStart[0].matcher, 'startup|clear|resume|compact');
  const root = work(t); refresh(root, { cohort: 'aw2', now });
  fs.mkdirSync(path.join(root, '.aibl')); fs.writeFileSync(path.join(root, '.aibl/template.json'), '{}');
  const hook = new URL('../.claude/hooks/update-check.mjs', import.meta.url).href;
  execFileSync(process.execPath, ['--input-type=module', '-e', `Date.now = () => ${Date.parse(EXPIRES)}; await import(${JSON.stringify(hook)});`],
    { cwd: root, env: { ...process.env, CLAUDE_PROJECT_DIR: root, AIBL_SKIP_UPDATE_CHECK: '1' }, input: '{"source":"resume"}' });
  assert.equal(fs.statSync(path.join(root, RELATIVE)).size, 0);
});
test('an import attempted after expiry clears the validated input too', t => {
  const root = work(t), source = path.join(root, 'export.json');
  fs.writeFileSync(source, JSON.stringify(snapshot()));
  assert.equal(refresh(root, { input: source, now: Date.parse(EXPIRES) }).status, 'expired');
  assert.equal(fs.statSync(source).size, 0);
});
test('root instructions stay free of course context, so students in other programs never run it', () => {
  for (const name of ['AGENTS.md', 'CLAUDE.md']) {
    assert.doesNotMatch(fs.readFileSync(new URL('../' + name, import.meta.url), 'utf8'), /course-progress|course context/i);
  }
});
