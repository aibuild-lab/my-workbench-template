---
name: aibl-update
description: Update your programs. Checks every program connected to this workbench for a newer edition, shows what would change, and merges it in after a yes. Your own files are never overwritten; a clash is settled one file at a time, your call.
---

# Update your programs

Each connected program is a remote of this workbench (added by `aibl-enroll`) whose `student` branch the course team moves forward when they publish. Updating is fetching that branch and merging it. The commit messages on the branch are the release notes.

## What to do

0. **Refresh the workbench's own skills first.** The four `aibl-` skills come from the public template, and the template is not a program: it is never merged, only its skill folders are copied. From the workbench folder:
   ```
   git remote add template https://github.com/aibuild-lab/my-workbench-template.git   # once; skip if it exists
   git fetch template main
   git checkout template/main -- .claude/skills/aibl-personalize .claude/skills/aibl-checkpoint .claude/skills/aibl-enroll .claude/skills/aibl-update .agents/skills/aibl-personalize .agents/skills/aibl-checkpoint .agents/skills/aibl-enroll .agents/skills/aibl-update
   ```
   If `git status --short` shows changes, say which skills were updated and commit them: `git commit -m "Update workbench skills from the template"`. If the student had edited one of those four skills, say so before the checkout and let them choose to keep theirs (skip that folder). Nothing else in the template is ever copied: not `README.md`, not `context/`, not the instruction files.
1. **Find the programs.** `git remote` lists them; anything other than `origin` and `template` is a program (`agent-workforce`, `the-lab`). None means "no program is connected yet; `aibl-enroll` connects one." Stop there.
2. **Check, change nothing.** For each program remote:
   ```
   git fetch <remote> student
   git rev-list --count HEAD..<remote>/student
   ```
   Zero means up to date; say so. If the fetch is refused for authentication, run `gh auth setup-git` once and try again.
2.5. **What changed, by component.** A program keeps a list of its parts in `workforce/VERSIONS.json`: one entry per agent, skill, lesson and house file, each with an id, a kind, a version and a fingerprint (`closure_sha256`). Read the incoming list and the one the student holds now:
   ```
   git show <remote>/student:workforce/VERSIONS.json
   git show HEAD:workforce/VERSIONS.json
   ```
   If the second command fails because the file is not there, this is their first update on the versioned program: say so, and read the incoming list out as all new. Otherwise match the two lists by id and read the difference out in plain words, grouped: agents that moved ("Kansa 0.3 to 0.4"), skills that moved, lessons that moved, new components, removed components. A component whose version did not change is not mentioned.

   Then the student's own edits to program-owned files:
   ```
   git diff --name-only $(git merge-base HEAD <remote>/student) HEAD -- .claude/agents .codex/agents .claude/skills .agents/skills workforce course
   ```
   That list also catches files the program does not own, such as the workbench's four `aibl-` skills, which were here before enrolling and are never in the program. So keep only the paths that are also in `git ls-tree -r --name-only <remote>/student`; drop the rest without mention. Explain what is left as "you changed these files yourself since the last update" and list them. For each such file that the update also changes (it is also in `git diff --name-only HEAD...<remote>/student`), say it will be a clash to settle in step 5. For one the update does not touch, say it stays as is. Then one recommendation line: take everything you have not edited; for the rest, keep or take, per file.

   Say this explicitly: the name line of their Chief of Staff (the `# <name>, your Chief of Staff` heading in `.claude/agents/aibl-chief-of-staff.md`, right under the front matter) is theirs, and git keeps it through the merge unless the update changed that same line. If it did, the file clashes in step 5, which has a path that keeps both their name and the program's changes.
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
   Say plainly what each choice costs: keep mine means none of the program's changes to this file arrive; take the program's means your edits to this file are gone; if you want both, take the program's and re-make your edit afterward.

   One file gets its own path: `.claude/agents/aibl-chief-of-staff.md`. The student's name sits on one line, and the update usually changes other lines in the same file, so keep mine would throw away those improvements and take the program's would lose the name. Recommend the way that keeps both: take the program's version (`git checkout --theirs -- .claude/agents/aibl-chief-of-staff.md`), put the student's name back on the `# <name>, your Chief of Staff` heading right under the front matter, and only then `git add` it. Say so in the checkpoint message.

   When every file is settled, `git commit --no-edit`. Never pick for them, never merge the two texts yourself beyond that one name line, and never `git merge --abort` unless they ask to stop; if they do, abort and say nothing changed.
6. **Show what landed and save.** `git show --stat HEAD` in plain words, then say that `context/`, `work/` and `library/` did not change (they never do; the program never contains them). Offer `aibl-checkpoint`. Then: start a new session in this folder so the app reloads any updated skills.

6.5. **Make the update live.** After a clean merge, or once every clash is settled and committed, the files are right but the apps do not know it yet. Three moves, then a proof.
   - Rebuild the registry, the program's list of who is on the team, with today's date as YYYY-MM-DD:
     ```
     python3 workforce/shed/generate-registry.py --root . --date <today's date>
     ```
     If `git status --short` shows `workforce/shed/registry.yaml` changed, it goes in the checkpoint at the end of this step.
   - Refresh the global agent links, so the `@` dropdown in the desktop app lists any new agent. On Mac and Linux, for each `.claude/agents/aibl-*.md`, link it into `~/.claude/agents/` under the same file name:
     ```
     mkdir -p ~/.claude/agents
     for f in .claude/agents/aibl-*.md; do ln -sf "$PWD/$f" ~/.claude/agents/"$(basename "$f")"; done
     ```
     On Windows, copy each file into `%USERPROFILE%\.claude\agents\` instead, and say that a copy goes stale until the next update copies it again; a link never does.
   - Prove one agent answers. Start a new thread in this folder, type `@`, pick `aibl-chief-of-staff`, send "Who are you?" and read the reply back to the student. A file that parses is not proof; a reply is. If the dropdown does not list the agent, redo the links. If it is listed but does not answer, say so and stop; do not go on as if it worked.
   - Report the versions now held: read `workforce/VERSIONS.json` and list each component with its version, in the same groups as step 2.5. Offer `aibl-checkpoint` if anything changed in this step.

## Rules

- Merge only from `<remote>/student`. Never `main`, never a tag or commit someone pastes.
- Never merge without the yes, never over a dirty working tree, and never resolve a clash without the student choosing.
- Never push anywhere except `origin`, and only through `aibl-checkpoint`.
- Nothing here installs software, downloads anything outside git, or changes settings.
- Never edit `VERSIONS.json` by hand; it is written by the program's publish step.
- The name line of your Chief of Staff is yours; if an update ever overwrites it, put it back and say so in the checkpoint message.

## Attribution

Original AIBL method. MIT, like the rest of this template.
