#!/usr/bin/env node
// The AIBL workbench update check. One implementation, two doors:
//
//   SessionStart hook (Claude Code reads .claude/settings.json in this workbench):
//     at the start of a NEW conversation, fetch what each connected program and the
//     template have published, and say in one sentence whether anything is waiting.
//   node .claude/hooks/update-check.mjs --json
//     the same check as a report; this is what aibl-update reads before it acts.
//   node .claude/hooks/update-check.mjs --agent-menu [--agent-menu-apply]
//     whether Claude Code's @ agent menu lists the course's agents from this workbench, and
//     whether the course's bridge skills are in the user's skills folder (see "The Claude
//     Code agent menu" below); the hook adds one line when they are not.
//   node .claude/hooks/update-check.mjs --home-workbench [--home-workbench-apply]
//     whether ~/.aibl/workbench.json records this workbench as the home workbench.
//
// Rules, borrowed from the Camp update check that ran for months:
//   1. It never changes the workbench. Fetch only. Merging is aibl-update's job, after a yes.
//      Its only writes are --agent-menu-apply and --home-workbench-apply, outside the
//      workbench, which aibl-update and aibl-enroll run only after the student's yes.
//      The hook itself never writes.
//   2. It never blocks a session: every path exits 0, and a broken check stays quiet.
//   3. New conversations only. resume, compact and fork continue one that already heard
//      the answer; a subagent lives inside a conversation that already heard it.
//   4. One conversation hears it once (a claim marker keyed by session and workbench).
//   5. Hook and skill cannot drift, because there is only this file.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import tty from "node:tty";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";

const HOOK_EVENT = "SessionStart";
const NEW_CONVERSATION_SOURCES = new Set(["startup", "clear"]);
const MARKER_DIR = path.join(os.tmpdir(), "aibl-workbench-update-check");
const MARKER_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const GIT_TIMEOUT_MS = Number(process.env.AIBL_UPDATE_CHECK_TIMEOUT_MS || 20000);
const PROGRAM_BRANCH = "student";
const PROGRAMS = new Set(["agent-workforce", "the-lab"]);
const LABELS = { "agent-workforce": "Agent Workforce", "the-lab": "The Lab" };
const SKILL_FOLDERS = ["aibl-personalize", "aibl-checkpoint", "aibl-enroll", "aibl-update"]
  .flatMap((name) => [`.claude/skills/${name}`, `.agents/skills/${name}`]);
// the agent menu's files (see "The Claude Code agent menu"); declared up here because main() runs below
const AGENT_FILE = /^aibl-[a-z0-9-]+\.md$/;
// Tyler's ruling (09-24): the menu sync and its cleanup touch ONLY what the course itself
// shipped. Never the student's own agents (in Claude Code or Codex, whatever their names,
// aibl- included), and never other course components. These are every aibl- agent file the
// Agent Workforce student edition has ever published, derived 09-24 from the history of
// agent-native-workforce-internal and of every branch and pull request of
// aibuild-lab/agent-workforce. The -lead terminal copies and aibl-evy never reached a
// published edition, so they are not here. When the course ships a new agent, add its
// name in the same release; never take a name out (a retired name is how a leftover is
// recognized).
const COURSE_AGENTS = new Set([
  "aibl-charter-steward.md",
  "aibl-chief-of-staff.md",
  "aibl-echo.md",
  "aibl-gigawatt.md",
  "aibl-kansa.md",
  "aibl-librarian.md",
  "aibl-the-professor.md",
  "aibl-ygm.md",
]);
// The course's bridge skills, kept as real copies in the user's skills folder so a thread
// opened outside this workbench still has them (workforce-internal #98).
const COURSE_SKILLS = ["aibl-bridge", "aibl-bridge-setup"];
const HOME_POINTER_SCHEMA = "aibl.home-workbench/v1";
const PLACED_SCHEMA = "aibl.agent-menu-placed/v2";
const WINDOWS = process.platform === "win32";
// Mac and Windows folders ignore letter case, so paths are compared the same way there.
const CASE_BLIND = WINDOWS || process.platform === "darwin";
// Finder and Explorer litter that never makes a skill copy "changed"
const TREE_NOISE = new Set([".DS_Store", "Thumbs.db", "__pycache__"]);

main();

function main() {
  try {
    if (process.argv.includes("--home-workbench-apply")) {
      const root = resolveRoot({});
      const report = root ? applyHomeWorkbench(root) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else if (process.argv.includes("--home-workbench")) {
      const root = resolveRoot({});
      const report = root ? homeWorkbench(root) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else if (process.argv.includes("--agent-menu-apply")) {
      const root = resolveRoot({});
      const report = root ? applyAgentMenu(root, replaceEditedArgs()) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else if (process.argv.includes("--agent-menu")) {
      const root = resolveRoot({});
      const report = root ? agentMenu(root) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else if (process.argv.includes("--json") || process.argv.includes("--check")) {
      const root = resolveRoot({});
      const report = root ? check(root) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else {
      hook();
    }
  } catch {
    // Fail quiet. A broken update check must never cost a student a session.
  }
  process.exit(0);
}

function replaceEditedArgs() {
  // --replace-edited NAME[,NAME]: the student said yes to replacing these edited copies
  const names = [];
  process.argv.forEach((arg, i) => {
    if (arg === "--replace-edited" && process.argv[i + 1]) names.push(...process.argv[i + 1].split(","));
    else if (arg.startsWith("--replace-edited=")) names.push(...arg.slice("--replace-edited=".length).split(","));
  });
  return names.map((n) => n.trim()).filter(Boolean);
}

function hook() {
  if (isTruthy(process.env.AIBL_SKIP_UPDATE_CHECK)) return;
  const payload = readPayload();
  const source = typeof payload.source === "string" ? payload.source : "startup";
  if (!NEW_CONVERSATION_SOURCES.has(source)) return;
  if (payload.agent_type) return;
  const root = resolveRoot(payload);
  if (!root) return;
  if (!claimThisConversation(payload.session_id, root)) return;
  const report = check(root);
  const sentences = [describe(report), describeAgentMenu(agentMenu(root))].filter(Boolean);
  if (sentences.length) emit(sentences.join(" "));
}

// ---------------------------------------------------------------------------
// The one check
// ---------------------------------------------------------------------------

function check(root) {
  const remotes = git(root, ["remote"]).split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const programs = [];
  for (const remote of remotes) {
    if (!PROGRAMS.has(remote)) continue;
    const row = { remote, label: LABELS[remote] || remote, behind: null, latest: null, joined: null, error: null };
    const url = git(root, ["remote", "get-url", remote]);
    if (!isOfficialRemote(url, remote)) {
      row.error = "remote_mismatch";
      programs.push(row);
      continue;
    }
    const fetched = spawnSync("git", ["fetch", "-q", remote, PROGRAM_BRANCH], gitOptions(root));
    if (fetched.status !== 0) {
      row.error = "fetch_failed";
    } else {
      const common = spawnSync("git", ["merge-base", "HEAD", `${remote}/${PROGRAM_BRANCH}`], gitOptions(root));
      row.joined = common.status === 0;
      if (!row.joined) {
        row.error = common.status === 1 ? "enrollment_required" : "history_check_failed";
        programs.push(row);
        continue;
      }
      const count = git(root, ["rev-list", "--count", `HEAD..${remote}/${PROGRAM_BRANCH}`]);
      row.behind = Number.parseInt(count, 10);
      if (!Number.isFinite(row.behind)) row.behind = null;
      if (row.behind > 0) {
        // Tyler's #7: read what is actually waiting, not only the newest
        // subject. A student three editions behind should see all three.
        // Capped at three so one line stays one line.
        const notes = git(root, ["log", "--format=%s", `HEAD..${remote}/${PROGRAM_BRANCH}`]);
        row.notes = String(notes).trim().split("\n").map(sanitize).filter(Boolean).slice(0, 3);
        row.latest = row.notes[0] || null;
      }
    }
    programs.push(row);
  }
  let skills = { present: remotes.includes("template"), changed: null, error: null };
  if (skills.present && !isOfficialRemote(git(root, ["remote", "get-url", "template"]), "my-workbench-template")) {
    skills.error = "remote_mismatch";
  } else if (skills.present) {
    const fetched = spawnSync("git", ["fetch", "-q", "template", "main"], gitOptions(root));
    if (fetched.status !== 0) {
      skills.error = "fetch_failed";
    } else {
      const present = SKILL_FOLDERS.filter((f) => git(root, ["ls-tree", "-d", "--name-only", "template/main", "--", f]).trim() !== "");
      const diff = spawnSync("git", ["diff", "--quiet", "HEAD", "template/main", "--", ...present], gitOptions(root));
      skills.changed = diff.status !== 0;
    }
  }
  return { status: "checked", workbench: root, checked_at: new Date().toISOString(), programs, skills };
}

function isOfficialRemote(url, repository) {
  return [`https://github.com/aibuild-lab/${repository}`, `https://github.com/aibuild-lab/${repository}.git`,
    `git@github.com:aibuild-lab/${repository}.git`, `git@github.com:aibuild-lab/${repository}`,
    `ssh://git@github.com/aibuild-lab/${repository}.git`, `ssh://git@github.com/aibuild-lab/${repository}`].includes(url.trim());
}

function describe(report) {
  if (!report || report.status !== "checked") return null;
  const parts = [];
  for (const p of report.programs) {
    if (p.behind > 0) {
      const editions = p.behind === 1 ? "1 new edition" : `${p.behind} new editions`;
      const notes = (p.notes && p.notes.length) ? p.notes : (p.latest ? [p.latest] : []);
      const published = notes.length ? ` (what the team published: ${notes.map((n) => `"${n}"`).join("; ")})` : "";
      parts.push(`${p.label} has ${editions}${published}`);
    }
  }
  if (report.skills.changed) parts.push("the workbench skills have an update from the template");
  if (!parts.length) return null;
  return `AIBL workbench update check, nothing was changed: ${parts.join("; ")}. ` +
    "Tell the student in one line and offer aibl-update, which shows what changes before merging. Do not run it unasked.";
}

// ---------------------------------------------------------------------------
// The Claude Code agent menu, and the bridge skills
// ---------------------------------------------------------------------------
//
// Claude Code desktop's @ menu lists agents only from the user's own agents folder
// (~/.claude/agents on a Mac, .claude\agents in the user folder on Windows), never from
// the workbench's .claude/agents. With the same name in both, the menu shows the user
// folder's entry but the workbench file is what runs; an entry with no workbench match
// runs its own copy, and so does any entry picked while another folder is open.
// Probe-tested on Mac and Windows, 09-24-2026. So: every course agent here has an
// identical real copy there, and no retired course entry is left behind. The same goes
// for the course's bridge skills in ~/.claude/skills: a thread opened outside this
// workbench has no bridge skill unless a real copy sits there.
//
// --agent-menu reports; --agent-menu-apply fixes, and only aibl-update or aibl-enroll runs
// it, after the student's yes. The rules it keeps (Tyler, 09-24: never a student's own
// agents, never other course components):
//   - It touches only the exact names in COURSE_AGENTS and COURSE_SKILLS. Anything else in
//     those folders (the student's own agents and skills, aibl- named or not, in any letter
//     case) is not_ours and never touched. Codex's folders are never touched.
//   - A missing name is copied only when nothing sits at that name in any letter case (Mac
//     and Windows folders ignore case): a clash is reported as case_conflict and skipped.
//   - An existing copy that differs from this workbench's is replaced only when its bytes
//     are provably course-made: a version the verified course branch has published, or
//     bytes some workbench is recorded as having placed. A copy that matches another
//     known workbench's current file is that workbench's (other_workbench, kept). Anything
//     else has the student's own edits (edited, kept); the agent asks the student, and
//     only --replace-edited NAME replaces it.
//   - A leftover (a retired course agent) is moved only when the course's verified branch
//     once shipped it and its current edition does not, this workbench no longer has it,
//     this workbench is recorded as having placed exactly these bytes, and no other known
//     workbench (recorded holders, the home pointer) still has that name.
//   - It records every copy it places, and every copy it finds already matching ("claim
//     without writing"), in ~/.claude/aibl-agent-menu-placed.json.
//   - It never writes through a link and refuses a linked ~/.claude, agents, skills,
//     backup or staging folder. It holds a lock while it plans and applies, and re-checks
//     each file just before it moves it.
//   - It never deletes: a replaced copy, a link it converts, and a leftover all move to a
//     uniquely named, dated backup folder outside the folders the app reads.

function claudeFolder() {
  return path.join(os.homedir(), ".claude");
}

function menuFolder() {
  return path.join(claudeFolder(), "agents");
}

function skillsFolder() {
  return path.join(claudeFolder(), "skills");
}

function placedFile() {
  return path.join(claudeFolder(), "aibl-agent-menu-placed.json");
}

function lockFile() {
  return path.join(claudeFolder(), "aibl-agent-menu.lock");
}

function backupRoot() {
  // outside the agents and skills folders, so the app cannot pick a backup up
  return path.join(claudeFolder(), "aibl-agent-menu-removed");
}

function stagingRoot() {
  return path.join(claudeFolder(), "aibl-agent-menu-staging");
}

function uniqueStamp() {
  return `${new Date().toISOString().replace(/[:.]/g, "-")}-${randomBytes(4).toString("hex")}`;
}

function agentFiles(folder) {
  try {
    return fs.readdirSync(folder).filter((name) => AGENT_FILE.test(name)).sort();
  } catch {
    return [];
  }
}

function entriesByLowerName(folder) {
  const map = new Map();
  try {
    for (const name of fs.readdirSync(folder)) map.set(name.toLowerCase(), name);
  } catch { /* no folder yet */ }
  return map;
}

function sameBytes(a, b) {
  try {
    return fs.readFileSync(a).equals(fs.readFileSync(b));
  } catch {
    return false;
  }
}

function isLink(file) {
  try { return fs.lstatSync(file).isSymbolicLink(); } catch { return false; }
}

function isRealFile(file) {
  try { return fs.lstatSync(file).isFile(); } catch { return false; }
}

function isRealDir(dir) {
  try { return fs.lstatSync(dir).isDirectory(); } catch { return false; }
}

function exists(file) {
  try { fs.lstatSync(file); return true; } catch { return false; }
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

function fileHash(file) {
  // follows a link: what the app would read
  try { return sha256(fs.readFileSync(file)); } catch { return null; }
}

function gitBlobIds(file) {
  // the id git would give these bytes, in both object formats
  try {
    const bytes = fs.readFileSync(file);
    const header = Buffer.from(`blob ${bytes.length}\0`);
    return [createHash("sha1").update(header).update(bytes).digest("hex"),
      createHash("sha256").update(header).update(bytes).digest("hex")];
  } catch {
    return [];
  }
}

// What an entry is right now, so apply can tell whether it changed after the plan.
function fingerprint(p) {
  try {
    const st = fs.lstatSync(p);
    if (st.isSymbolicLink()) return `link:${fs.readlinkSync(p)}`;
    if (st.isFile()) return `file:${fileHash(p)}`;
    if (st.isDirectory()) return `dir:${treeHash(p)}`;
    return "other";
  } catch {
    return "absent";
  }
}

function workbenchId(root) {
  try { return fs.realpathSync(root); } catch { return path.resolve(root); }
}

function sameWorkbench(a, b) {
  const x = workbenchId(a);
  const y = workbenchId(b);
  return CASE_BLIND ? x.toLowerCase() === y.toLowerCase() : x === y;
}

function linkedFolders(base, rels) {
  // Any of these folders that is (or sits under) a link or a Windows junction. Writing into
  // one would change another folder, perhaps another workbench's own agents.
  let realBase;
  try { realBase = fs.realpathSync(base); } catch { return []; }
  const linked = [];
  for (const rel of rels) {
    const p = path.join(base, rel);
    if (!exists(p)) continue;
    let real;
    try { real = fs.realpathSync(p); } catch { linked.push(p); continue; }
    const expected = path.join(realBase, rel);
    if (CASE_BLIND ? real.toLowerCase() !== expected.toLowerCase() : real !== expected) linked.push(p);
  }
  return linked;
}

function linkedClaudeFolders() {
  return linkedFolders(os.homedir(), [".claude", path.join(".claude", "agents"), path.join(".claude", "skills"),
    path.join(".claude", "aibl-agent-menu-removed"), path.join(".claude", "aibl-agent-menu-staging")]);
}

// The record: for each name, every hash any workbench has placed or claimed (proof those
// bytes are course-made copies), and which workbench holds which hash now. An unreadable
// record is treated as empty, which only ever makes the hook keep more.
function readPlaced() {
  const empty = { agents: {}, skills: {} };
  try {
    if (!isRealFile(placedFile())) return empty;
    const parsed = JSON.parse(fs.readFileSync(placedFile(), "utf8"));
    if (!parsed || parsed.schema_version !== PLACED_SCHEMA) return empty;
    return { agents: parsed.agents || {}, skills: parsed.skills || {} };
  } catch {
    return empty;
  }
}

function writePlaced(placed) {
  const file = placedFile();
  const temp = `${file}.${process.pid}.${randomBytes(4).toString("hex")}.tmp`;
  const fd = fs.openSync(temp, "wx"); // never an existing file, never a link
  try {
    fs.writeSync(fd, JSON.stringify({ schema_version: PLACED_SCHEMA, agents: placed.agents, skills: placed.skills }, null, 2) + "\n");
  } finally {
    fs.closeSync(fd);
  }
  if (isLink(file)) fs.unlinkSync(file);
  fs.renameSync(temp, file);
}

function hold(placed, group, name, root, hash) {
  if (!hash) return;
  const entry = placed[group][name] || (placed[group][name] = { hashes: [], holders: {} });
  if (!entry.hashes.includes(hash)) entry.hashes.push(hash);
  for (const wb of Object.keys(entry.holders)) if (sameWorkbench(wb, root)) delete entry.holders[wb];
  entry.holders[workbenchId(root)] = hash;
}

function release(placed, group, name, root) {
  const entry = placed[group][name];
  if (!entry) return;
  for (const wb of Object.keys(entry.holders)) if (sameWorkbench(wb, root)) delete entry.holders[wb];
}

function heldHere(placed, group, name, root, hash) {
  const entry = placed[group][name];
  if (!entry || !hash) return false;
  return Object.entries(entry.holders).some(([wb, h]) => sameWorkbench(wb, root) && h === hash);
}

function knownOtherWorkbenches(root, placed) {
  // every other workbench this computer has a record of: the holders in the record, and
  // the recorded home workbench
  const found = [];
  const add = (wb) => {
    if (typeof wb !== "string" || sameWorkbench(wb, root)) return;
    if (!isRealDir(wb) || found.some((f) => sameWorkbench(f, wb))) return;
    found.push(wb);
  };
  for (const group of [placed.agents, placed.skills]) {
    for (const entry of Object.values(group)) for (const wb of Object.keys((entry && entry.holders) || {})) add(wb);
  }
  try { add(JSON.parse(fs.readFileSync(pointerFile(), "utf8")).path); } catch { /* no pointer */ }
  return found;
}

function verifiedProgramRefs(root) {
  // <remote>/student refs whose remote's EFFECTIVE fetch URL (`git remote get-url`, which
  // applies any insteadOf rewrite) is the official repository. A remote merely named
  // agent-workforce, or one rewritten to point somewhere else, proves nothing.
  const refs = [];
  for (const remote of PROGRAMS) {
    const url = git(root, ["remote", "get-url", remote]);
    if (!url || !isOfficialRemote(url, remote)) continue;
    const ref = `refs/remotes/${remote}/${PROGRAM_BRANCH}`;
    if (git(root, ["rev-parse", "--verify", "--quiet", ref])) refs.push(ref);
  }
  return refs;
}

function courseHistory(root) {
  // shipped: every aibl- agent a verified program branch has ever held. current: the ones
  // its current edition holds. blobs: every version of each it ever published. No verified
  // ref, no names: nothing is a leftover and nothing is proven course-made by the course.
  const shipped = new Set();
  const current = new Set();
  const blobs = new Map();
  for (const ref of verifiedProgramRefs(root)) {
    const raw = git(root, ["log", "--raw", "--no-abbrev", "--no-renames", "--format=", ref, "--", ".claude/agents"]);
    for (const line of raw.split(/\r?\n/)) {
      const m = line.match(/^:\d+ \d+ ([0-9a-f]+) ([0-9a-f]+) \w+\t(.+)$/);
      if (!m) continue;
      const name = path.posix.basename(m[3].trim());
      if (!AGENT_FILE.test(name)) continue;
      shipped.add(name);
      const set = blobs.get(name) || new Set();
      for (const id of [m[1], m[2]]) if (!/^0+$/.test(id)) set.add(id);
      blobs.set(name, set);
    }
    const tip = git(root, ["ls-tree", "--name-only", `${ref}:.claude/agents`]);
    for (const p of tip.split(/\r?\n/)) {
      const name = p.trim();
      if (AGENT_FILE.test(name)) current.add(name);
    }
  }
  return { shipped, current, blobs };
}

function agentMenu(root) {
  const source = path.join(root, ".claude", "agents");
  const menu = menuFolder();
  const all = agentFiles(source).filter((name) => isRealFile(path.join(source, name)));
  // Only the course's own agents are synced. An aibl- file the student made is theirs.
  const here = all.filter((name) => COURSE_AGENTS.has(name));
  const skipped = all.filter((name) => !COURSE_AGENTS.has(name));
  const placed = readPlaced();
  const others = knownOtherWorkbenches(root, placed);
  const history = courseHistory(root);
  const byLower = entriesByLowerName(menu);
  const there = agentFiles(menu);
  const missing = [];
  const caseConflict = [];
  const changed = [];
  const edited = [];
  const otherWorkbench = [];
  const inStepNames = [];
  const seen = {};
  for (const name of here) {
    const actual = byLower.get(name.toLowerCase());
    const dest = path.join(menu, name);
    if (actual === undefined) { missing.push(name); continue; }
    if (actual !== name) { caseConflict.push(`${actual} (in the way of ${name})`); continue; }
    seen[name] = fingerprint(dest);
    const ours = path.join(source, name);
    if (!isLink(dest) && sameBytes(ours, dest)) { inStepNames.push(name); continue; }
    const hash = fileHash(dest);
    // another known workbench's current copy: theirs
    if (hash && others.some((wb) => sameBytes(path.join(wb, ".claude", "agents", name), dest))) {
      otherWorkbench.push(name);
      continue;
    }
    const recorded = Boolean(hash && placed.agents[name] && placed.agents[name].hashes.includes(hash));
    const published = gitBlobIds(dest).some((id) => (history.blobs.get(name) || new Set()).has(id));
    const linkToOurs = isLink(dest) && sameBytes(ours, dest);
    if (recorded || published || linkToOurs) changed.push(name);
    else edited.push(name);
  }
  const gone = there.filter((name) => !here.includes(name));
  const leftover = gone.filter((name) => {
    const dest = path.join(menu, name);
    if (!COURSE_AGENTS.has(name) || !history.shipped.has(name) || history.current.has(name)) return false;
    if (!isRealFile(dest)) return false;
    if (!heldHere(placed, "agents", name, root, fileHash(dest))) return false;
    // no other workbench this computer knows of still has it, in any form
    return !others.some((wb) => exists(path.join(wb, ".claude", "agents", name)));
  });
  for (const name of leftover) seen[name] = fingerprint(path.join(menu, name));
  const notOurs = gone.filter((name) => !leftover.includes(name));
  // the bridge skills only come with the course's agents; a workbench with none gets none
  const skills = here.length ? bridgeSkills(root, placed, others)
    : { skills_folder: skillsFolder(), missing: [], changed: [], edited: [], other_workbench: [], case_conflict: [], in_step: [], seen: {}, errors: [] };
  const linked = linkedClaudeFolders();
  const empty = !here.length && !leftover.length;
  const pending = missing.length + changed.length + leftover.length + skills.missing.length + skills.changed.length;
  const toAsk = edited.length + skills.edited.length + caseConflict.length + skills.case_conflict.length;
  let status = empty ? "no_agents" : pending ? "out_of_step" : toAsk ? "needs_a_decision" : "in_step";
  if (linked.length && (pending || toAsk)) status = "linked_folder";
  return { status, workbench: root, menu_folder: menu, missing, changed, edited, leftover, not_ours: notOurs, skipped,
    other_workbench: otherWorkbench, case_conflict: caseConflict, linked_folders: linked, skills,
    in_step: inStepNames, seen };
}

function realTree(dir) {
  // the relative paths of every file under dir, or null when anything in it is a link or
  // not a plain file (such a skill is refused, never copied)
  const files = [];
  const walk = (rel) => {
    for (const entry of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
      if (TREE_NOISE.has(entry.name)) continue;
      const r = rel ? path.join(rel, entry.name) : entry.name;
      if (entry.isSymbolicLink()) throw new Error("link");
      if (entry.isDirectory()) walk(r);
      else if (entry.isFile()) files.push(r);
      else throw new Error("special");
    }
  };
  try { walk(""); } catch { return null; }
  return files.sort();
}

function executable(file) {
  try { return (fs.statSync(file).mode & 0o111) !== 0; } catch { return false; }
}

function treeHash(dir, withModes = true) {
  const files = isRealDir(dir) ? realTree(dir) : null;
  if (!files) return null;
  const h = createHash("sha256");
  for (const rel of files) {
    h.update(rel.split(path.sep).join("/")).update("\0");
    h.update(WINDOWS || !withModes ? "" : (executable(path.join(dir, rel)) ? "x" : "-")).update("\0");
    h.update(fs.readFileSync(path.join(dir, rel))).update("\0");
  }
  return h.digest("hex");
}

function bridgeSkills(root, placed, others) {
  const folder = skillsFolder();
  const byLower = entriesByLowerName(folder);
  const out = { skills_folder: folder, missing: [], changed: [], edited: [], other_workbench: [], case_conflict: [],
    in_step: [], seen: {}, errors: [] };
  for (const name of COURSE_SKILLS) {
    const src = path.join(root, ".claude", "skills", name);
    if (!isRealDir(src)) continue; // this workbench's edition does not have it
    const ours = treeHash(src);
    if (!ours) { out.errors.push(`${name}: the workbench copy holds a link, so it is not copied`); continue; }
    const actual = byLower.get(name.toLowerCase());
    const dest = path.join(folder, name);
    if (actual === undefined) { out.missing.push(name); continue; }
    if (actual !== name) { out.case_conflict.push(`${actual} (in the way of ${name})`); continue; }
    out.seen[name] = fingerprint(dest);
    const theirs = isLink(dest) ? null : treeHash(dest);
    if (theirs === ours) { out.in_step.push(name); continue; }
    if (theirs && others.some((wb) => treeHash(path.join(wb, ".claude", "skills", name)) === theirs)) {
      out.other_workbench.push(name);
      continue;
    }
    const linkToOurs = isLink(dest);
    const recorded = Boolean(theirs && placed.skills[name] && placed.skills[name].hashes.includes(theirs));
    // the same files, only a lost exec bit (the 09-23 failure): still the course's copy
    const modesOnly = Boolean(theirs && treeHash(dest, false) === treeHash(src, false));
    if (recorded || linkToOurs || modesOnly) out.changed.push(name);
    else out.edited.push(name);
  }
  return out;
}

function copySkill(root, name, dest, keep) {
  const src = path.join(root, ".claude", "skills", name);
  const files = realTree(src);
  if (!files) throw Object.assign(new Error("link in source"), { code: "source_has_link" });
  fs.mkdirSync(stagingRoot(), { recursive: true });
  const staging = path.join(stagingRoot(), `${name}-${uniqueStamp()}`);
  fs.mkdirSync(staging); // a new folder, never an existing one or a link
  try {
    for (const rel of files) {
      const to = path.join(staging, rel);
      fs.mkdirSync(path.dirname(to), { recursive: true });
      fs.copyFileSync(path.join(src, rel), to, fs.constants.COPYFILE_EXCL);
      // keep the scripts runnable: the bridge runs them by path, not through bash
      if (!WINDOWS) fs.chmodSync(to, fs.statSync(path.join(src, rel)).mode & 0o777);
    }
    if (exists(dest)) keep(dest, path.join("skills", name)); // a link moves as a link
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.renameSync(staging, dest);
  } catch (error) {
    try { fs.rmSync(staging, { recursive: true, force: true }); } catch { /* our own temp copy */ }
    throw error;
  }
}

function takeLock() {
  const file = lockFile();
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      fs.mkdirSync(claudeFolder(), { recursive: true });
      const fd = fs.openSync(file, "wx");
      fs.writeSync(fd, `${process.pid} ${new Date().toISOString()}\n`);
      fs.closeSync(fd);
      return () => { try { fs.unlinkSync(file); } catch { /* already gone */ } };
    } catch (error) {
      if (error.code !== "EEXIST") return null;
      // a lock older than ten minutes was left by a run that died
      try {
        if (isRealFile(file) && Date.now() - fs.statSync(file).mtimeMs > 10 * 60 * 1000) { fs.unlinkSync(file); continue; }
      } catch { /* keep it */ }
      return null;
    }
  }
  return null;
}

function applyAgentMenu(root, replaceEdited) {
  const unlock = takeLock();
  if (!unlock) {
    return { status: "busy", explain: "Another agent-menu update is running right now. Nothing was changed; try again in a minute." };
  }
  try {
    return applyLocked(root, replaceEdited);
  } finally {
    unlock();
  }
}

function applyLocked(root, replaceEdited) {
  const plan = agentMenu(root);
  if (plan.status === "no_agents") return plan;
  if (plan.linked_folders.length) {
    return { ...plan, applied: null, refused: "linked_folder",
      explain: "Your Claude agents or skills folder is a shortcut (a link) to another folder, perhaps another " +
        "workbench's. Nothing was written, so that folder stays exactly as it is. The course team can help make " +
        "it a real folder." };
  }
  const source = path.join(root, ".claude", "agents");
  const menu = plan.menu_folder;
  const placed = readPlaced();
  const backup = path.join(backupRoot(), uniqueStamp());
  const done = { copied: [], replaced: [], removed: [], claimed: [], skills_copied: [], skipped_changed_since_check: [],
    removed_to: null, errors: [] };
  const keep = (from, rel) => {
    const to = path.join(backup, rel);
    if (!exists(backup)) { fs.mkdirSync(backupRoot(), { recursive: true }); fs.mkdirSync(backup); }
    fs.mkdirSync(path.dirname(to), { recursive: true });
    if (exists(to)) throw Object.assign(new Error("backup exists"), { code: "EEXIST" });
    fs.renameSync(from, to);
    done.removed_to = backup;
  };
  const unchanged = (p, seen) => fingerprint(p) === seen;
  const approved = (name, list) => replaceEdited.includes(name) && list.includes(name);
  fs.mkdirSync(menu, { recursive: true });

  // claim without writing: copies that already match this workbench's are recorded as held here
  for (const name of plan.in_step) {
    hold(placed, "agents", name, root, fileHash(path.join(menu, name)));
    done.claimed.push(name);
  }
  for (const name of plan.missing) {
    if (!COURSE_AGENTS.has(name)) continue; // the allowlist again, in case plan and list ever drift
    const dest = path.join(menu, name);
    try {
      // on a folder that ignores case, a different-case file answers to this name: never touch it
      if (exists(dest)) { done.skipped_changed_since_check.push(name); continue; }
      fs.copyFileSync(path.join(source, name), dest, fs.constants.COPYFILE_EXCL);
      hold(placed, "agents", name, root, fileHash(dest));
      done.copied.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    }
  }
  for (const name of [...plan.changed, ...plan.edited.filter((n) => approved(n, plan.edited))]) {
    if (!COURSE_AGENTS.has(name)) continue;
    const dest = path.join(menu, name);
    try {
      if (!unchanged(dest, plan.seen[name])) { done.skipped_changed_since_check.push(name); continue; }
      keep(dest, path.join("replaced", name)); // a link moves as a link; what it points at is untouched
      fs.copyFileSync(path.join(source, name), dest, fs.constants.COPYFILE_EXCL);
      hold(placed, "agents", name, root, fileHash(dest));
      done.replaced.push(name);
      done.copied.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    }
  }
  for (const name of plan.leftover) {
    if (!COURSE_AGENTS.has(name)) continue;
    const dest = path.join(menu, name);
    try {
      if (!unchanged(dest, plan.seen[name])) { done.skipped_changed_since_check.push(name); continue; }
      keep(dest, name);
      release(placed, "agents", name, root);
      done.removed.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "move_failed"}`);
    }
  }
  const sk = plan.skills;
  for (const name of sk.in_step) {
    hold(placed, "skills", name, root, treeHash(path.join(skillsFolder(), name)));
    done.claimed.push(`skill ${name}`);
  }
  for (const name of [...sk.missing, ...sk.changed, ...sk.edited.filter((n) => approved(n, sk.edited))]) {
    if (!COURSE_SKILLS.includes(name)) continue;
    const dest = path.join(skillsFolder(), name);
    try {
      const expected = sk.missing.includes(name) ? "absent" : sk.seen[name];
      if (fingerprint(dest) !== expected) { done.skipped_changed_since_check.push(`skill ${name}`); continue; }
      copySkill(root, name, dest, keep);
      hold(placed, "skills", name, root, treeHash(dest));
      done.skills_copied.push(name);
    } catch (error) {
      done.errors.push(`skill ${name}: ${error.code || "copy_failed"}`);
    }
  }
  try { fs.rmdirSync(stagingRoot()); } catch { /* not empty or never made */ }
  try { writePlaced(placed); } catch (error) { done.errors.push(`record: ${error.code || "write_failed"}`); }
  return { ...agentMenu(root), applied: done, next: "Quit the app fully and open it again: the menu reads this folder only at launch. Then start a new thread before typing @." };
}

function describeAgentMenu(menu) {
  if (!menu || !["out_of_step", "needs_a_decision", "linked_folder"].includes(menu.status)) return null;
  const bits = [];
  if (menu.missing.length) bits.push(`not in the @ agent menu yet: ${menu.missing.join(", ")}`);
  if (menu.changed.length) bits.push(`course copies in the menu that differ from this workbench's: ${menu.changed.join(", ")}`);
  if (menu.leftover.length) bits.push(`left over in the menu from a retired seat: ${menu.leftover.join(", ")}`);
  if (menu.skills.missing.length) bits.push(`bridge skills not yet available outside this workbench: ${menu.skills.missing.join(", ")}`);
  if (menu.skills.changed.length) bits.push(`bridge skill copies that differ from this workbench's: ${menu.skills.changed.join(", ")}`);
  const edited = [...menu.edited, ...menu.skills.edited];
  if (edited.length) bits.push(`copies in the user folder that carry the student's own edits (never replaced unasked): ${edited.join(", ")}`);
  const clashes = [...menu.case_conflict, ...menu.skills.case_conflict];
  if (clashes.length) bits.push(`files whose names differ only in capital letters are in the way (never touched): ${clashes.join(", ")}`);
  if (menu.status === "linked_folder") {
    return `AIBL agent menu check, nothing was changed: ${bits.join("; ")}. ` +
      `But ${menu.linked_folders.join(" and ")} is a link to another folder, so the fix would write into that folder. ` +
      "Do not offer the fix. Tell the student in plain words that their Claude agents folder is a shortcut to another " +
      "folder, that nothing was changed, and that the course team can help make it a real folder.";
  }
  return `AIBL agent menu check, nothing was changed: ${bits.join("; ")}. ` +
    "Run `node .claude/hooks/update-check.mjs --agent-menu` yourself and tell the student in plain words what it found, " +
    "that Claude Code's @ menu only lists agents from their user folder, and that the bridge needs its skills there to work " +
    "outside this workbench; do not hand them the command. " +
    "Only on their yes, run `node .claude/hooks/update-check.mjs --agent-menu-apply` yourself, say what it changed, " +
    "then tell them to quit the app fully and reopen it. For a copy with their own edits, ask separately (\"Your copy of " +
    "NAME has your own edits; replace it with the course version? The old one goes to a backup.\") and only on that yes " +
    "add `--replace-edited NAME`. If they would rather not, drop it for this conversation.";
}

// ---------------------------------------------------------------------------
// The home workbench pointer
// ---------------------------------------------------------------------------
//
// The course's agents and bridge work from any folder, but keep their registry, charter and
// receipts in one home workbench. ~/.aibl/workbench.json (the same file in the user folder
// on Windows) records which one; workforce/shed/shed.py home and the bridge preflight read
// it. --home-workbench reports; --home-workbench-apply writes this workbench's absolute path,
// and aibl-enroll or aibl-update run it only after the student's yes. It touches that one
// file and nothing else under ~/.aibl/.

function pointerFile() {
  return path.join(os.homedir(), ".aibl", "workbench.json");
}

function samePath(a, b) {
  const real = (p) => { try { return fs.realpathSync(p); } catch { return path.resolve(p); } };
  const x = real(a);
  const y = real(b);
  return CASE_BLIND ? x.toLowerCase() === y.toLowerCase() : x === y;
}

function homeWorkbench(root) {
  const pointer = pointerFile();
  const workbench = path.resolve(root);
  const wanted = { schema_version: HOME_POINTER_SCHEMA, path: workbench };
  const hasRegistry = fs.existsSync(path.join(workbench, "workforce", "shed", "registry.yaml"));
  let recorded = null;
  let status;
  if (isLink(pointer)) {
    status = "pointer_is_a_link";
  } else if (!exists(pointer)) {
    status = "not_recorded";
  } else {
    try {
      const parsed = JSON.parse(fs.readFileSync(pointer, "utf8"));
      recorded = parsed && typeof parsed.path === "string" ? parsed.path : null;
    } catch {
      recorded = null;
    }
    if (recorded === null) status = "unreadable";
    else status = samePath(recorded, workbench) ? "this_workbench" : "another_folder";
  }
  return { status, pointer, recorded, workbench, has_registry: hasRegistry, would_write: wanted };
}

function applyHomeWorkbench(root) {
  const before = homeWorkbench(root);
  const pointer = before.pointer;
  const temp = `${pointer}.${process.pid}.tmp`;
  const linked = linkedFolders(os.homedir(), [".aibl"]);
  if (linked.length) return { ...before, applied: false, error: "linked_folder", linked_folders: linked };
  try {
    if (isLink(pointer)) fs.unlinkSync(pointer); // never write through a link
    fs.mkdirSync(path.dirname(pointer), { recursive: true });
    fs.writeFileSync(temp, JSON.stringify(before.would_write, null, 2) + "\n");
    fs.renameSync(temp, pointer);
  } catch (error) {
    try { fs.rmSync(temp, { force: true }); } catch { /* our own temp file */ }
    return { ...homeWorkbench(root), applied: false, error: error.code || "write_failed", previous: before.recorded };
  }
  return { ...homeWorkbench(root), applied: true, previous: before.recorded };
}

// ---------------------------------------------------------------------------
// Plumbing
// ---------------------------------------------------------------------------

function readPayload() {
  try {
    if (tty.isatty(0)) return {};
    const raw = fs.readFileSync(0, "utf8");
    if (!raw.trim()) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function resolveRoot(payload) {
  const candidates = [process.env.CLAUDE_PROJECT_DIR, typeof payload.cwd === "string" ? payload.cwd : null, process.cwd()];
  for (const candidate of candidates) {
    if (!candidate) continue;
    const top = spawnSync("git", ["rev-parse", "--show-toplevel"], gitOptions(candidate));
    if (top.status !== 0) continue;
    const root = String(top.stdout).trim();
    if (isWorkbench(root)) return root;
  }
  return null;
}

function isWorkbench(root) {
  return fs.existsSync(path.join(root, ".aibl", "template.json")) ||
    fs.existsSync(path.join(root, ".claude", "skills", "aibl-update", "SKILL.md"));
}

function claimThisConversation(sessionId, root) {
  if (typeof sessionId !== "string" || !sessionId.trim()) return true;
  const key = createHash("sha256").update(`${sessionId}\0${root}`).digest("hex");
  const marker = path.join(MARKER_DIR, `${key}.claimed`);
  try {
    fs.mkdirSync(MARKER_DIR, { recursive: true, mode: 0o700 });
    prune(MARKER_DIR);
    fs.closeSync(fs.openSync(marker, "wx", 0o600)); // exclusive create; a second call throws
    return true;
  } catch {
    return false;
  }
}

function prune(directory) {
  try {
    const cutoff = Date.now() - MARKER_TTL_MS;
    for (const entry of fs.readdirSync(directory)) {
      const target = path.join(directory, entry);
      try { if (fs.statSync(target).mtimeMs < cutoff) fs.rmSync(target, { force: true }); } catch { /* leave it */ }
    }
  } catch { /* housekeeping only */ }
}

function gitOptions(cwd) {
  return { cwd, encoding: "utf8", timeout: GIT_TIMEOUT_MS, stdio: ["ignore", "pipe", "pipe"], windowsHide: true };
}

function git(root, args) {
  const result = spawnSync("git", args, gitOptions(root));
  return result.status === 0 ? String(result.stdout).trim() : "";
}

function sanitize(text) {
  return String(text).replace(/\b(?:https?|ssh|git|file):\/\/\S+/gi, "[address withheld]").slice(0, 160);
}

function emit(additionalContext) {
  process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: HOOK_EVENT, additionalContext } })}\n`);
}

function isTruthy(value) {
  return typeof value === "string" && /^(1|true|yes|on)$/i.test(value.trim());
}
