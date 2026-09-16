---
name: aibl-checkpoint
description: Save a snapshot of chosen files in this folder and send it to the private copy on GitHub, in one move. Also brings one file back from an earlier snapshot. Run it when they say "save", "checkpoint", "back this up", or "get my file back".
---

# Checkpoint

A checkpoint is a named snapshot of chosen files, kept in two places: this computer and the private copy on GitHub. Saving a file is not a checkpoint. A checkpoint is the thing you can go back to.

## Save

1. Look. Run `git status --short` and `git diff`. Tell them what changed in plain words, one line per file. Name files, not hashes. Example: "Your note in context/project.md got three new lines. Nothing else changed."
2. Leave out anything private: `.env` files, anything under `.aibl-local/`, settings files, and client material they did not ask to include. Say what you left out and why.
3. Propose a label in their words, under ten words. Example: "Interview answers, first pass." Let them change it.
4. Stage the named files only (never `git add -A` or `git add .`), commit with the label, then push to `origin` on the current branch. Then say: "Saved in two places: on this computer, and at github.com/<user>/my-workbench."
5. If the push is refused because the copy on GitHub has moved: stop, explain in one sentence, pull, then push again. Never force-push.

If Git asks who they are (no local name or email), set `user.name` and `user.email` for this folder only, using their GitHub login and its noreply address. Never change global settings.

## Bring a file back

When they say a file is gone or wrong:

1. Run `git log --oneline -- <file>` to find the snapshots that have it. Show the labels. Let them pick.
2. Show the old version first (`git show <commit>:<file>`), so they see what is coming back before it moves.
3. Restore only that file: `git checkout <commit> -- <file>`. Nothing else moves.
4. Say what came back and from which label. Then offer a new checkpoint, so the restore is itself saved.

Never run `git reset --hard`. Never rewrite history that has been pushed.

## What to say when it is done

The label, the files in it, and the two places it now lives. One line each.

## Attribution

Adapted from the AIBL checkpoint method (Sara Davison, Tyler Fisk, Hunter Canning). MIT, like the rest of this template.
