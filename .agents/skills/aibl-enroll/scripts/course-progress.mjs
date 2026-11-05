// Temporary course context. No network, credentials, names, or durable progress ledger.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

export const COHORT = 'bcbe669f-b76d-5eea-a515-dc17cac55eeb';
export const EXPIRES = '2026-12-06T05:00:00.000Z'; // End of Dec 5 in America/New_York.
export const WEEKS = ['2026-11-02', '2026-11-09', '2026-11-16', '2026-11-30'];
export const RELATIVE = '.aibl-local/course-progress.json';
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const SCHEMA = 'aibl.course-progress/v1';

function safeFile(root, relative) {
  root = path.resolve(root);
  let current = path.parse(root).root;
  for (const part of path.relative(current, root).split(path.sep).concat(relative.split('/'))) {
    current = path.join(current, part);
    let stat;
    try { stat = fs.lstatSync(current); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (stat && (stat.isSymbolicLink() || (!stat.isDirectory() && (!stat.isFile() || stat.nlink > 1)))) throw new Error('Linked course context path; stop for review.');
  }
  return current;
}
function parse(file) {
  if (fs.statSync(file).size > 100000) throw new Error('Course context is too large.');
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}
function valid(value, now) {
  if (value?.schema_version !== SCHEMA || value.program !== 'agent-workforce' ||
      value.cohort?.id !== COHORT || value.expires_at !== EXPIRES ||
      JSON.stringify(value.week_dates) !== JSON.stringify(WEEKS) ||
      !Number.isFinite(Date.parse(value.generated_at)) || Date.parse(value.generated_at) > now ||
      Date.parse(value.generated_at) >= Date.parse(EXPIRES)) throw new Error('Invalid or future course context.');
  if (value.student?.learn_user_id != null && !UUID.test(value.student.learn_user_id)) throw new Error('Invalid learner reference.');
  const progress = value.learn_progress;
  if (progress == null) return;
  if (!UUID.test(value.student?.learn_user_id || '') || progress.source !== 'learn-browser-local' ||
      progress.ownership_confirmed !== true || !Number.isFinite(Date.parse(progress.read_at)) ||
      Date.parse(progress.read_at) > now || !Array.isArray(progress.lessons) || progress.lessons.length > 200) throw new Error('Invalid Learn progress.');
  const ids = new Set();
  for (const row of progress.lessons) {
    if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(row.id) || ids.has(row.id) ||
        !Number.isInteger(row.week) || row.week < 0 || row.week > 4 ||
        typeof row.done !== 'boolean' || typeof row.recorded !== 'boolean' || (row.done && !row.recorded)) throw new Error('Invalid lesson record.');
    ids.add(row.id);
    if (row.checklist != null && (!Number.isInteger(row.checklist.total) || row.checklist.total < 0 || row.checklist.total > 1000 ||
        !Number.isInteger(row.checklist.completed) || row.checklist.completed < 0 || row.checklist.completed > row.checklist.total)) throw new Error('Invalid lesson checklist.');
  }
}
export function project(value, now = Date.now()) {
  valid(value, now);
  if (now >= Date.parse(EXPIRES)) return null;
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  const calendar = WEEKS.filter(date => date <= day).length;
  const p = value.learn_progress;
  const lessons = p?.lessons.map(({ id, week, done, recorded, checklist }) => ({ id, week, done, recorded,
    checklist: checklist == null ? null : { completed: checklist.completed, total: checklist.total } }));
  const real = lessons?.some(row => row.recorded);
  const pending = lessons?.find(row => !row.done && row.week > 0); // PROVISIONAL (P31): setup rows never hold a student back. To undo: drop `&& row.week > 0`.
  return {
    schema_version: SCHEMA, program: 'agent-workforce',
    student: { context: 'context/project.md', learn_user_id: value.student?.learn_user_id ?? null },
    cohort: { id: COHORT, label: 'AW2', starts_on: WEEKS[0], ends_on: '2026-12-05', timezone: 'America/New_York' },
    week_dates: WEEKS, calendar_week: calendar,
    current_week: real ? Math.min(Math.max(1, calendar), pending?.week ?? 4) : calendar, // PROVISIONAL (P31): never ahead of the weeks that have opened. To undo: `Math.max(1, pending?.week ?? 4)`.
    current_week_source: real ? 'learn-progress' : 'calendar-default',
    learn_progress: p == null ? null : { source: p.source, ownership_confirmed: true, read_at: p.read_at, lessons },
    generated_at: new Date(now).toISOString(), expires_at: EXPIRES,
  };
}
function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  fs.chmodSync(file, 0o600);
}
// Scrub in place: no Trash copy, backup, tombstone containing identity, or durable history.
export function expire(root, now = Date.now()) {
  const file = safeFile(root, RELATIVE);
  if (!fs.existsSync(file) || !fs.statSync(file).size) return false;
  let expired = now >= Date.parse(EXPIRES);
  try { expired ||= !project(parse(file), now); } catch { expired = true; }
  if (expired) { fs.writeFileSync(file, '', { mode: 0o600 }); return true; }
  return false;
}
export function refresh(root, { input, cohort, now = Date.now() } = {}) {
  const file = safeFile(root, RELATIVE);
  expire(root, now);
  if (now >= Date.parse(EXPIRES)) {
    if (input) {
      const source = safeFile(path.dirname(path.resolve(input)), path.basename(input));
      valid(parse(source), now);
      fs.writeFileSync(source, '', { mode: 0o600 });
    }
    return { status: 'expired' };
  }
  const git = args => spawnSync('git', args, { cwd: root, encoding: 'utf8', timeout: 5000 });
  const ignored = git(['check-ignore', '--no-index', '-q', '--', RELATIVE]);
  const tracked = git(['ls-files', '--', RELATIVE]);
  if (ignored.status !== 0 || tracked.status !== 0 || tracked.stdout.trim()) throw new Error('Course context must be ignored and untracked.');
  let value, inputLeft = false;
  if (input) {
    const source = safeFile(path.dirname(path.resolve(input)), path.basename(input));
    value = parse(source);
    valid(value, now);
    if (fs.existsSync(file) && fs.statSync(file).size) {
      const previous = parse(file);
      if (previous.student?.learn_user_id && previous.student.learn_user_id !== value.student?.learn_user_id) throw new Error('Learn account changed; preserve context for review.');
      if (Date.parse(previous.learn_progress?.read_at) > Date.parse(value.learn_progress?.read_at)) throw new Error('A newer Learn snapshot is already present.');
    }
    value = project(value, now);
    write(file, value);
    if (source !== file) { try { fs.writeFileSync(source, '', { mode: 0o600 }); } catch { inputLeft = true; } }
  } else if (fs.existsSync(file) && fs.statSync(file).size) {
    value = project(parse(file), now);
    write(file, value);
  } else if (cohort === 'aw2') {
    value = project({ schema_version: SCHEMA, program: 'agent-workforce', cohort: { id: COHORT }, week_dates: WEEKS,
      student: { learn_user_id: null }, learn_progress: null, generated_at: new Date(now).toISOString(), expires_at: EXPIRES }, now);
    write(file, value);
  } else return { status: 'not_connected' };
  return { status: 'refreshed', current_week: value.current_week, source: value.current_week_source, ...(inputLeft ? { input_left: true } : {}) };
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    const option = flag => args.includes(flag) ? args[args.indexOf(flag) + 1] : undefined;
    if (args.some((arg, i) => !['--import', '--cohort'].includes(arg) && !['--import', '--cohort'].includes(args[i - 1])) ||
        args.some((arg, i) => ['--import', '--cohort'].includes(arg) && (!args[i + 1] || args[i + 1].startsWith('--'))) ||
        (option('--cohort') && option('--cohort') !== 'aw2')) throw new Error('Use --import FILE, --cohort aw2, or no arguments to refresh.');
    console.log(JSON.stringify(refresh(process.cwd(), { input: option('--import'), cohort: option('--cohort') })));
  } catch { console.error('Course context could not be refreshed. Check the export and account; no credentials are needed.'); process.exitCode = 1; }
}
