---
name: aibl-enroll
description: Connect a program you have joined (Agent Workforce, The Lab) to this workbench. Checks access in your signed-in account and prepares an exact package preview when supported.
---

# Enroll

Use this skill when the student wants to inspect or add a program. Access follows the cohort schedule; the first live session is not proof that files are available. Check the signed-in account instead of guessing from a date.

## What it does

1. Find the installer on this computer: `~/GitHub/aibl-installer` (Windows: `$HOME\GitHub\aibl-installer`). If it is missing, say: "The installer that built this workbench is not on this computer. Paste the setup prompt from your program page again; it puts the installer back without touching your workbench."
2. From the workbench folder, run:
   - Mac: `python3 ~/GitHub/aibl-installer/scripts/enroll.py --workbench "$PWD" --check --json`
   - Windows: `py -3 $HOME\GitHub\aibl-installer\scripts\enroll.py --workbench "$PWD" --check --json` (or `python` if `py` is absent)

   `--check` reads only. It asks GitHub which program repositories this account can read and changes nothing.
3. Read the JSON. Show one line per program: which ones this account can read, and which are already connected. If none are readable, say: "Nothing to add yet. Check your cohort access in Learn, then run this again." Do not guess why a program is missing or claim an invitation is pending.
4. If a program is readable and they choose it, ask once for their confirmation, then rerun with `--yes --program <id> --json` instead of `--check`. Never call the interactive selector from the app. This records the choice only.
5. For a workbench with `.aibl/family.json` using `aibl.family-lock/v2`, use the retained installer's existing import route: `--preview --program <id> --json`. Show its exact planned additions and conflicts. After the student confirms that plan, run `--apply-plan <plan_id> --json`, using the `plan_id` returned by preview. Check the installed receipt and list the new files. If the lock, bundle, access, or preview is missing, stop with that named hold. Do not substitute a current branch, download an unpinned package, or overwrite student files.
6. Older workbenches keep their original selected adoption route. If that route names a skill that is not installed, report the missing skill and request the reviewed package or frozen distribution update. Selection alone is never installation.

## Missing a program they paid for?

Give them what to send to their program's channel: the program name and their GitHub username (`gh api user --jq .login`). Do not troubleshoot invitations from here.

Never pull a newer installer. Never delete or replace anything in the workbench.

## Attribution

Original AIBL method. MIT, like the rest of this template.
