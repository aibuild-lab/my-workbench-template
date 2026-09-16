---
name: aibl-enroll
description: Connect a program you have joined (Agent Workforce, The Lab) to this workbench. Lists nothing until your program's first live session, and that is expected.
---

# Enroll

This skill is for the day a program starts. Before that day it lists nothing, because a program's repository is unlocked at its first live session. If they run it early, say exactly that and stop. Nothing is wrong.

## What it does

1. Find the installer on this computer: `~/GitHub/aibl-installer` (Windows: `$HOME\GitHub\aibl-installer`). If it is missing, say: "The installer that built this workbench is not on this computer. Paste the setup prompt from your program page again; it puts the installer back without touching your workbench."
2. From the workbench folder, run:
   - Mac: `python3 ~/GitHub/aibl-installer/scripts/enroll.py --workbench "$PWD" --check --json`
   - Windows: `py -3 $HOME\GitHub\aibl-installer\scripts\enroll.py --workbench "$PWD" --check --json` (or `python` if `py` is absent)

   `--check` reads only. It asks GitHub which program repositories this account can read and changes nothing.
3. Read the JSON. Show one line per program: which ones this account can read, and which are already connected. If none are readable, say: "Nothing to add yet. Your program's repository unlocks at your first live session. Run me again that day." Do not guess why a program is missing.
4. If a program is readable and they want it: run the same command without `--check`, with `--program <id>`. It records the choice and names the next step for that program. It does not install files by itself; the program's own step does that, and it will say so.

## Missing a program they paid for?

Give them what to send to their program's channel: the program name and their GitHub username (`gh api user --jq .login`). Do not troubleshoot invitations from here.

Never pull a newer installer. Never delete or replace anything in the workbench.

## Attribution

Original AIBL method. MIT, like the rest of this template.
