---
name: aibl-checkpoint
description: Save a snapshot of chosen files in this folder and send it to the private copy on GitHub, in one move. Also brings one file back from an earlier snapshot. Run it when they say "save", "checkpoint", "back this up", or "get my file back".
---

# Checkpoint

A checkpoint is a named snapshot of chosen files, kept in two places: this computer and the private copy on GitHub. Saving a file is not a checkpoint. A checkpoint is the thing you can go back to.

## In Codex: one permission for each protected write

In Codex, an agent can't change this folder's history (`.git`), anything outside this folder, or use the network, unless the owner allows that step. Claude Code has no such step: there, run the steps as written. In Codex, every write in the table below follows these five rules, and each part that makes one says so with "(Codex: one permission per write.)":

- **One plain line first.** Before the command, say in one plain line what is about to change, then the course's Week 1 words for the box: "If Codex asks you to allow a save to your workbench's history, that's this save; choose to allow it." for a save, and "If Codex asks you to allow it, that's this step; choose to allow it." for any other write. Use the part's line from the table, with the label and the files in plain words. Never show the command, a file path or a word in capitals in that line.
- **Its own command, with the permission asked together with it.** Run each write as one command on its own, never joined to another with `&&`, `;` or `|`, and never inside a script you write to run several. Request the app's permission together with that exact command when you run it: ask to run it outside the sandbox, with a one-line reason that names the same step as your plain line, so the box the owner sees names the step you just named. Never try it first and ask only after it fails: Codex does not offer the permission on its own. If a write you ran without asking fails with a read-only or permission message (such as "Unable to create .git/index.lock: Permission denied"), that is not the owner's no: run the same command once more, alone, with the permission asked.
- **One line and one box per write.** When every file in the save is already tracked, save with one command, `git commit -m "<label>" -- <files>`, so there is one box, not two; a new file needs `git add -- <file>` first, its own command. Read-only commands (`git status`, `git diff`, `git ls-files`, `git log`, `git show`) need no line and no permission.
- **Never a terminal step for the owner.** You run every command. Never hand the owner a command, a box with a command in it, or a step in a terminal or PowerShell, even when a permission is refused.
- **If it isn't allowed, wait.** If the owner doesn't allow it, or no box comes (for example the session's approval policy is never, so no permission can be asked), stop at that step. When you stop there, that reply is exactly two lines: the step's plain line, then its waiting line, word for word from the table, even when you knew before running it that no box could come. Nothing before them and nothing after: no note that a permission is needed or can't be asked, no quote of this skill, no file link, no word about the app's settings or policies. Then do nothing else: no other command, no other way to make the same change, no choices of your own, and never say or suggest the step happened ("Saved in two places" only after both the save and the push worked). On "try again", recheck that the files are as they were, say the plain line again, and run the same command with the permission asked.

| Part | The write (each its own command) | The plain line before it | The waiting line if it isn't allowed |
|---|---|---|---|
| Save 4 | `git add -- <file>`, only for a file Git doesn't track yet | "Next I add <the new file, in plain words> to this save. If Codex asks you to allow a save to your workbench's history, that's this save; choose to allow it." | "Nothing is saved yet; your files are as they were, nothing is lost. Say "try again" when you're ready." |
| Save 4 | `git commit -m "<label>" -- <files>` | "Next I save <the files, in plain words> on this computer as "<label>". If Codex asks you to allow a save to your workbench's history, that's this save; choose to allow it." | "Nothing is saved yet; your files are as they were, nothing is lost. Say "try again" when you're ready." |
| Save 4 | `git push origin <branch>` (it also uses the network) | "Next I send this save to your private copy on GitHub. If Codex asks you to allow it, that's this step; choose to allow it." | "Your save is on this computer, not on GitHub yet; nothing is lost. Say "try again" when you're ready." |
| Save 5 | `git pull` when GitHub has moved (it also uses the network) | "Next I bring in what changed on GitHub first. If Codex asks you to allow it, that's this step; choose to allow it." | "Your save is on this computer, not on GitHub yet; nothing is lost. Say "try again" when you're ready." |
| Save | `git config user.name <login>`, then `git config user.email <noreply address>`, for this folder only | "Next I put your GitHub name on saves in this folder. If Codex asks you to allow it, that's this step; choose to allow it." | "Nothing is saved yet; your files are as they were, nothing is lost. Say "try again" when you're ready." |
| Bring back 3 | `git checkout <commit> -- <file>` | "Next I bring back <the file, in plain words> from "<label>". If Codex asks you to allow it, that's this step; choose to allow it." | "<The file> hasn't come back yet; nothing else changed. Say "try again" when you're ready." |

The waiting lines are true because each command changes nothing when it is refused: a refused commit leaves the files as they were, and a refused push leaves the save on this computer, so "try again" runs only the push.

## Save

1. Look. Run `git status --short` and `git diff`. Tell them what changed in plain words, one line per file. Name files, not hashes. Example: "Your note in context/project.md got three new lines. Nothing else changed."
2. Leave out anything private: `.env` files, anything under `.aibl-local/`, a `course-progress-import*.json` download, `runs/`, `quarantine/`, `logs/` or `library/originals/`, log files, the voice samples and voice package (`work/course/staff/voice*`), account records (`*-accounts.yaml`), the agents' local notes (`.claude/agent-memory-local/`), settings files, and client material they did not ask to include. Before staging or pushing, run `git ls-files -- runs/ quarantine/ logs/ "*.log" library/originals/ "work/course/staff/voice*" "*-accounts.yaml" .claude/agent-memory-local/ .aibl-local/ .env ".env.*" .claude/settings.local.json`. Example key files (`.env.example`, `.env.sample`, `.env.template`) may show up in that list and are fine to keep. If it lists any other path, stop the checkpoint: these local-only records are already tracked, and ignore rules do not remove them from Git. Name the paths without printing their contents. Ask the owner to review how to stop tracking them while retaining the local files; do not delete files, untrack them or rewrite remote history on their behalf. An earlier remote copy remains even after untracking. If the command lists nothing, or only example key files, continue. Never force-add these local-only paths. Say what you left out and why.
3. Propose a label in their words, under ten words. Example: "Interview answers, first pass." Let them change it.
4. Stage the named files only (never `git add -A` or `git add .`), commit with the label, then push to `origin` on the current branch. Then say: "Saved in two places: on this computer, and at github.com/<user>/my-workbench." (Codex: one permission per write. The commit and the push are two writes, each its own command after its own plain line; a new file's `git add` is one more.)
5. If the push is refused because the copy on GitHub has moved: stop, explain in one sentence, pull, then push again. Never force-push. (Codex: one permission per write. The pull and the second push are each their own command.)

If Git asks who they are (no local name or email), set `user.name` and `user.email` for this folder only, using their GitHub login and its noreply address. Never change global settings. (Codex: one permission per write. Each `git config` is its own command.)

## Bring a file back

When they say a file is gone or wrong:

1. Run `git log --oneline -- <file>` to find the snapshots that have it. Show the labels. Let them pick.
2. Show the old version first (`git show <commit>:<file>`), so they see what is coming back before it moves.
3. Restore only that file: `git checkout <commit> -- <file>`. Nothing else moves. (Codex: one permission per write.)
4. Say what came back and from which label. Then offer a new checkpoint, so the restore is itself saved.

Never run `git reset --hard`. Never rewrite history that has been pushed.

## What to say when it is done

The label, the files in it, and the two places it now lives. One line each.

## Attribution

Adapted from the AIBL checkpoint method (Sara Davison, Tyler Fisk, Hunter Canning). MIT, like the rest of this template.
