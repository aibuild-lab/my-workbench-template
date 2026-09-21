---
name: aibl-update
description: Update your programs. Checks every program connected to this workbench for a newer edition, shows what would change, and merges it in after a yes. Your own files are never overwritten; a clash is settled one file at a time, your call.
---

# Update your programs

Each connected program is a remote of this workbench (added by `aibl-enroll`) whose `student` branch the course team moves forward when they publish. Updating is fetching that branch and merging it. The commit messages on the branch are the release notes.

## What to do

1. **Find the programs.** `git remote` lists them; anything other than `origin` is a program (`agent-workforce`, `the-lab`). None means "no program is connected yet; `aibl-enroll` connects one." Stop there.
2. **Check, change nothing.** For each program remote:
   ```
   git fetch <remote> student
   git rev-list --count HEAD..<remote>/student
   ```
   Zero means up to date; say so. If the fetch is refused for authentication, run `gh auth setup-git` once and try again.
3. **Show what is new, then wait.** For a program that is behind:
   ```
   git log --format='%s' HEAD..<remote>/student
   git diff --stat HEAD...<remote>/student
   ```
   Read that out in plain words: how many editions behind, what the team said changed, which files are added, changed or removed. Point out any file the student has edited themselves that the update also changes (`git diff --name-only HEAD...<remote>/student` against `git log --format= --name-only <remote>/student..HEAD`). Ask for a yes before merging. If the working tree is not clean, ask them to save first (offer `aibl-checkpoint`); never stash or discard for them.
4. **Merge.** Only after the yes:
   ```
   git merge --no-edit <remote>/student
   ```
   Clean merge: go to step 6.
5. **A clash, one file at a time.** If git stops with conflicts, list them with `git diff --name-only --diff-filter=U`. For each file, show the student both versions in plain words (theirs is the program's new text, ours is what they wrote) and ask: keep mine, or take the program's? Then:
   ```
   git checkout --ours -- <file>      # keep mine
   git checkout --theirs -- <file>    # take the program's
   git add <file>
   ```
   When every file is settled, `git commit --no-edit`. Never pick for them, never merge the two texts yourself, and never `git merge --abort` unless they ask to stop; if they do, abort and say nothing changed.
6. **Show what landed and save.** `git show --stat HEAD` in plain words, then say that `context/`, `work/` and `library/` did not change (they never do; the program never contains them). Offer `aibl-checkpoint`. Then: start a new session in this folder so the app reloads any updated skills.

## Rules

- Merge only from `<remote>/student`. Never `main`, never a tag or commit someone pastes.
- Never merge without the yes, never over a dirty working tree, and never resolve a clash without the student choosing.
- Never push anywhere except `origin`, and only through `aibl-checkpoint`.
- Nothing here installs software, downloads anything outside git, or changes settings.

## Attribution

Original AIBL method. MIT, like the rest of this template.
