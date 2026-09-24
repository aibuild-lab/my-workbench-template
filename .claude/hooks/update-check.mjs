#!/usr/bin/env node
// The AIBL workbench update check. One implementation, two doors:
//
//   SessionStart hook (Claude Code reads .claude/settings.json in this workbench):
//     at the start of a NEW conversation, fetch what each connected program and the
//     template have published, and say in one sentence whether anything is waiting.
//   node .claude/hooks/update-check.mjs --json
//     the same check as a report; this is what aibl-update reads before it acts.
//   node .claude/hooks/update-check.mjs --agent-menu [--agent-menu-apply]
//     whether Claude Code's @ agent menu lists this workbench's aibl- agents (see "The
//     Claude Code agent menu" below); the hook adds one line when it does not.
//
// Rules, borrowed from the Camp update check that ran for months:
//   1. It never changes the workbench. Fetch only. Merging is aibl-update's job, after a yes.
//      Its one write is --agent-menu-apply, outside the workbench, which aibl-update and
//      aibl-enroll run only after the student's yes. The hook itself never writes.
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

main();

function main() {
  try {
    if (process.argv.includes("--agent-menu-apply")) {
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
// The Claude Code agent menu
// ---------------------------------------------------------------------------
//
// Claude Code desktop's @ menu lists agents only from the user's own agents folder
// (~/.claude/agents on a Mac, .claude\agents in the user folder on Windows), never from
// the workbench's .claude/agents. With the same name in both, the menu shows the user
// folder's entry but the workbench file is what runs; an entry with no workbench match
// runs its own copy, and so does any entry picked while another folder is open.
// Probe-tested on Mac and Windows, 09-24-2026. So: every aibl- agent here has an
// identical entry there, and no retired aibl- entry is left behind. --agent-menu reports; --agent-menu-apply fixes, and only aibl-update or
// aibl-enroll runs it, after the student's yes. It touches aibl-*.md in that one
// folder and nothing else, never writes through a link, and moves leftovers (only
// names a program's published branch once shipped) to a dated backup folder instead
// of deleting them.

function menuFolder() {
  return path.join(os.homedir(), ".claude", "agents");
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

function agentMenu(root) {
  const source = path.join(root, ".claude", "agents");
  const menu = menuFolder();
  const here = agentFiles(source).filter((name) => {
    try { return fs.lstatSync(path.join(source, name)).isFile(); } catch { return false; }
  });
  if (!here.length) return { status: "no_agents", workbench: root, menu_folder: menu, missing: [], changed: [], leftover: [] };
  const there = agentFiles(menu);
  const missing = here.filter((name) => !there.includes(name));
  // content only changes the description the menu shows; the workbench file runs
  const changed = here.filter((name) => there.includes(name) && !sameBytes(path.join(source, name), path.join(menu, name)));
  // A leftover is an entry the COURSE once shipped and has since retired or renamed.
  // Anything else (the student's own agents, the terminal Chief aibl-bridge-setup renders
  // locally, a second workbench's) is not ours to move: reported as not_ours, never
  // touched (Gigawatt's review and Tyler's ruling 3, 09-24).
  const shipped = shippedByCourse(root);
  const gone = there.filter((name) => !here.includes(name));
  const leftover = gone.filter((name) => shipped.has(name));
  const notOurs = gone.filter((name) => !shipped.has(name));
  // contents count too: outside this workbench (another folder open) the user-folder copy is what runs
  const inStep = !missing.length && !changed.length && !leftover.length;
  return { status: inStep ? "in_step" : "out_of_step", workbench: root, menu_folder: menu, missing, changed, leftover,
    not_ours: notOurs };
}

function shippedByCourse(root) {
  // every aibl- agent file any connected program's published branch has ever held, retired
  // ones included. Read from the already-fetched <remote>/student refs; no ref, no names,
  // so nothing is ever treated as a leftover.
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

function applyAgentMenu(root) {
  const plan = agentMenu(root);
  if (plan.status === "no_agents") return plan;
  const source = path.join(root, ".claude", "agents");
  const menu = plan.menu_folder;
  const done = { copied: [], removed_to: null, removed: [], errors: [] };
  fs.mkdirSync(menu, { recursive: true });
  for (const name of [...plan.missing, ...plan.changed]) {
    const dest = path.join(menu, name);
    try {
      // copyFile onto a link would overwrite whatever the link points at
      if (isLink(dest)) fs.unlinkSync(dest);
      fs.copyFileSync(path.join(source, name), dest);
      done.copied.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    }
  }
  if (plan.leftover.length) {
    // outside the agents folder, so the menu cannot pick the backup up
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const backup = path.join(os.homedir(), ".claude", "aibl-agent-menu-removed", stamp);
    for (const name of plan.leftover) {
      try {
        fs.mkdirSync(backup, { recursive: true });
        fs.renameSync(path.join(menu, name), path.join(backup, name));
        done.removed.push(name);
        done.removed_to = backup;
      } catch (error) {
        done.errors.push(`${name}: ${error.code || "move_failed"}`);
      }
    }
  }
  return { ...agentMenu(root), applied: done, next: "Quit the app fully and open it again: the menu reads this folder only at launch. Then start a new thread before typing @." };
}

function describeAgentMenu(menu) {
  if (!menu || menu.status !== "out_of_step") return null;
  const bits = [];
  if (menu.missing.length) bits.push(`not in the @ agent menu yet: ${menu.missing.join(", ")}`);
  if (menu.changed.length) bits.push(`older copies in the menu than in this workbench: ${menu.changed.join(", ")}`);
  if (menu.leftover.length) bits.push(`left over in the menu from a retired or renamed seat: ${menu.leftover.join(", ")}`);
  return `AIBL agent menu check, nothing was changed: ${bits.join("; ")}. ` +
    "Run `node .claude/hooks/update-check.mjs --agent-menu` yourself and tell the student in plain words what it found " +
    "and that Claude Code's @ menu only lists agents from their user folder; do not hand them the command. " +
    "Only on their yes, run `node .claude/hooks/update-check.mjs --agent-menu-apply` yourself, say what it changed, " +
    "then tell them to quit the app fully and reopen it. If they would rather not, drop it for this conversation.";
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
