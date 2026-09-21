---
name: aibl-update
description: Update your programs. Checks every program connected to this workbench for a newer edition, shows what would change, and merges it in after a yes. Your own files are never overwritten; a clash is settled one file at a time, your call.
---

# Update your programs

Each connected program is a remote of this workbench (added by `aibl-enroll`) whose `student` branch the course team moves forward when they publish. Updating is fetching that branch and merging it. The commit messages on the branch are the release notes.

## What to do

0. **Stop before writing over unfinished work.** Run `git status --short`. If it prints anything, ask the student to save with `aibl-checkpoint` and stop; never stash or discard it.
1. **Refresh the workbench's own skills after the student's choices.** The four `aibl-` skills come from the public template, and the template is not a program: it is never merged, only its skill folders are copied. From the workbench folder:
   ```
   git remote get-url template >/dev/null 2>&1 || git remote add template https://github.com/aibuild-lab/my-workbench-template.git
   git fetch template main
   ```
   For each skill folder, first run `git diff --quiet HEAD template/main -- <folder>`. If it differs, show `git diff HEAD template/main -- <folder>` and ask whether to keep the workbench version or take the template version. It may be an older template skill or a committed student edit, so never guess. Skip folders the student keeps; run the checkout only for folders they approve. The hook is the workbench's read-only update check. If `.claude/settings.json` is absent, copy the template's file too. If it already exists, leave it unchanged so its hooks and preferences are preserved; the student can still run this skill directly. If `git status --short` shows changes, say which approved skills were updated and commit them: `git commit -m "Update workbench skills from the template"`. Nothing else in the template is ever copied: not `README.md`, not `context/`, not the instruction files.
2. **Check, change nothing.** Run the workbench's own check, the same one that runs at the start of every new conversation:
   ```
   node .claude/hooks/update-check.mjs --json
   ```
   It fetches each connected program's `student` branch and the template, and reports `behind` per program and whether the skills changed. No programs listed means "no program is connected yet; `aibl-enroll` connects one." Stop there. `behind: 0` everywhere and no skill change means up to date; say so and stop. If a fetch failed for authentication, run `gh auth setup-git` once and run the check again. If `node` is missing, do the same by hand: `git remote` (anything other than `origin` and `template` is a program), then `git fetch <remote> student` and `git rev-list --count HEAD..<remote>/student`.
3. **Name what is behind.** One line per program that has editions waiting, and one line if the skills changed.
4. **Show what is new, then wait.** For a program that is behind:
   ```
   git log --format='%s' HEAD..<remote>/student
   git diff --stat HEAD...<remote>/student
   ```
   Read that out in plain words: how many editions behind, what the team said changed, which files are added, changed or removed. Point out any file the student has edited themselves that the update also changes (`git diff --name-only HEAD...<remote>/student` against `git log --format= --name-only <remote>/student..HEAD`). Ask for a yes before merging. If the working tree is not clean, ask them to save first (offer `aibl-checkpoint`); never stash or discard for them.
5. **Merge.** Only after the yes:
   ```
   git merge --no-edit <remote>/student
   ```
   Clean merge: go to step 7.
6. **A clash, one file at a time.** If git stops with conflicts, list them with `git diff --name-only --diff-filter=U`. For each file, show the student both versions in plain words (theirs is the program's new text, ours is what they wrote) and ask: keep mine, or take the program's? Then:
   ```
   git checkout --ours -- <file>      # keep mine
   git checkout --theirs -- <file>    # take the program's
   git add <file>
   ```
   When every file is settled, `git commit --no-edit`. Never pick for them, never merge the two texts yourself, and never `git merge --abort` unless they ask to stop; if they do, abort and say nothing changed.
7. **Show what landed and save.** `git show --stat HEAD` in plain words, then say that `context/`, `work/` and `library/` did not change (they never do; the program never contains them). Offer `aibl-checkpoint`. Then: start a new session in this folder so the app reloads any updated skills.

## Rules

- Merge only from `<remote>/student`. Never `main`, never a tag or commit someone pastes.
- Never merge without the yes, never over a dirty working tree, and never resolve a clash without the student choosing.
- Never push anywhere except `origin`, and only through `aibl-checkpoint`.
- Nothing here installs software, downloads anything outside git, or touches settings anywhere except the workbench's own `.claude/settings.json`, which carries only the update check.

## Attribution

Original AIBL method. MIT, like the rest of this template.
