#!/usr/bin/env node
// The AIBL workbench update check. One implementation, two doors:
//
//   SessionStart hook (Claude Code reads .claude/settings.json in this workbench):
//     at the start of a NEW conversation, fetch what each connected program and the
//     template have published, and say in one sentence whether anything is waiting.
//   node .claude/hooks/update-check.mjs --json
//     the same check as a report; this is what aibl-update reads before it acts.
//
// Rules, borrowed from the Camp update check that ran for months:
//   1. It never changes the workbench. Fetch only. Merging is aibl-update's job, after a yes.
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

main();

function main() {
  try {
    if (process.argv.includes("--json") || process.argv.includes("--check")) {
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
  const sentence = describe(report);
  if (sentence) emit(sentence);
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
