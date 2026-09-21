#!/usr/bin/env node

// Claude Code SessionStart hook for the workbench: "an update is waiting."
//
// Ported from Agent Native Camp's session-update-check.mjs (Tyler's design, stated
// plainly there): at the beginning of a NEW conversation, check what the course
// team has published against what this workbench has. Never pull. Say what is
// waiting and name the skill that brings it in. Fail quiet: a broken check must
// never cost a student a session.
//
// What this file does, and does not do:
// - Runs only for a new conversation (`startup` or `clear`). `resume`, `compact`
//   and `fork` continue a conversation that already heard the answer.
// - Stays quiet inside a subagent (it is already inside a conversation that knows).
// - Reads the connected programs from `git remote` (anything that is not `origin`
//   or `template`), fetches each program's `student` branch (fetch only; the
//   working tree is never touched), counts how many editions this workbench is
//   behind, and reads the incoming release notes (commit subjects).
// - Prints one short paragraph as additional context. Nothing else. `aibl-update`
//   does the merge, after the student's yes.
// - Every path exits 0.
//
// Codex has no SessionStart hook of this shape; the `aibl-workforce` entry skill
// carries the same check in words for that app.

import fs from "node:fs";
import tty from "node:tty";
import { spawnSync } from "node:child_process";

const NEW_CONVERSATION_SOURCES = new Set(["startup", "clear"]);
const FETCH_TIMEOUT_MS = Number(process.env.AIBL_UPDATE_CHECK_TIMEOUT_MS || 20000);
const SKIP_REMOTES = new Set(["origin", "template"]);

main();

function main() {
  try {
    run();
  } catch {
    // Fail quiet.
  }
  process.exit(0);
}

function run() {
  if (isTruthy(process.env.AIBL_SKIP_UPDATE_CHECK)) return;
  const payload = readPayload();
  const source = typeof payload.source === "string" ? payload.source : "startup";
  if (!NEW_CONVERSATION_SOURCES.has(source)) return;
  if (payload.agent_type) return;

  const root = process.env.CLAUDE_PROJECT_DIR || (typeof payload.cwd === "string" ? payload.cwd : process.cwd());
  if (!isGitRepo(root)) return;

  const programs = listPrograms(root);
  if (programs.length === 0) return;

  const waiting = [];
  const unknown = [];
  for (const remote of programs) {
    const fetched = git(root, ["fetch", "--quiet", remote, "student"], FETCH_TIMEOUT_MS);
    if (fetched.status !== 0) {
      unknown.push(remote);
      continue;
    }
    const behind = git(root, ["rev-list", "--count", `HEAD..${remote}/student`]);
    const count = behind.status === 0 ? Number(String(behind.stdout).trim()) : NaN;
    if (!Number.isFinite(count)) {
      unknown.push(remote);
      continue;
    }
    if (count === 0) continue;
    const notes = git(root, ["log", "--format=%s", `HEAD..${remote}/student`]);
    const subjects = notes.status === 0 ? String(notes.stdout).trim().split("\n").filter(Boolean).slice(0, 3) : [];
    waiting.push({ remote, count, subjects });
  }

  if (waiting.length === 0 && unknown.length === 0) return;
  emit(compose(waiting, unknown));
}

function compose(waiting, unknown) {
  const lines = [];
  for (const w of waiting) {
    const edition = w.count === 1 ? "1 edition" : `${w.count} editions`;
    lines.push(`An update is waiting for ${w.remote}: ${edition} behind. What the team published: ${w.subjects.join("; ") || "no notes"}. Nothing has changed here. Say "update" and the aibl-update skill shows what would change and merges it after your yes.`);
  }
  for (const u of unknown) {
    lines.push(`Could not check ${u} for updates (the fetch did not finish). Nothing has changed here. Ask for "update" later, or run the aibl-update skill to try again.`);
  }
  return lines.join(" ");
}

function listPrograms(root) {
  const res = git(root, ["remote"]);
  if (res.status !== 0) return [];
  return String(res.stdout)
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s && !SKIP_REMOTES.has(s));
}

function isGitRepo(root) {
  const res = git(root, ["rev-parse", "--is-inside-work-tree"]);
  return res.status === 0 && String(res.stdout).trim() === "true";
}

function git(cwd, args, timeout = 10000) {
  return spawnSync("git", args, {
    cwd,
    encoding: "utf8",
    timeout,
    env: { ...process.env, GIT_TERMINAL_PROMPT: "0" },
  });
}

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

function emit(text) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: text },
    }) + "\n",
  );
}

function isTruthy(v) {
  return typeof v === "string" && ["1", "true", "yes", "on"].includes(v.trim().toLowerCase());
}
