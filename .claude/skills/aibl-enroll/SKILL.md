---
name: aibl-enroll
description: Connect a program you have joined (Agent Workforce, The Lab) to this workbench. Shows what will be added, waits for a yes, then merges the program's files in. Lists nothing until your program has opened your access, and that is expected.
---

# Enroll

A program is a folder of files kept on a GitHub branch only its students can read. Enrolling means adding that branch as a remote of this workbench and merging it in, once. Updates later are `aibl-update`. Nothing here creates a second workbench, and nothing here touches `context/`, `library/`, `work/`, `CLAUDE.md` or `AGENTS.md`.

## The programs

| Program | Remote name | Repository | Branch |
|---|---|---|---|
| Agent Workforce | `agent-workforce` | `https://github.com/aibuild-lab/agent-workforce.git` | `student` |
| The Lab | `the-lab` | `https://github.com/aibuild-lab/the-lab.git` | `student` |

If `~/GitHub/aibl-installer/course-options.json` exists and disagrees with this table, the installer's file wins; say so.

## What to do

1. **Check access, change nothing.** For each program not yet connected (`git remote` does not list its remote name), run `gh api repos/<owner/repo> --jq .full_name`. Readable means the student can enroll. A 404 means their access has not opened yet: say "Nothing to add yet. Your program's access opens on its schedule; check your cohort on the Learn dashboard at https://learn.aibuildlab.com/ and run me again then." Do not guess why. If they are missing a program they paid for, give them what to send to their program's channel: the program name and `gh api user --jq .login`.
2. **Ask which readable program to connect**, if more than one. Then, from the workbench folder:
   ```
   git remote add <remote> <repository>
   git fetch <remote> student
   ```
   If the fetch is refused for authentication, run `gh auth setup-git` once and fetch again. If the branch does not exist yet, say the program has not published its files and stop; remove the remote you added.
3. **Show what will be added, then wait.** Run `git ls-tree -r --name-only <remote>/student`. Say how many files, and list the top-level folders (for Workforce: `course/workforce/`, `workforce/`, one new skill `aibl-workforce`, a stamp under `.aibl/programs/`). Then check for collisions: any path that is both in that list and in `git ls-files`. Expected: none. If there are some, run `git diff --quiet HEAD <remote>/student -- <those paths>`: no difference means the workbench already holds this same edition (it arrived another way, for example the installer's package route) and joining the branch is safe; say that and carry on. Any path that differs stops you: list it, and the student decides, with their program's channel if needed. Ask for a yes before merging.
4. **Merge.** Only after the yes:
   ```
   git merge --allow-unrelated-histories --no-edit -m "Add <program name>" <remote>/student
   ```
   It brings the program's files in as one merge commit on top of the student's own history. If `git status` was not clean before, ask them to save or set aside their unfinished work first (offer `aibl-checkpoint`); never stash or discard for them.
5. **Show what landed.** `git show --stat HEAD` summarised in plain words: the new folders, the new skill, and that `context/`, `work/` and `library/` did not change. Offer `aibl-checkpoint` so their private copy on GitHub has the program too.
6. **Point at the program's own start.** Say: start a new session in this folder (skills load when a session starts), then run the program's entry skill. For Workforce that is `aibl-workforce`.

## Rules

- Merge only from the program's `student` branch. Never `main`, never a tag someone pastes.
- Never merge without the yes in step 3, and never merge over a dirty working tree.
- Never delete or rewrite anything the student made. If a merge stops with conflicts, do not resolve them here: say what conflicted, run `git merge --abort`, and point them to `aibl-update`, which handles conflicts file by file.
- Never push to any remote except `origin`, and only through `aibl-checkpoint`.

## Attribution

Original AIBL method. MIT, like the rest of this template.
