#!/usr/bin/env node
// The AIBL workbench update check. One implementation, two doors:
//
//   SessionStart hook (Claude Code reads .claude/settings.json in this workbench):
//     at the start of a NEW conversation, fetch what each connected program and the
//     template have published, and say in one sentence whether anything is waiting.
//   node .claude/hooks/update-check.mjs --json
//     the same check as a report; this is what aibl-update reads before it acts.
//   node .claude/hooks/update-check.mjs --agent-menu [--agent-menu-apply --expect <preview_sha256>
//                                                    [--replace-edited NAME] [--refresh-from-home]]
//     whether Claude Code's @ agent menu lists the course's agents from this workbench, and
//     whether the course's bridge skills are in the user's skills folder (see "The Claude
//     Code agent menu" below); the hook adds one line when they are not.
//   node .claude/hooks/update-check.mjs --home-workbench [--home-workbench-apply]
//     whether ~/.aibl/workbench.json records this workbench as the home workbench.
//   node .claude/hooks/update-check.mjs --seat-titles
//     whether a renamed Chief of Staff's title is written in two shapes (read-only; see below).
//
//   Team settings: a program never ships .claude/settings.json. A program that has settings of its
//   own ships a merge script (PROGRAM_SETTINGS below); the check runs that script's read-only preview
//   and reports, in the hook's one line, when the program's ask-before-sending rules are missing, so
//   a workbench updated by an older aibl-update (which had no settings step) still hears about it at
//   its next new conversation. The preview writes nothing; adding the settings is aibl-update's job.
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
// A program's own settings merge script, run with no arguments for a read-only JSON preview
// (status, adds[{where, value}]). The contract is the program's: agent-native-workforce-internal,
// workforce/house/settings-merge.mjs and its tests/test_program_settings.py.
const PROGRAM_SETTINGS = { "agent-workforce": "workforce/house/settings-merge.mjs" };
const SETTINGS_PREVIEW_TIMEOUT_MS = 15000;
const SKILL_FOLDERS = ["aibl-personalize", "aibl-checkpoint", "aibl-enroll", "aibl-update"]
  .flatMap((name) => [`.claude/skills/${name}`, `.agents/skills/${name}`]);
// The update paste: the one route that always runs the newest update procedure (aibl-installer START-HERE.md).
const UPDATE_PASTE_NAME = "Later: update your workbench";
const START_HERE_URL = "https://github.com/aibuild-lab/aibl-installer/blob/main/START-HERE.md";
const UPDATE_PROMPT_URL = "https://raw.githubusercontent.com/aibuild-lab/aibl-installer/main/UPDATE-PROMPT.md";
// the agent menu's files (see "The Claude Code agent menu"); declared up here because main() runs below
const AGENT_FILE = /^aibl-[a-z0-9-]+\.md$/;
// Tyler's ruling (09-24): the menu sync and its cleanup touch ONLY what the course itself
// shipped, never the student's own agents (in Claude Code or Codex, whatever their names,
// aibl- included) and never other course components; and the team is found, never kept as a
// roster here. The course's agents are the ones in the program's own list, which its publish
// step writes into every edition (agent-native-workforce-internal, scripts/student_branch.py):
// for each agent, whether it is current or retired, and the sha256 of every version the
// published student branch ever had of it, as committed (LF) and as Git for Windows checks it
// out (CRLF). It is read from this workbench's HEAD: one small file, offline, the same time
// whatever the history. A file is the course's only when its bytes are one of those versions.
const COURSE_AGENTS_FILE = ".aibl/course-agents.json";
// A seat the student named (Lesson 32): the course's naming step (aibl-agent-setup's name_seat.py)
// records the exact sha256 of every renamed agent file it leaves, in the workbench and in the
// global copy, here. Under work/, so a course update never touches it; read from the working tree.
const SEAT_NAMES_FILE = "work/course/staff/seat-names.json";
// The naming step as published before that record existed (agent-workforce up to 521234a) keeps
// only its table, "| Seat | Name | Named on | Your yes |", here, and rewrites one line of the agent
// file: the first "# " title line after the frontmatter, "[student names this agent], your Chief
// of Staff" becoming "Hestia, your Chief of Staff" (a later shape is "Chief of Staff (Hestia)").
// Read only when there is no SEAT_NAMES_FILE: a seat listed there with a name, whose file is a
// published version but for that one title line, is the student's renamed seat.
const LEGACY_SEAT_NAMES_FILE = "work/course/staff/seat-names.md";
const LEGACY_NAMED_SEATS = ["aibl-chief-of-staff", "aibl-ygm"];
const SEAT_PLACEHOLDER = "[student names this agent]";
const SEAT_SHIPPED_NAMES = { "aibl-ygm": "You've Got Mail" };
const COURSE_AGENTS_SCHEMA = 1;
// Backward compatibility, for that edition only: editions published before the list existed
// (agent-workforce up to 521234a) do not carry it, so a workbench whose HEAD has no list uses
// the eight agents those editions shipped, with every sha256 each had on the published branch
// in all ten of its commits (read 09-27), which is exactly today's behavior; it never grows.
const LEGACY_EDITION = {
  "aibl-charter-steward.md": {
    current: ["08f7b7959ee7618a177fd74c426fa0a92d11744f89c3f20fad14b870885e8cdc", "505e34a17087f2203d80f68290d17d9c741f2e677c955e2c622cf5192a4cd8bd"],
    published: [
      "08f7b7959ee7618a177fd74c426fa0a92d11744f89c3f20fad14b870885e8cdc",
      "330d1cd28fb0cde3e52e1bb23bd80acd746af6cb1d7192e1cc7bafc5e70ee3ba",
      "46e626898c69ccf0605d9eb37fd59499d9d37fbae076bdee75bb9e4d06fbd318",
      "505e34a17087f2203d80f68290d17d9c741f2e677c955e2c622cf5192a4cd8bd",
      "5cf9f1690db2d095a28f37905d4ac0e27c72862e616b50b09d4ce208d47bd623",
      "5de7a4ac06d4f6210a047769a8f750669914508519b450a04cab9a340af07844",
      "83f11b3b1d71ea690af17108ecfd1e186f05770cc41b1a586f01b17486e3a439",
      "a08cb5de3348980b7ef87bde88b66cd2330c426c7e8c1acb0f080721031befdf",
      "d9923d5ace969cfe79eeb4c7cd1d1a8dacf1c224a04e030e63429ad5f477be86",
      "fbcbcda828dc6428da20a59fb1f732aaba316afa0ed6005f12c37bfaa78857b0",
    ],
  },
  "aibl-chief-of-staff.md": {
    current: ["2f01c892c9946d4f5b0b073b4240da77c89a728694b1bf3a8ed03357c5d6d4fd", "fdfdf7f370357b20ed3979c9f6649afefb9d169703e316efb41353b4e54c0790"],
    published: [
      "2f01c892c9946d4f5b0b073b4240da77c89a728694b1bf3a8ed03357c5d6d4fd",
      "449f57519429e079585c5e957890bbb312a37f06da017e22c747d73b3fd83df4",
      "48151addb6d4fc1220ae4432a488ad034564389f7f278e4ac8a617fc0f0a349a",
      "485bca800541bb300bc3eb54027da5bd3bd3482b3914c2251eb99d003d518ba1",
      "492bb0583581d5cc1624ecc9bf023a74ff49206e9afe7c39d00654a98c47adac",
      "4c60419dd4cedf24d84bee8463c37eb4235a49c11cdb2bd65011ab197cc4180b",
      "595ac6a2f399c8a86d0b7480544059b18fb9ae2d0749f04d506e4cd82e5aa28b",
      "5c31a09bd19a7a7f25d9f3b58f3614f242922e04779f554ac0e35826f7c5bc67",
      "6bd00742287a88bdfda8e962afaface08cf68006e82badbff961c5af34dc77d2",
      "7f09bac4daccf39c1ef95d00009fd8f858466c6d950337440b0e38c58876aeea",
      "d85186e11851a6039cff6cc7ce92a11aad3345408f8969079b91c1993cee4f48",
      "fdfdf7f370357b20ed3979c9f6649afefb9d169703e316efb41353b4e54c0790",
    ],
  },
  "aibl-echo.md": {
    current: ["99cb4e69a94ae949b531bbb622b0301be8947a49a6a465f9638e1ded3e176f6f", "e00f5c7ef82449d2ad5942f3f1597a7b42d17c4c034e4a5136d2137dcc6c4307"],
    published: [
      "057367b2b2a981bef97c49d9015a5ad421ca6b81547eb0eb27104e53c6db6dc0",
      "06d3e559ee313bdb9c9df1369c48898947fe71a80408aff770408c27ab7bd2c8",
      "29f37a7e2bbd5ca3f5f4dade58a0ed8db318644e718166f171b5b1106023d2e1",
      "99cb4e69a94ae949b531bbb622b0301be8947a49a6a465f9638e1ded3e176f6f",
      "c8028fefab46127a7cf975bc6e1a285c7209f9eafe4e4211e3ca0e030f2be1e1",
      "cd2521c770c911666e670815ecc99ba7eebe103148639c67f728be86157c9445",
      "e00f5c7ef82449d2ad5942f3f1597a7b42d17c4c034e4a5136d2137dcc6c4307",
      "eaa6956ec04f3cad66bd070b14e6364f0a1722d3b573ff27117b34c3eaaa7241",
      "ef2a715982c1585b734966dc4fe3a9cba40aeb492e4052e2a4745e30ca02f3a2",
      "f65b8b041658209258bf58bfe3c179c1596d8eb30a31780d334aaade75563eb7",
    ],
  },
  "aibl-gigawatt.md": {
    current: ["559a7e18b683c11172e3e95dea12ad4a268651adb02a7b614ebeafd2587044c3", "ad7bbab3e8e6d0f563d97f865da761635ef3af4da2181c17845920f8e3cd4cdf"],
    published: [
      "3b1f45d964f88e22b6d8a1fc8b4b4175f56bcf6ef38e8e6baffcacae5e699ebf",
      "559a7e18b683c11172e3e95dea12ad4a268651adb02a7b614ebeafd2587044c3",
      "56321973ad7aa536e7bffa67d1478116f8365ceba51243c34f4536439beff392",
      "6402b41058dfbdb3e52e84316d98174dd1c843b4868c49fc542df236f1181297",
      "8c63ed59e03b4c3c531f169d813c5aff9cee30273ca729b839f529e15946cee8",
      "9aba3abf8ce07491f8c3472575fb0be313f6f33f3c31b6932afc8e3569f7ce5f",
      "ad7bbab3e8e6d0f563d97f865da761635ef3af4da2181c17845920f8e3cd4cdf",
      "d77018847b0ec2b52266917e29db50f7edaf4694ddf2203d4b2d6f964a0c590c",
    ],
  },
  "aibl-kansa.md": {
    current: ["4e19aa54e860d0f55a19dd6d19843f73f5a96edbf7718ff7175ed7c9ea5a1986", "a1b0c2f23604f73435d9f976d2568b3f8ed0a953cc3f8b5dc215763e8aa13932"],
    published: [
      "0206a3c6ffda85462bad51a8c3d37a727e6311d449d72f95234303aad93864d3",
      "4e19aa54e860d0f55a19dd6d19843f73f5a96edbf7718ff7175ed7c9ea5a1986",
      "8d5c6f254d4fb173f19bcbcf1f66cb3b729ee5da61c6c1a24844cacbfc3ba736",
      "9dc743c7d21f1e0b96bcc0aae6744aa65dfbb8c141f95dfc0bada30b2c3bf0ee",
      "a1b0c2f23604f73435d9f976d2568b3f8ed0a953cc3f8b5dc215763e8aa13932",
      "a91a76bff12141df2443cf20eb5d9020dcb80efcef83388a00fa4f6d81cc4c14",
      "baa0930148aca22b9031a1986724fa175613e2f79d4d43cd81c584dd7f0ef05b",
      "c00b1ba7252c1126e4440f98f00bb0492e05f1d050ca7cd2dcc4f6038dbb7ec0",
    ],
  },
  "aibl-librarian.md": {
    current: ["84010d9f9722d960d9121dd37f1422d34528f2a0fbb7cff94fe3df13725e8ac9", "e6e494a18778903ccbf0916748dd3bc05d3f2a569ebbdbc91967b9dc200bf338"],
    published: [
      "2045d993678ecffc4107a41a4005c4aa44638d639f7afd22f39369d0f748f6c9",
      "29ef912878ac315be89dd10f8a3878fc23120a85695ac5884d27ca05b483bf56",
      "3bde6d78e0c4853201bc9861962767d819353f09182635ee6eb170981ddf99e9",
      "4dc6a9dc7e9964591199d53465a5266b2c09e2d9a7d4939c1be3be1c3be7b093",
      "77abd6ec5f97b0d12e6f7a6c9504a268c4123e9b1582db539b16e47b4e2aea89",
      "84010d9f9722d960d9121dd37f1422d34528f2a0fbb7cff94fe3df13725e8ac9",
      "d85fe8eb4a16025ab5699e4260dc53077557641615d49772589e1b8f1bdaea10",
      "e6e494a18778903ccbf0916748dd3bc05d3f2a569ebbdbc91967b9dc200bf338",
    ],
  },
  "aibl-the-professor.md": {
    current: ["2ae3c21398d6a40e32c3d4e365231031812ddc0c00467a95498734e46f7b4968", "cafaa652352defe905a9f893500939974ad8b044656e7984c05561c3321491b3"],
    published: [
      "00398445e0c77878f18ee26929f62758beb9153a95e45b860712fce8dff2e94e",
      "18ae3dcaef845447e8b695d6d6ffe5a02481f8daa32570bd3096c094fee67413",
      "1dd7d59b34a05187d03f805803cb3b2c432ce6208724f5abfacc6ac1a24114ed",
      "232c355c711af0521c7ce2c5a50a431b94f01d8f99c35058f280c25a042dcb4e",
      "2ae3c21398d6a40e32c3d4e365231031812ddc0c00467a95498734e46f7b4968",
      "5ca093cd69d0533aa017958e9556c28acfbe2bacef8dddd4bb63cd1433b28769",
      "60d7d0d9e59fb05faf99d3ec998cc3c181178790ac340c500ab1a9ba2a1a78ff",
      "79f99dc6f21af515675288de41d0e6048d5364465536d563fbdc2e979c36089e",
      "987c4d92d19247aa9f45cd615943fec117a8d58bda9837c6e3426d8fcda07902",
      "a950ca21138ad60c811b8053a9b2c98fe17144fb7c3c1ab7332c268b5efe485f",
      "cafaa652352defe905a9f893500939974ad8b044656e7984c05561c3321491b3",
      "e26fa37a7afbdb7f740ef47652210af67621c1362d77257f2cdc2d00601dbcab",
    ],
  },
  "aibl-ygm.md": {
    current: ["d8e01e6d9bcec00ff0661990c633c94c8397d21872a5ff4ddbfd634aaaf91a24", "ff121e17b6c005dc02279743b667a4ae0b36fe024d245c1fd22b67042c6edba3"],
    published: [
      "080308f1383f2023878c3d2383f57e63961427aeee1b2fb82110813807e936dd",
      "117e776e7dcfc344c183f93dca63febf3c34a090522ffa5314d2ee90cefb8a5d",
      "612598b8a35e86348104300b0d7431a38a1cd97d7efa28ffb2e54d81faf5302f",
      "6223c8b764bad1cfbc575567921e804d19e5cb4ab3f3656a9a1ed508c02501c5",
      "70e7b6c1a6d739bb87a1ab8b492740a65bd918f98223ed4f5507f9803222cf38",
      "b785d795126e4279ce8251da77da25e40e8b780f71ec4d0eb63cd18060358611",
      "d8e01e6d9bcec00ff0661990c633c94c8397d21872a5ff4ddbfd634aaaf91a24",
      "ff121e17b6c005dc02279743b667a4ae0b36fe024d245c1fd22b67042c6edba3",
    ],
  },
};
// The course's bridge skills, kept as real copies in the user's skills folder so a thread
// opened outside this workbench still has them (workforce-internal #98).
const COURSE_SKILLS = ["aibl-bridge", "aibl-bridge-setup"];
// --seat-titles (see "A renamed Chief's title in two shapes" below); declared up here because main() runs below
const CHIEF_TITLE_FILES = [
  ".claude/agents/aibl-chief-of-staff.md",
  ".claude/agents/aibl-chief-of-staff-lead.md",
  ".codex/agents/aibl-chief-of-staff.toml",
  "workforce/profiles/aibl-chief-of-staff.capability-profile.yaml",
  "workforce/ROSTER.md",
];
// a title line, a profile display_name, or a roster entry: never the prose that mentions "your Chief of Staff"
const OLD_CHIEF_TITLE = /^(?:#\s+|display_name:\s*"?|title:\s*"?|- \*\*)([^,()"*\r\n]+?), your Chief of Staff\b/gm;
const NEW_CHIEF_TITLE = /^(?:#\s+|display_name:\s*"?|title:\s*"?|- \*\*)Chief of Staff \(([^()\r\n]+)\)/gm;
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
    } else if (process.argv.includes("--seat-titles")) {
      const root = resolveRoot({});
      const report = root ? seatTitles(root) : { status: "not_a_workbench" };
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    } else if (process.argv.includes("--agent-menu-apply")) {
      const root = resolveRoot({});
      const report = root ? applyAgentMenu(root, replaceEditedArgs(), argValue("--expect"), process.argv.includes("--refresh-from-home"))
        : { status: "not_a_workbench" };
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

function argValue(flag) {
  // --flag VALUE or --flag=VALUE; null when absent
  let value = null;
  process.argv.forEach((arg, i) => {
    if (arg === flag && process.argv[i + 1]) value = process.argv[i + 1];
    else if (arg.startsWith(`${flag}=`)) value = arg.slice(flag.length + 1);
  });
  return value;
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
    // Local, so it still answers when the fetch fails (offline).
    row.team_settings = teamSettings(root, remote);
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

// The program's team settings, from its own read-only preview. null when the program has none
// (or has not arrived yet); otherwise { status, missing_send_asks }. A link, a failure or a timeout
// is "unknown", never "in step".
function teamSettings(root, remote) {
  const rel = PROGRAM_SETTINGS[remote];
  if (!rel) return null;
  const script = path.join(root, ...rel.split("/"));
  try {
    if (!fs.lstatSync(script).isFile()) return { status: "unknown", missing_send_asks: [] };
  } catch {
    return null;
  }
  const r = spawnSync(process.execPath, [script], { cwd: root, encoding: "utf8", timeout: SETTINGS_PREVIEW_TIMEOUT_MS,
    stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
  try {
    const report = JSON.parse(String(r.stdout || ""));
    const adds = Array.isArray(report.adds) ? report.adds : [];
    const missing = adds.filter((a) => a && a.where === "permissions.ask" && String(a.value || "").startsWith("mcp__"))
      .map((a) => String(a.value));
    return { status: typeof report.status === "string" ? report.status : "unknown", missing_send_asks: missing };
  } catch {
    return { status: "unknown", missing_send_asks: [] };
  }
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
  if (report.skills.changed) parts.push("the workbench's own update skills (the aibl- core skills) are older than the template's");
  const settings = [];
  for (const p of report.programs) {
    const t = p.team_settings;
    if (t && t.missing_send_asks && t.missing_send_asks.length) {
      const n = t.missing_send_asks.length;
      settings.push(`${p.label}'s team settings are not in this workbench's .claude/settings.json yet, so the app will not ask ` +
        `before an agent sends a message (${n === 1 ? "1 send tool has" : `${n} send tools have`} no ask rule)`);
    }
  }
  if (!parts.length && !settings.length) return null;
  const all = [...parts, ...settings];
  // Decision 40 (WF-60): an out-of-date aibl-update cannot fix itself mid-run, and older copies
  // recommended merging around the files they did not know. When the core skills are behind,
  // the route is the update paste, which is fetched fresh every time and refreshes them first.
  const offer = report.skills.changed
    ? "Tell the student in one line and recommend the update paste, not aibl-update: this workbench's own copy of aibl-update " +
      `is older than the course's, and an older copy can't update itself mid-run. The paste is "${UPDATE_PASTE_NAME}" on the ` +
      `installer's Start Here page (${START_HERE_URL}); it fetches the newest update procedure (${UPDATE_PROMPT_URL}) every time ` +
      "and refreshes these skills before it touches any program. Offer to start it now by fetching that procedure and following " +
      "it from step 1; if you cannot fetch it, ask the student to paste it. Never call a partial update recommended. Do not run anything unasked."
    : settings.length
      ? "Tell the student in one line and offer aibl-update, which shows what changes and previews the team settings, adding them only on a yes. Do not run it unasked."
      : "Tell the student in one line and offer aibl-update, which shows what changes before merging. Do not run it unasked.";
  return `AIBL workbench update check, nothing was changed: ${all.join("; ")}. ${offer}`;
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
//   - It touches only the course's agents and COURSE_SKILLS. The course's agents are the
//     names in the program's list in this workbench's HEAD (COURSE_AGENTS_FILE), or the
//     editions from before the list (LEGACY_EDITION). A name proves nothing on its own: a
//     file is the course's only when its bytes are a version the list records for that name.
//     An aibl- agent in this workbench with other bytes is the student's (their own, or a
//     course agent they changed): skipped, never copied or recorded, and reported as a
//     name_conflict when it has a course name. The one exception is a seat the student named
//     (SEAT_NAMES_FILE): exactly the bytes the naming step left is `renamed`, a clean state;
//     anything else there is `rename_waiting`, one line pointing at the naming step's --reapply.
//     Neither is ever replaced or recorded, and an existing menu entry is left alone; a renamed
//     seat with no menu entry at all (a fresh clone) is added, add-only, like a missing agent. Anything else in the user's folders (the student's own agents and skills, aibl-
//     named or not, in any letter case) is not_ours and never touched. Codex's folders are
//     never touched.
//   - A missing name is copied only when nothing sits at that name in any letter case (Mac
//     and Windows folders ignore case): a clash is reported as case_conflict and skipped.
//   - An existing agent copy that differs from this workbench's is replaced only when its
//     bytes are a course version (CRLF or LF line endings alike: Git for Windows checks files
//     out with CRLF): those are changed, and the ones proven older than this workbench's
//     version are also listed as older. A record of having placed some bytes is not enough
//     (an older sync could have placed the student's own file under a course name). A copy
//     that matches another known workbench's current file is that workbench's
//     (other_workbench, kept), unless ~/.aibl/workbench.json names THIS workbench as home and
//     the copy is a course version: then the menu follows the home workbench, and the copy is
//     offered as from_other_workbench, replaced only with --refresh-from-home on its own yes
//     (decision 45, WF-16). Anything else is edited, kept; the agent asks the student,
//     and only --replace-edited NAME replaces it. Line endings alone are not a difference.
//     (A bridge skill copy is still course-made when its bytes are recorded as placed.)
//   - A leftover (a retired course agent) is removed only when this workbench's list says
//     it is retired and no newer edition already fetched ships it again, this workbench has
//     no file of that name, its bytes are a course version, this workbench is recorded as
//     having placed exactly those bytes, and no other known workbench (recorded holders,
//     the home pointer) still has that name.
//   - It records every copy it places, and every copy it finds already matching ("claim
//     without writing"), in ~/.claude/aibl-agent-menu-placed.json: only ever bytes the
//     course published.
//   - It never writes through a link and refuses a linked ~/.claude, agents, skills,
//     backup or staging folder. It holds a lock while it plans and applies.
//   - An agent copy is written to a temp file beside it and put in place by one rename, after
//     the entry is read again and found exactly as the preview saw it; any failure leaves
//     the entry as it was. Nothing is lost: a replaced copy, a link it converts, and a
//     leftover are first copied to a uniquely named, dated backup folder outside the folders
//     the app reads.

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

function lineEndingsAsCommitted(bytes) {
  // Git for Windows checks text out with CRLF line endings (core.autocrlf=true) and commits
  // it with LF, so a Windows copy of a published file is that file with \r\n for \n. A file
  // with a NUL byte is binary to git and is never converted.
  if (bytes.includes(0) || !bytes.includes("\r\n")) return null;
  return Buffer.from(bytes.toString("latin1").replace(/\r\n/g, "\n"), "latin1");
}

function gitBlobIds(file) {
  // the ids git would give these bytes, in both object formats: as they are, and as git
  // would commit them from a CRLF checkout (see lineEndingsAsCommitted)
  try {
    const raw = fs.readFileSync(file);
    const ids = [];
    for (const bytes of [raw, lineEndingsAsCommitted(raw)]) {
      if (!bytes) continue;
      const header = Buffer.from(`blob ${bytes.length}\0`);
      ids.push(createHash("sha1").update(header).update(bytes).digest("hex"),
        createHash("sha256").update(header).update(bytes).digest("hex"));
    }
    return ids;
  } catch {
    return [];
  }
}

// What a bridge skill entry is right now, so apply can tell whether it changed after the plan.
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

function olderVersion(copy, ours) {
  // proven older: both are versions the same course branch published, and ours came later.
  // Anything unproven (ours customized, a newer copy, a recorded copy) is not called older.
  return Boolean(copy && ours && copy.ref === ours.ref && copy.age > ours.age);
}

function readCourseList(root, rev) {
  // The program's list of its agents at rev: a Map of name -> { status, current, published },
  // undefined when rev has no list, null when it has one that does not read as the schema.
  const r = spawnSync("git", ["cat-file", "blob", `${rev}:${COURSE_AGENTS_FILE}`], gitOptions(root));
  if (r.status !== 0) return undefined;
  try {
    const parsed = JSON.parse(String(r.stdout));
    if (!parsed || parsed.version !== COURSE_AGENTS_SCHEMA || !parsed.agents || typeof parsed.agents !== "object") return null;
    const list = new Map();
    const hashes = (v) => (Array.isArray(v) ? v : []).filter((h) => typeof h === "string" && /^[0-9a-f]{64}$/.test(h));
    for (const [name, entry] of Object.entries(parsed.agents)) {
      if (!AGENT_FILE.test(name) || !entry || !["current", "retired"].includes(entry.status)) return null;
      const published = hashes(entry.published_sha256);
      if (!published.length) return null;
      list.set(name, { status: entry.status, current: new Set(hashes(entry.current_sha256)), published: new Set(published) });
    }
    return list;
  } catch {
    return null;
  }
}

function courseCatalog(root) {
  // The course's agents for this workbench: the list in its HEAD, or, when HEAD has none, the
  // editions from before the list (LEGACY_EDITION). A list that does not read names no agents.
  // A verified program branch fetched ahead of HEAD may vouch for newer versions of those same
  // names (a copy another workbench placed from the next edition is the course's, not edits)
  // and says which names its edition still ships; it never adds a name.
  const head = readCourseList(root, "HEAD");
  const agents = new Map();
  const from = head === undefined ? "legacy_edition" : head === null ? "unreadable" : "program";
  const base = head === undefined
    ? new Map(Object.entries(LEGACY_EDITION).map(([name, e]) => [name, { status: "current", current: new Set(e.current), published: new Set(e.published) }]))
    : head || new Map();
  for (const [name, e] of base) {
    agents.set(name, { status: e.status, current: e.current, here: e.published, published: new Set(e.published) });
  }
  const aheadCurrent = new Set();
  for (const ref of verifiedProgramRefs(root)) {
    const list = readCourseList(root, ref);
    if (!list) continue;
    for (const [name, e] of list) {
      if (e.status === "current") aheadCurrent.add(name);
      const mine = agents.get(name);
      if (mine) for (const h of e.published) mine.published.add(h);
    }
  }
  return { agents, from, aheadCurrent };
}

function readSeatNames(root) {
  // name -> { title, sums } from the naming step's record; empty when there is none or it does not read
  const names = new Map();
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, ...SEAT_NAMES_FILE.split("/")), "utf8"));
    if (!parsed || parsed.version !== 1 || !parsed.agents || typeof parsed.agents !== "object") return names;
    for (const [name, entry] of Object.entries(parsed.agents)) {
      if (!AGENT_FILE.test(name) || !entry || !Array.isArray(entry.sha256)) continue;
      const sums = new Set(entry.sha256.filter((h) => typeof h === "string" && /^[0-9a-f]{64}$/.test(h)));
      if (sums.size) names.set(name, { title: typeof entry.title === "string" ? entry.title : name, sums });
    }
  } catch { /* no record: no seat was named with it */ }
  return names;
}

function readLegacySeatNames(root) {
  // agent file name -> the name the published naming step recorded; empty when SEAT_NAMES_FILE
  // exists (it rules) or there is no table
  const names = new Map();
  if (exists(path.join(root, ...SEAT_NAMES_FILE.split("/")))) return names;
  let text;
  try { text = fs.readFileSync(path.join(root, ...LEGACY_SEAT_NAMES_FILE.split("/")), "utf8"); } catch { return names; }
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith("| ")) continue;
    const cells = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    if (cells.length >= 4 && LEGACY_NAMED_SEATS.includes(cells[0]) && cells[1]) names.set(`${cells[0]}.md`, cells[1]);
  }
  return names;
}

function titleNamed(bytes, seat, recordedName) {
  // The agent file with its title line's name put back to what the course shipped, if the title
  // line (the first "# " line after the frontmatter, the only line the naming step changes) names
  // recordedName: { title, shipped: [Buffer] }; otherwise null.
  if (!bytes) return null;
  const text = bytes.toString("utf8");
  if (!Buffer.from(text, "utf8").equals(bytes)) return null;
  const lines = text.split(/(?<=\n)/);
  const bare = (l) => l.replace(/\r?\n$/, "");
  if (!lines.length || bare(lines[0]) !== "---") return null;
  const close = lines.findIndex((l, i) => i > 0 && bare(l) === "---");
  if (close < 0) return null;
  let at = -1;
  for (let i = close + 1; i < lines.length; i += 1) {
    const content = bare(lines[i]);
    if (!content.trim()) continue;
    if (content.startsWith("# ")) at = i;
    break;
  }
  if (at < 0) return null;
  const body = bare(lines[at]);
  const ending = lines[at].slice(body.length);
  const value = body.slice(2);
  let parts = null;
  const titled = /^([^,()]+?) \(([^()]+)\)$/.exec(value);
  if (titled) parts = { name: titled[2], before: `${titled[1]} (`, after: ")" };
  else if (value.indexOf(", ") > 0) parts = { name: value.slice(0, value.indexOf(", ")), before: "", after: value.slice(value.indexOf(", ")) };
  if (!parts || parts.name !== recordedName) return null;
  const shipped = [SEAT_PLACEHOLDER, SEAT_SHIPPED_NAMES[seat]].filter(Boolean).map((n) =>
    Buffer.from([...lines.slice(0, at), `# ${parts.before}${n}${parts.after}${ending}`, ...lines.slice(at + 1)].join(""), "utf8"));
  // how the student hears it: "Chief of Staff (Hestia)", whichever shape the title line has
  const title = titled ? value : `${parts.after.slice(2).replace(/^your /, "")} (${parts.name})`;
  return { title, shipped };
}

function legacyRenamedTitle(entry, bytes, name, recordedName) {
  // the title, when these bytes are a published version of name but for the recorded name in its title
  const named = titleNamed(bytes, name.replace(/\.md$/, ""), recordedName);
  return named && named.shipped.some((b) => versionOf(entry, b)) ? named.title : null;
}

function versionOf(entry, bytes) {
  // Which course version these exact bytes are: null when they are none. The list already
  // carries each version as committed and as Git for Windows checks it out, so the bytes are
  // never normalized first (a mixed-ending file no version has is not the course's). here: a
  // version this workbench's own edition lists (so no newer than it); current: the version
  // that edition ships now.
  if (!entry || !bytes) return null;
  const sum = sha256(bytes);
  if (!entry.published.has(sum)) return null;
  return { here: entry.here.has(sum), current: entry.current.has(sum) };
}

function readBytes(file) {
  try { return fs.readFileSync(file); } catch { return null; }
}

function snapshot(p) {
  // What an entry is right now, from one read: its fingerprint (the same one the plan keeps
  // and the apply compares), and for a file its bytes. A link is fingerprinted by where it
  // points and what it reads there, so a change to either is a change.
  try {
    const st = fs.lstatSync(p);
    if (st.isSymbolicLink()) {
      const target = fs.readlinkSync(p);
      const content = readBytes(p);
      return { fp: `link:${target}:${content ? sha256(content) : "-"}`, link: true, target, content };
    }
    if (st.isFile()) {
      const bytes = fs.readFileSync(p);
      return { fp: `file:${sha256(bytes)}`, link: false, bytes, content: bytes };
    }
    return { fp: st.isDirectory() ? "dir" : "other", link: false };
  } catch {
    return { fp: "absent", link: false };
  }
}

function sameTextBytes(x, y) {
  // the same bytes, or the same bytes but for CRLF against LF line endings
  return Boolean(x && y) && (x.equals(y) || (lineEndingsAsCommitted(x) || x).equals(lineEndingsAsCommitted(y) || y));
}

function agentMenu(root, catalog = courseCatalog(root)) {
  const source = path.join(root, ".claude", "agents");
  const menu = menuFolder();
  const { agents } = catalog;
  const all = agentFiles(source).filter((name) => isRealFile(path.join(source, name)));
  const workbenchLower = new Set(all.map((name) => name.toLowerCase()));
  const ourBytes = {};
  const here = [];
  const skipped = [];
  // A seat the student named: its file is exactly what the naming step left (renamed, in step,
  // silent), or a course update has changed it since (rename_waiting: one line saying the
  // Technical Operator re-applies the name). Either way the hook never copies, replaces or
  // records it, and leaves its menu copy to the naming step, which refreshes it.
  const seatNames = readSeatNames(root);
  const legacySeatNames = readLegacySeatNames(root);
  const legacyRenamed = new Set(); // named by the published naming step, read from its table
  const renamed = [];
  const renameWaiting = [];
  const renameTitles = {};
  const renamedBytes = {};
  for (const name of all) {
    const bytes = readBytes(path.join(source, name));
    const named = agents.has(name) && seatNames.get(name);
    if (named && bytes) {
      renameTitles[name] = named.title;
      if (named.sums.has(sha256(bytes))) { renamed.push(name); renamedBytes[name] = bytes; } else renameWaiting.push(name);
      continue;
    }
    const legacyName = agents.has(name) && legacySeatNames.get(name);
    const legacyTitle = legacyName && legacyRenamedTitle(agents.get(name), bytes, name, legacyName);
    if (legacyTitle) {
      renameTitles[name] = legacyTitle;
      renamed.push(name);
      renamedBytes[name] = bytes;
      legacyRenamed.add(name);
      continue;
    }
    // the course's only with a course name AND the bytes of a version the course published
    if (versionOf(agents.get(name), bytes)) { here.push(name); ourBytes[name] = bytes; } else skipped.push(name);
  }
  const placed = readPlaced();
  const others = knownOtherWorkbenches(root, placed);
  // Decision 45 (WF-16): the menu follows the home workbench. Once ~/.aibl/workbench.json names this
  // workbench, a copy another workbench placed is offered here (from_other_workbench, its own yes,
  // --refresh-from-home), but only when its bytes are a version the course published; anything else
  // another workbench holds stays theirs (other_workbench), and edited copies are never replaced unasked.
  const isHome = homeWorkbench(root).status === "this_workbench";
  const fromOtherFolders = new Set();
  const byLower = entriesByLowerName(menu);
  const there = agentFiles(menu);
  const missing = [];
  // A renamed seat with no menu entry at all, in any letter case (a fresh clone on a new computer):
  // added exactly as the naming step left it, add-only. An entry already there is left alone.
  const renamedMissing = renamed.filter((name) => byLower.get(name.toLowerCase()) === undefined);
  const caseConflict = [];
  const changed = [];
  const older = []; // the part of changed proven to be an older course version than this workbench's
  const edited = [];
  const otherWorkbench = [];
  const fromOther = [];
  const inStepNames = [];
  const seen = {};
  for (const name of here) {
    const actual = byLower.get(name.toLowerCase());
    const dest = path.join(menu, name);
    if (actual === undefined) { missing.push(name); continue; }
    if (actual !== name) { caseConflict.push(`${actual} (in the way of ${name})`); continue; }
    const snap = snapshot(dest);
    seen[name] = snap.fp;
    const ours = ourBytes[name];
    // line endings alone (a CRLF checkout against an LF copy) are not a difference
    if (!snap.link && sameTextBytes(ours, snap.bytes)) { inStepNames.push(name); continue; }
    // another known workbench's current copy: theirs, unless this is the home workbench now and
    // the copy is a course version (then it is offered, on its own yes)
    const holder = snap.content ? others.find((wb) => {
      const theirs = readBytes(path.join(wb, ".claude", "agents", name));
      return Boolean(theirs && theirs.equals(snap.content));
    }) : undefined;
    if (holder) {
      if (isHome && !snap.link && versionOf(agents.get(name), snap.content)) {
        fromOther.push(name);
        fromOtherFolders.add(holder);
      } else {
        otherWorkbench.push(name);
      }
      continue;
    }
    const theirs = versionOf(agents.get(name), snap.content);
    const linkToOurs = snap.link && sameTextBytes(ours, snap.content);
    if (theirs || linkToOurs) {
      changed.push(name);
      // proven older: a version this workbench's own edition lists, but not the one it ships now,
      // while this workbench has the one it ships now
      const mine = versionOf(agents.get(name), ours);
      if (theirs && theirs.here && !theirs.current && mine && mine.current) older.push(name);
    } else {
      edited.push(name);
    }
  }
  // A course name in this workbench with bytes the course never published: the student's.
  // Never copied or recorded, and always reported, whatever the menu holds (both files are
  // left exactly as they are).
  const nameConflict = skipped.filter((name) => agents.has(name));
  // A seat named by the published naming step whose menu entry is an exact course copy: that copy
  // is replaced by the student's named file (previewed, --expect, the old copy kept in a backup).
  // Any other menu bytes are left alone and reported.
  const renamedReplace = [];
  const renamedMenuConflict = [];
  for (const name of renamed.filter((n) => legacyRenamed.has(n))) {
    if (byLower.get(name.toLowerCase()) !== name) continue; // missing: added below; another case: left alone
    const snap = snapshot(path.join(menu, name));
    if (!snap.link && snap.bytes && snap.bytes.equals(renamedBytes[name])) continue; // in step
    if (!snap.link && versionOf(agents.get(name), snap.bytes)) {
      renamedReplace.push(name);
      seen[name] = snap.fp;
    } else {
      renamedMenuConflict.push(name);
    }
  }
  const gone = there.filter((name) => !here.includes(name) && !renamed.includes(name) && !renameWaiting.includes(name));
  const leftover = gone.filter((name) => {
    const entry = agents.get(name);
    // retired in this workbench's edition, and not shipped again by a newer one already fetched
    if (!entry || entry.status !== "retired" || catalog.aheadCurrent.has(name)) return false;
    if (workbenchLower.has(name.toLowerCase())) return false; // this workbench still has a file of that name
    const snap = snapshot(path.join(menu, name));
    if (snap.link || !snap.bytes || !versionOf(entry, snap.bytes)) return false;
    if (!heldHere(placed, "agents", name, root, sha256(snap.bytes))) return false;
    // no other workbench this computer knows of still has it, in any form
    if (others.some((wb) => exists(path.join(wb, ".claude", "agents", name)))) return false;
    seen[name] = snap.fp;
    return true;
  });
  const notOurs = gone.filter((name) => !leftover.includes(name));
  // the bridge skills only come with the course's agents; a workbench with none gets none
  const skills = here.length ? bridgeSkills(root, placed, others, isHome)
    : { skills_folder: skillsFolder(), missing: [], changed: [], older: [], edited: [], other_workbench: [], from_other_workbench: [],
      case_conflict: [], in_step: [], seen: {}, errors: [] };
  for (const wb of skills.from_other_folders || []) fromOtherFolders.add(wb);
  delete skills.from_other_folders;
  const linked = linkedClaudeFolders();
  const empty = !here.length && !leftover.length && !nameConflict.length && !renameWaiting.length && !renamedMissing.length &&
    !renamedReplace.length && !renamedMenuConflict.length;
  const pending = missing.length + changed.length + leftover.length + skills.missing.length + skills.changed.length +
    renamedMissing.length + renamedReplace.length;
  const toAsk = edited.length + skills.edited.length + caseConflict.length + skills.case_conflict.length + nameConflict.length +
    renameWaiting.length + renamedMenuConflict.length + fromOther.length + skills.from_other_workbench.length;
  let status = empty ? "no_agents" : pending ? "out_of_step" : toAsk ? "needs_a_decision" : "in_step";
  if (linked.length && (pending || toAsk)) status = "linked_folder";
  const report = { status, workbench: root, menu_folder: menu, course_agents_from: catalog.from, missing, changed, older, edited,
    leftover, not_ours: notOurs, skipped, name_conflict: nameConflict, renamed, renamed_missing: renamedMissing,
    renamed_replace: renamedReplace, renamed_menu_conflict: renamedMenuConflict,
    rename_waiting: renameWaiting,
    rename_titles: renameTitles, other_workbench: otherWorkbench,
    from_other_workbench: fromOther, from_other_folders: [...fromOtherFolders].sort(), home_workbench: isHome,
    case_conflict: caseConflict, linked_folders: linked, skills, in_step: inStepNames, seen };
  // the bytes of each workbench agent the plan would copy: the apply writes only these exact bytes
  const sources = Object.fromEntries([...here.map((name) => [name, sha256(ourBytes[name])]),
    ...[...renamedMissing, ...renamedReplace].map((name) => [name, sha256(renamedBytes[name])])]);
  Object.defineProperty(report, "sources", { value: sources, enumerable: false });
  report.preview_sha256 = previewHash(report, root);
  return report;
}

function previewHash(report, root) {
  // What the preview showed, as one value: every list it showed, every entry it saw (the same
  // fingerprints the apply compares), and the exact bytes it would copy, agents and bridge
  // skills alike. --agent-menu-apply --expect VALUE refuses to act unless its own fresh plan
  // hashes to exactly this.
  const pick = (r) => ({ missing: r.missing, changed: r.changed, older: r.older, edited: r.edited, leftover: r.leftover,
    case_conflict: r.case_conflict, other_workbench: r.other_workbench, from_other_workbench: r.from_other_workbench,
    in_step: r.in_step, seen: r.seen });
  const skillSources = Object.fromEntries(COURSE_SKILLS.map((name) => [name, treeHash(path.join(root, ".claude", "skills", name))]));
  return sha256(Buffer.from(JSON.stringify({ agents: { ...pick(report), name_conflict: report.name_conflict, renamed: report.renamed,
    renamed_missing: report.renamed_missing, renamed_replace: report.renamed_replace,
    renamed_menu_conflict: report.renamed_menu_conflict,
    rename_waiting: report.rename_waiting, sources: report.sources },
    skills: { ...pick(report.skills), sources: skillSources } })));
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

function bridgeSkills(root, placed, others, isHome = false) {
  const folder = skillsFolder();
  const byLower = entriesByLowerName(folder);
  const out = { skills_folder: folder, missing: [], changed: [], older: [], edited: [], other_workbench: [], from_other_workbench: [],
    case_conflict: [], in_step: [], seen: {}, errors: [], from_other_folders: [] };
  // the workbench's own folder, as the plan saw it: the apply installs only exactly this
  const sources = {};
  Object.defineProperty(out, "sources", { value: sources, enumerable: false });
  for (const name of COURSE_SKILLS) {
    const src = path.join(root, ".claude", "skills", name);
    if (!isRealDir(src)) continue; // this workbench's edition does not have it
    const ours = treeHash(src);
    if (!ours) { out.errors.push(`${name}: the workbench copy holds a link, so it is not copied`); continue; }
    sources[name] = ours;
    const actual = byLower.get(name.toLowerCase());
    const dest = path.join(folder, name);
    if (actual === undefined) { out.missing.push(name); continue; }
    if (actual !== name) { out.case_conflict.push(`${actual} (in the way of ${name})`); continue; }
    out.seen[name] = fingerprint(dest);
    const theirs = isLink(dest) ? null : treeHash(dest);
    if (theirs === ours) { out.in_step.push(name); continue; }
    const holder = theirs ? others.find((wb) => treeHash(path.join(wb, ".claude", "skills", name)) === theirs) : undefined;
    if (holder) {
      // the home workbench takes over a course-made copy another workbench placed (decision 45), on its own yes
      const courseMade = (placed.skills[name] && placed.skills[name].hashes.includes(theirs)) ||
        Boolean(skillVersion(publishedSkillVersions(root, name), dest));
      if (isHome && courseMade) {
        out.from_other_workbench.push(name);
        out.from_other_folders.push(holder);
      } else {
        out.other_workbench.push(name);
      }
      continue;
    }
    const linkToOurs = isLink(dest);
    const recorded = Boolean(theirs && placed.skills[name] && placed.skills[name].hashes.includes(theirs));
    // the same files, only a lost exec bit (the 09-23 failure): still the course's copy
    const modesOnly = Boolean(theirs && treeHash(dest, false) === treeHash(src, false));
    // any version the course ever published, at any commit of its branch, in either line ending
    const versions = theirs ? publishedSkillVersions(root, name) : [];
    const published = theirs ? skillVersion(versions, dest) : null;
    if (recorded || linkToOurs || modesOnly || published) {
      out.changed.push(name);
      if (olderVersion(published, skillVersion(versions, src))) out.older.push(name);
    } else {
      out.edited.push(name);
    }
  }
  return out;
}

function publishedSkillVersions(root, name) {
  // every version of this skill folder a verified program branch has published: its files
  // and their blob ids, with how recent it is (0 = the newest commit that touched it)
  const prefix = `.claude/skills/${name}/`;
  const versions = [];
  for (const ref of verifiedProgramRefs(root)) {
    const commits = git(root, ["log", "--topo-order", "--format=%H", ref, "--", prefix])
      .split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    commits.forEach((commit, age) => {
      const files = new Map();
      for (const entry of git(root, ["ls-tree", "-r", "-z", "--full-tree", commit, "--", prefix]).split("\0")) {
        const m = entry.match(/^\d+ blob ([0-9a-f]+)\t(.+)$/);
        if (m && m[2].startsWith(prefix)) files.set(m[2].slice(prefix.length), m[1]);
      }
      if (files.size) versions.push({ ref, age, files });
    });
  }
  return versions;
}

function skillVersion(versions, dir) {
  // the most recent published version whose files these exactly are (Finder and Explorer
  // litter aside), in either line ending; null when none is
  const rels = isRealDir(dir) ? realTree(dir) : null;
  if (!rels) return null;
  return versions.find((v) => v.files.size === rels.length && rels.every((rel) => {
    const id = v.files.get(rel.split(path.sep).join("/"));
    return Boolean(id) && gitBlobIds(path.join(dir, rel)).includes(id);
  })) || null;
}

function copySkill(root, name, dest, keep, expected) {
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
    // the staged copy must be exactly the folder the plan (and the preview) saw
    if (!expected || treeHash(staging) !== expected) throw Object.assign(new Error("changed"), { code: "changed_since_check" });
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

function applyAgentMenu(root, replaceEdited, expect, refreshFromHome = false) {
  const unlock = takeLock();
  if (!unlock) {
    return { status: "busy", explain: "Another agent-menu update is running right now. Nothing was changed; try again in a minute." };
  }
  try {
    return applyLocked(root, replaceEdited, expect, refreshFromHome);
  } finally {
    unlock();
  }
}

function releaseOthers(placed, group, name, root) {
  // this workbench now holds the copy: no other workbench is recorded as holding that name
  const entry = placed[group][name];
  if (!entry) return;
  for (const wb of Object.keys(entry.holders)) if (!sameWorkbench(wb, root)) delete entry.holders[wb];
}

function applyLocked(root, replaceEdited, expect, refreshFromHome = false) {
  // one reading of the course's list for the plan and for every check below
  const catalog = courseCatalog(root);
  const plan = agentMenu(root, catalog);
  // Nothing is written without the student's yes to one exact preview: --expect is required.
  if (!expect) {
    return { ...plan, applied: null, refused: "no_preview",
      explain: "Nothing was changed: an apply needs --expect with the preview_sha256 of the preview the student said " +
        "yes to. Run the preview, show it, ask, and pass that value." };
  }
  if (expect !== plan.preview_sha256) {
    return { ...plan, applied: null, refused: "changed_since_preview",
      explain: "Something in the menu or this workbench changed since the preview, so nothing was changed. Run the " +
        "preview again and ask again." };
  }
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
    taken_from_other_workbench: [], removed_to: null, errors: [] };
  const backupFolder = () => {
    if (!exists(backup)) { fs.mkdirSync(backupRoot(), { recursive: true }); fs.mkdirSync(backup); }
    done.removed_to = backup;
    return backup;
  };
  const keep = (from, rel) => {
    // the bridge skills' folders only (see copySkill); agent copies are never moved aside
    const to = path.join(backupFolder(), rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    if (exists(to)) throw Object.assign(new Error("backup exists"), { code: "EEXIST" });
    fs.renameSync(from, to);
  };
  const approved = (name, list) => replaceEdited.includes(name) && list.includes(name);
  fs.mkdirSync(menu, { recursive: true });

  // Agent writes. Nothing in the menu is ever moved aside first:
  //   1. the course bytes are read from the workbench once and proven a course version;
  //   2. they are written to a new temp file in the menu folder (a name the app never lists)
  //      and flushed to disk;
  //   3. the entry in the menu is read once more and must still be exactly what the preview saw;
  //   4. a copy of that entry (a link as a link) is written to the dated backup folder;
  //   5. one rename puts the temp file in its place (for a missing entry, a hard link that
  //      fails if anything has appeared there since).
  // Any failure removes only the temp file; the entry in the menu stays exactly as it was.
  const courseBytes = (name) => {
    // exactly the bytes the plan saw in the workbench, and a course version
    const bytes = fs.readFileSync(path.join(source, name));
    if (sha256(bytes) !== plan.sources[name]) throw Object.assign(new Error("changed"), { code: "changed_since_check" });
    if (!versionOf(catalog.agents.get(name), bytes)) {
      throw Object.assign(new Error("not a course version"), { code: "not_a_course_version" });
    }
    return bytes;
  };
  const writeAll = (file, bytes) => {
    // a new file (never an existing one or a link), every byte written, flushed to disk; on
    // any failure the partial file is removed
    const fd = fs.openSync(file, "wx");
    try {
      try {
        for (let at = 0; at < bytes.length;) at += fs.writeSync(fd, bytes, at, bytes.length - at);
        fs.fsyncSync(fd);
      } finally {
        fs.closeSync(fd);
      }
    } catch (error) {
      try { fs.unlinkSync(file); } catch { /* never made */ }
      throw error;
    }
  };
  const staged = (bytes) => {
    const temp = path.join(menu, `.aibl-agent-menu-${uniqueStamp()}.tmp`);
    writeAll(temp, bytes);
    return temp;
  };
  const dropTemp = (temp) => { try { fs.unlinkSync(temp); } catch { /* already in place, or never made */ } };
  const backupCopy = (snap, rel) => {
    const to = path.join(backupFolder(), rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    if (snap.link) fs.symlinkSync(snap.target, to);
    else writeAll(to, snap.bytes);
    return to;
  };
  const changedSinceCheck = (name, error) => {
    if (error && error.code === "changed_since_check") { done.skipped_changed_since_check.push(name); return true; }
    return false;
  };

  // claim without writing: copies that already match this workbench's are recorded as held here
  for (const name of plan.in_step) {
    const snap = snapshot(path.join(menu, name));
    if (snap.link || !versionOf(catalog.agents.get(name), snap.bytes)) { done.skipped_changed_since_check.push(name); continue; }
    hold(placed, "agents", name, root, sha256(snap.bytes));
    done.claimed.push(name);
  }
  for (const name of plan.missing) {
    const dest = path.join(menu, name);
    let temp = null;
    try {
      const bytes = courseBytes(name);
      temp = staged(bytes);
      try {
        fs.linkSync(temp, dest); // fails if anything sits at that name, in any letter case on Mac and Windows
      } catch (error) {
        if (error.code === "EEXIST") { done.skipped_changed_since_check.push(name); continue; }
        // a folder without hard links: a new file (never over anything), written in full and
        // flushed, and removed again if the write fails
        writeAll(dest, bytes);
      }
      hold(placed, "agents", name, root, sha256(bytes));
      done.copied.push(name);
    } catch (error) {
      if (error.code === "EEXIST") done.skipped_changed_since_check.push(name);
      else if (!changedSinceCheck(name, error)) done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    } finally {
      if (temp) dropTemp(temp);
    }
  }
  // A renamed seat missing from the menu: its exact renamed bytes, as the plan saw them, added the
  // same add-only way. It is the student's own file, so it is never recorded as a course copy.
  for (const name of plan.renamed_missing) {
    const dest = path.join(menu, name);
    let temp = null;
    try {
      const bytes = fs.readFileSync(path.join(source, name));
      if (sha256(bytes) !== plan.sources[name]) { done.skipped_changed_since_check.push(name); continue; }
      temp = staged(bytes);
      try {
        fs.linkSync(temp, dest);
      } catch (error) {
        if (error.code === "EEXIST") { done.skipped_changed_since_check.push(name); continue; }
        writeAll(dest, bytes);
      }
      done.copied.push(name);
    } catch (error) {
      if (error.code === "EEXIST") done.skipped_changed_since_check.push(name);
      else done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    } finally {
      if (temp) dropTemp(temp);
    }
  }
  // A seat named by the published naming step, whose menu entry is still the course's copy: the
  // student's named file, exactly as the plan saw it, replaces it the same safe way (the course copy
  // kept in the backup). The named file is the student's, so it is never recorded as a course copy.
  for (const name of plan.renamed_replace) {
    const dest = path.join(menu, name);
    let temp = null;
    try {
      const bytes = fs.readFileSync(path.join(source, name));
      if (sha256(bytes) !== plan.sources[name]) { done.skipped_changed_since_check.push(name); continue; }
      temp = staged(bytes);
      const before = snapshot(dest);
      if (before.fp !== plan.seen[name]) { done.skipped_changed_since_check.push(name); continue; }
      const kept = backupCopy(before, path.join("replaced", name));
      if (snapshot(dest).fp !== plan.seen[name]) {
        try { fs.unlinkSync(kept); } catch { /* leave it; it is only a copy */ }
        done.skipped_changed_since_check.push(name);
        continue;
      }
      fs.renameSync(temp, dest);
      temp = null;
      release(placed, "agents", name, root);
      done.replaced.push(name);
      done.copied.push(name);
    } catch (error) {
      done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    } finally {
      if (temp) dropTemp(temp);
    }
  }
  // the home workbench's copies replace the course copies another workbench placed, only on --refresh-from-home
  const takeOver = refreshFromHome && plan.home_workbench ? plan.from_other_workbench : [];
  for (const name of [...plan.changed, ...plan.edited.filter((n) => approved(n, plan.edited)), ...takeOver]) {
    const dest = path.join(menu, name);
    let temp = null;
    try {
      const bytes = courseBytes(name);
      temp = staged(bytes);
      const before = snapshot(dest);
      if (before.fp !== plan.seen[name]) { done.skipped_changed_since_check.push(name); continue; }
      const kept = backupCopy(before, path.join("replaced", name));
      // the last look, with nothing but this one read between it and the rename
      if (snapshot(dest).fp !== plan.seen[name]) {
        try { fs.unlinkSync(kept); } catch { /* leave it; it is only a copy */ }
        done.skipped_changed_since_check.push(name);
        continue;
      }
      fs.renameSync(temp, dest); // replaces the entry itself; a link's target is never written
      temp = null;
      hold(placed, "agents", name, root, sha256(bytes));
      if (takeOver.includes(name)) { releaseOthers(placed, "agents", name, root); done.taken_from_other_workbench.push(name); }
      done.replaced.push(name);
      done.copied.push(name);
    } catch (error) {
      if (!changedSinceCheck(name, error)) done.errors.push(`${name}: ${error.code || "copy_failed"}`);
    } finally {
      if (temp) dropTemp(temp);
    }
  }
  for (const name of plan.leftover) {
    const dest = path.join(menu, name);
    try {
      const snap = snapshot(dest);
      if (snap.fp !== plan.seen[name] || snap.link || !versionOf(catalog.agents.get(name), snap.bytes)) {
        done.skipped_changed_since_check.push(name);
        continue;
      }
      const kept = backupCopy(snap, name); // the backup copy is on disk before the entry goes
      if (snapshot(dest).fp !== plan.seen[name]) {
        try { fs.unlinkSync(kept); } catch { /* leave it; it is only a copy */ }
        done.skipped_changed_since_check.push(name);
        continue;
      }
      fs.unlinkSync(dest);
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
  const skillsTakeOver = refreshFromHome && plan.home_workbench ? sk.from_other_workbench : [];
  for (const name of [...sk.missing, ...sk.changed, ...sk.edited.filter((n) => approved(n, sk.edited)), ...skillsTakeOver]) {
    if (!COURSE_SKILLS.includes(name)) continue;
    const dest = path.join(skillsFolder(), name);
    try {
      const expected = sk.missing.includes(name) ? "absent" : sk.seen[name];
      if (fingerprint(dest) !== expected) { done.skipped_changed_since_check.push(`skill ${name}`); continue; }
      copySkill(root, name, dest, keep, sk.sources[name]);
      hold(placed, "skills", name, root, treeHash(dest));
      if (skillsTakeOver.includes(name)) {
        releaseOthers(placed, "skills", name, root);
        done.taken_from_other_workbench.push(`skill ${name}`);
      }
      done.skills_copied.push(name);
    } catch (error) {
      if (!changedSinceCheck(`skill ${name}`, error)) done.errors.push(`skill ${name}: ${error.code || "copy_failed"}`);
    }
  }
  try { fs.rmdirSync(stagingRoot()); } catch { /* not empty or never made */ }
  try { writePlaced(placed); } catch (error) { done.errors.push(`record: ${error.code || "write_failed"}`); }
  return { ...agentMenu(root), applied: done, next: "Quit the app fully and open it again: the menu reads this folder only at launch. Then start a new thread before typing @." };
}

function describeAgentMenu(menu) {
  if (!menu || !["out_of_step", "needs_a_decision", "linked_folder"].includes(menu.status)) return null;
  const bits = [];
  const older = [...menu.older, ...menu.skills.older];
  const differ = menu.changed.filter((n) => !menu.older.includes(n));
  const skillsDiffer = menu.skills.changed.filter((n) => !menu.skills.older.includes(n));
  if (menu.missing.length) bits.push(`not in the @ agent menu yet: ${menu.missing.join(", ")}`);
  const titleOf = (name) => (menu.rename_titles || {})[name] || name;
  for (const name of menu.renamed_missing || []) {
    bits.push(`your renamed ${titleOf(name)} is not in the @ agent menu yet (${name})`);
  }
  for (const name of menu.renamed_replace || []) {
    bits.push(`the @ agent menu still has the course's copy of your renamed ${titleOf(name)} (${name}); the fix puts your named version there, and the course's copy goes to a backup`);
  }
  for (const name of menu.renamed_menu_conflict || []) {
    bits.push(`the @ agent menu has a copy of your renamed ${titleOf(name)} (${name}) that is neither your named version nor a course version, so it is left alone`);
  }
  if (older.length) bits.push(`older course versions in the user folder (this workbench has a newer course version): ${older.join(", ")}`);
  if (differ.length) bits.push(`course copies in the menu that differ from this workbench's: ${differ.join(", ")}`);
  if (menu.leftover.length) bits.push(`left over in the menu from a retired seat: ${menu.leftover.join(", ")}`);
  if (menu.skills.missing.length) bits.push(`bridge skills not yet available outside this workbench: ${menu.skills.missing.join(", ")}`);
  if (skillsDiffer.length) bits.push(`bridge skill copies that differ from this workbench's: ${skillsDiffer.join(", ")}`);
  const edited = [...menu.edited, ...menu.skills.edited];
  if (edited.length) bits.push(`copies in the user folder with changes that are not from any course version (never replaced unasked): ${edited.join(", ")}`);
  const clashes = [...menu.case_conflict, ...menu.skills.case_conflict];
  if (clashes.length) bits.push(`files whose names differ only in capital letters are in the way (never touched): ${clashes.join(", ")}`);
  const fromOther = [...(menu.from_other_workbench || []), ...((menu.skills.from_other_workbench || []).map((n) => `skill ${n}`))];
  const otherNames = (menu.from_other_folders || []).map((wb) => path.basename(wb));
  if (fromOther.length) {
    bits.push(`this is the home workbench now, but ${fromOther.length === 1 ? "1 menu entry is" : `${fromOther.length} menu entries are`} ` +
      `still the copies another workbench (${otherNames.join(", ")}) placed: ${fromOther.join(", ")}`);
  }
  const conflicts = menu.name_conflict || [];
  const waiting = menu.rename_waiting || [];
  for (const name of waiting) {
    bits.push(`a course update for your renamed ${(menu.rename_titles || {})[name] || name} is waiting; Gigawatt re-applies your name`);
  }
  if (conflicts.length) bits.push(`name conflicts, agents in this workbench named like a course agent but matching no version the course published, so they are treated as the student's own and never copied to the menu or recorded as course copies: ${conflicts.join(", ")}`);
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
    "Only on their yes, run `node .claude/hooks/update-check.mjs --agent-menu-apply --expect <preview_sha256 from that preview>` yourself, say what it changed, " +
    "then tell them to quit the app fully and reopen it. In that one offer, name each older course version in these words, " +
    "and recommend yes: \"Your copy of NAME is an older course version; update it to the current one? The old copy goes " +
    "to a backup.\" For a copy with changes that are not from the course, ask separately (\"Your copy of NAME has changes " +
    "that aren't from the course; replace it with the course version? The old one goes to a backup.\") and only on that " +
    "yes add `--replace-edited NAME`. Such a copy may be an agent of their own that only shares a course agent's name: " +
    "if they say so, recommend no, and suggest they rename theirs without the aibl- prefix. If they would rather not, drop " +
    "it for this conversation." +
    (fromOther.length ? " Ask about the copies from the other workbench separately, in these words (with the real folder name " +
      `and count): "Your agent menu is still using labels from your other workbench, **${otherNames[0] || "NAME"}**, for ` +
      `${fromOther.length} ${fromOther.length === 1 ? "agent" : "agents"}. Your agents themselves are up to date: when you pick one here, ` +
      "your current workbench's version runs. Only the short descriptions in the menu are older. Want me to refresh the menu " +
      "from this workbench? (yes / no)\" Recommend yes, because this is the workbench they chose as home, and say the old copies " +
      "go to a backup. Only on that yes add `--refresh-from-home` to the apply. It replaces only copies whose contents are a " +
      "version the course published; edited copies keep their own question." : "") +
    (waiting.length ? " For each renamed seat with a course update waiting, tell the student that line as it is and " +
      "that the Technical Operator (Gigawatt) re-applies their name: it runs " +
      "`python3 workforce/skills/aibl-agent-setup/scripts/name_seat.py --reapply` itself, which puts the name back into " +
      "the new version and refreshes the menu copy; do not hand them the command, and nothing needs applying here." : "") +
    (conflicts.length ? " For each name conflict, tell the student plainly that the file in this workbench has the same " +
      "name as a course agent but is not a course version (their own agent, or a course agent they changed here), so the " +
      "menu sync leaves it and the menu alone; if it is an agent of their own, suggest renaming it without the aibl- " +
      "prefix. There is nothing to apply for it." : "");
}

// ---------------------------------------------------------------------------
// A renamed Chief's title in two shapes (decision 45, WF-58)
// ---------------------------------------------------------------------------
//
// The naming step writes a seat's name into its title. An older edition's title read
// "Spyro, your Chief of Staff"; the current one reads "Chief of Staff (Spyro)". A student who
// renamed their Chief and then combined an update's conflict by hand (before template a8e4644,
// 09-29) can end up with both shapes across the Chief's files. name_seat.py --reapply keeps the
// shape each line has, so it never tidies that. --seat-titles reports it, read-only; aibl-update
// offers the repair: take the program's copy of the old-shape files, then --reapply writes the
// recorded name back in the current shape. It never guesses a name: with no record it says so.
function recordedChiefName(root) {
  // the name the naming step recorded: seat-names.json's title, else the seat-names.md table
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, ...SEAT_NAMES_FILE.split("/")), "utf8"));
    const entry = parsed && parsed.agents && parsed.agents["aibl-chief-of-staff.md"];
    const m = entry && typeof entry.title === "string" ? /\(([^()]+)\)\s*$/.exec(entry.title) || /^([^,]+), /.exec(entry.title) : null;
    if (m && m[1].trim() && m[1].trim() !== SEAT_PLACEHOLDER) return m[1].trim();
  } catch { /* no json record */ }
  try {
    const text = fs.readFileSync(path.join(root, ...LEGACY_SEAT_NAMES_FILE.split("/")), "utf8");
    for (const line of text.split(/\r?\n/)) {
      const cells = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      if (line.startsWith("| ") && cells.length >= 4 && cells[0] === "aibl-chief-of-staff" && cells[1]) return cells[1];
    }
  } catch { /* no table */ }
  return null;
}

function seatTitles(root) {
  const oldShape = [];
  const newShape = [];
  const names = new Set();
  for (const rel of CHIEF_TITLE_FILES) {
    const file = path.join(root, ...rel.split("/"));
    if (!isRealFile(file)) continue;
    let text;
    try { text = fs.readFileSync(file, "utf8"); } catch { continue; }
    const olds = [...text.matchAll(OLD_CHIEF_TITLE)].map((m) => m[1].trim());
    const news = [...text.matchAll(NEW_CHIEF_TITLE)].map((m) => m[1].trim());
    if (olds.length) oldShape.push(rel);
    if (news.length) newShape.push(rel);
    for (const n of [...olds, ...news]) if (n !== SEAT_PLACEHOLDER) names.add(n);
  }
  const recorded = recordedChiefName(root);
  const base = { seat: "aibl-chief-of-staff", recorded_name: recorded, names_found: [...names].sort(),
    old_shape: oldShape, new_shape: newShape };
  if (!oldShape.length || !newShape.length) {
    return { status: recorded ? "one_shape" : "not_named", ...base, fix: [] };
  }
  if (!recorded) {
    return { status: "two_shapes_no_record", ...base, fix: [],
      explain: "The Chief's title is written two ways, and there is no saved name to write back. Ask the student for the name; never guess." };
  }
  return { status: "two_shapes", ...base, fix: oldShape,
    explain: "Take the program's copy of each file in fix, then run name_seat.py --reapply, which writes the recorded name back in the current shape." };
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
