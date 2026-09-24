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
import { createHash } from "node:crypto";
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
const WINDOWS = process.platform === "win32";
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
      const report = root ? applyAgentMenu(root) : { status: "not_a_workbench" };
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
// it, after the student's yes. It touches only the names in COURSE_AGENTS and COURSE_SKILLS,
// never writes through a link, and never deletes: a leftover or a replaced copy is moved to
// a dated backup folder outside the folders the app reads. A leftover is a course agent
// that this workbench no longer has AND that a connected program's published branch once
// shipped. Everything else in those folders (the student's own agents and skills, aibl-
// named or not, anything a second workbench or another course component put there) is
// reported as not_ours and never touched. Codex's folders are never touched.

function menuFolder() {
  return path.join(os.homedir(), ".claude", "agents");
}

function skillsFolder() {
  return path.join(os.homedir(), ".claude", "skills");
}

function backupFolder(stamp) {
  // outside the agents and skills folders, so the app cannot pick a backup up
  return path.join(os.homedir(), ".claude", "aibl-agent-menu-removed", stamp);
}

function agentFiles(folder) {
  try {
    return fs.readdirSync(folder).filter((name) => AGENT_FILE.test(name)).sort();
  } catch {
    return [];
  }
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

function agentMenu(root) {
  const source = path.join(root, ".claude", "agents");
  const menu = menuFolder();
  const all = agentFiles(source).filter((name) => isRealFile(path.join(source, name)));
  // Only the course's own agents are synced. An aibl- file the student made is theirs.
  const here = all.filter((name) => COURSE_AGENTS.has(name));
  const skipped = all.filter((name) => !COURSE_AGENTS.has(name));
  if (!here.length) {
    return { status: "no_agents", workbench: root, menu_folder: menu, missing: [], changed: [], leftover: [],
      not_ours: [], skipped, skills: { skills_folder: skillsFolder(), missing: [], changed: [], errors: [] } };
  }
  const there = agentFiles(menu);
  const missing = here.filter((name) => !there.includes(name));
  // Contents count too: with another folder open, the user-folder copy is what runs. A link is
  // not a real copy (it breaks when the workbench moves, and Windows does not follow it).
  const changed = here.filter((name) => there.includes(name) &&
    (isLink(path.join(menu, name)) || !sameBytes(path.join(source, name), path.join(menu, name))));
  const shipped = shippedByCourse(root);
  const gone = there.filter((name) => !here.includes(name));
  const leftover = gone.filter((name) => COURSE_AGENTS.has(name) && shipped.has(name));
  const notOurs = gone.filter((name) => !leftover.includes(name));
  const skills = bridgeSkills(root);
  const inStep = !missing.length && !changed.length && !leftover.length && !skills.missing.length && !skills.changed.length;
  return { status: inStep ? "in_step" : "out_of_step", workbench: root, menu_folder: menu, missing, changed, leftover,
    not_ours: notOurs, skipped, skills };
}

function shippedByCourse(root) {
  // every aibl- agent file any connected program's published branch has ever held, retired
  // ones included. Read from the already-fetched <remote>/student refs; no ref, no names,
  // so nothing is ever treated as a leftover. A second condition on top of COURSE_AGENTS,
  // never a way around it.
  const names = new Set();
  for (const remote of PROGRAMS) {
    const ref = `refs/remotes/${remote}/${PROGRAM_BRANCH}`;
    if (!git(root, ["rev-parse", "--verify", "--quiet", ref])) continue;
    const log = git(root, ["log", "--format=", "--name-only", "--no-renames", ref, "--", ".claude/agents"]);
    for (const p of log.split(/\r?\n/)) {
      const name = path.posix.basename(p.trim());
      if (AGENT_FILE.test(name)) names.add(name);
    }
  }
  return names;
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

function sameTree(src, files, dest) {
  const other = isRealDir(dest) ? realTree(dest) : null;
  if (!other || other.join("\n") !== files.join("\n")) return false;
  return files.every((rel) => sameBytes(path.join(src, rel), path.join(dest, rel)) &&
    (WINDOWS || executable(path.join(src, rel)) === executable(path.join(dest, rel))));
}

function bridgeSkills(root) {
  const folder = skillsFolder();
  const missing = [];
  const changed = [];
  const errors = [];
  for (const name of COURSE_SKILLS) {
    const src = path.join(root, ".claude", "skills", name);
    if (!isRealDir(src)) continue; // this workbench's edition does not have it
    const files = realTree(src);
    if (!files) { errors.push(`${name}: the workbench copy holds a link, so it is not copied`); continue; }
    const dest = path.join(folder, name);
    if (!exists(dest)) missing.push(name);
    else if (isLink(dest) || !sameTree(src, files, dest)) changed.push(name);
  }
  return { skills_folder: folder, missing, changed, errors };
}

function copySkill(root, name, staging, dest, keep) {
  const src = path.join(root, ".claude", "skills", name);
  const files = realTree(src);
  if (!files) throw Object.assign(new Error("link in source"), { code: "source_has_link" });
  fs.rmSync(staging, { recursive: true, force: true });
  for (const rel of files) {
    const to = path.join(staging, rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(path.join(src, rel), to);
    // keep the scripts runnable: the bridge runs them by path, not through bash
    if (!WINDOWS) fs.chmodSync(to, fs.statSync(path.join(src, rel)).mode & 0o777);
  }
  if (isLink(dest)) fs.unlinkSync(dest); // removes the link only, never what it points at
  else if (exists(dest)) keep(dest, path.join("skills", name));
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.renameSync(staging, dest);
}

function applyAgentMenu(root) {
  const plan = agentMenu(root);
  if (plan.status === "no_agents") return plan;
  const source = path.join(root, ".claude", "agents");
  const menu = plan.menu_folder;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backup = backupFolder(stamp);
  const done = { copied: [], replaced: [], removed: [], skills_copied: [], removed_to: null, errors: [] };
  const keep = (from, rel) => {
    const to = path.join(backup, rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.renameSync(from, to);
    done.removed_to = backup;
  };
  fs.mkdirSync(menu, { recursive: true });
  for (const name of [...plan.missing, ...plan.changed]) {
    if (!COURSE_AGENTS.has(name)) continue; // the allowlist again, in case plan and list ever drift
    const dest = path.join(menu, name);
    try {
      // copyFile onto a link would overwrite whatever the link points at
      if (isLink(dest)) fs.unlinkSync(dest);
      else if (exists(dest)) { keep(dest, path.join("replaced", name)); done.replaced.push(name); }
      fs.copyFileSync(path.join(source, name), dest, fs.constants.COPYFILE_EXCL);
      done.copied.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    }
  }
  for (const name of plan.leftover) {
    if (!COURSE_AGENTS.has(name)) continue;
    try {
      keep(path.join(menu, name), name);
      done.removed.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "move_failed"}`);
    }
  }
  const stagingRoot = path.join(os.homedir(), ".claude", "aibl-agent-menu-staging");
  for (const name of [...plan.skills.missing, ...plan.skills.changed]) {
    if (!COURSE_SKILLS.includes(name)) continue;
    const staging = path.join(stagingRoot, `${stamp}-${name}`);
    try {
      copySkill(root, name, staging, path.join(skillsFolder(), name), keep);
      done.skills_copied.push(name);
    } catch (error) {
      done.errors.push(`skill ${name}: ${error.code || "copy_failed"}`);
      try { fs.rmSync(staging, { recursive: true, force: true }); } catch { /* our own temp copy */ }
    }
  }
  try { fs.rmdirSync(stagingRoot); } catch { /* not empty or never made */ }
  return { ...agentMenu(root), applied: done, next: "Quit the app fully and open it again: the menu reads this folder only at launch. Then start a new thread before typing @." };
}

function describeAgentMenu(menu) {
  if (!menu || menu.status !== "out_of_step") return null;
  const bits = [];
  if (menu.missing.length) bits.push(`not in the @ agent menu yet: ${menu.missing.join(", ")}`);
  if (menu.changed.length) bits.push(`older copies in the menu than in this workbench: ${menu.changed.join(", ")}`);
  if (menu.leftover.length) bits.push(`left over in the menu from a retired or renamed seat: ${menu.leftover.join(", ")}`);
  if (menu.skills.missing.length) bits.push(`bridge skills not yet available outside this workbench: ${menu.skills.missing.join(", ")}`);
  if (menu.skills.changed.length) bits.push(`older bridge skill copies than this workbench's: ${menu.skills.changed.join(", ")}`);
  return `AIBL agent menu check, nothing was changed: ${bits.join("; ")}. ` +
    "Run `node .claude/hooks/update-check.mjs --agent-menu` yourself and tell the student in plain words what it found, " +
    "that Claude Code's @ menu only lists agents from their user folder, and that the bridge needs its skills there to work " +
    "outside this workbench; do not hand them the command. " +
    "Only on their yes, run `node .claude/hooks/update-check.mjs --agent-menu-apply` yourself, say what it changed, " +
    "then tell them to quit the app fully and reopen it. If they would rather not, drop it for this conversation.";
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
  return WINDOWS ? x.toLowerCase() === y.toLowerCase() : x === y;
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
