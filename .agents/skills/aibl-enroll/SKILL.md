---
name: aibl-enroll
description: Add an accessible program to your existing workbench after showing the exact changes and receiving your approval.
---

# Connect your program

Workforce joins the Essentials `my-workbench` you already own. No second workbench. Updates later use `aibl-update`. Keep Camp and Agent Native OS projects separate.

## Current destinations

| Program | Remote | Repository | Branch |
|---|---|---|---|
| Agent Workforce | agent-workforce | https://github.com/aibuild-lab/agent-workforce.git | student |
| The Lab | the-lab | https://github.com/aibuild-lab/the-lab.git | student |

If the retained installer's `course-options.json` has an `enrollment` object for the selected program, check its `repository` and `branch` against this table. A disagreement stops for course-team review. If that object is absent, use this table. The old `publisher`, `release_product`, and `adopt_skill` fields describe historical package delivery, not this Git route. Never rewrite a retained installer or package receipt.

## Steps

1. **Check the folder and unfinished work before changing anything.** Run `git rev-parse --show-toplevel`, `git remote get-url origin`, and `gh api user --jq .login`. Confirm this is the student's workbench, with a private GitHub origin owned by that account (`gh repo view <owner/repo> --json nameWithOwner,isPrivate`). Accept the normal HTTPS or SSH spelling of that exact repository. A wrong folder, unknown ownership, public origin, symlinked workbench, or missing setup stops here. Run `git status --porcelain --untracked-files=all`; any output stops for the student to checkpoint. Never stash, discard, or rerun setup. Missing skills on an older workbench use the official installer `UPDATE-PROMPT.md`, not a new installation.
2. **Check access.** Run `gh api repos/<owner/repo> --jq .full_name` for the selected program. A 404 establishes unavailable repository access, not why or when it opens. Authentication and network errors remain separate failures. Give the student their signed-in GitHub username and the program name to use when asking the team; check Learn separately. Never grant access or send a message for them.
3. **Connect or reuse the exact remote.** Inspect an existing remote's URL; accept only the HTTPS or SSH URL of the listed repository. Stop on mismatch, never replace it. Otherwise add the listed remote, then `git fetch <remote> student`. Retry once with `gh auth setup-git` only for an authentication failure. A missing branch or failed fetch stops; never use a stale fetched ref. Retain a newly added remote for a safe retry. A remote alone does not mean enrollment succeeded. If `git merge-base --is-ancestor <remote>/student HEAD` succeeds, the published edition is already present: do not merge again; proceed to step 7. If there is a common ancestor but newer program commits, follow `aibl-update`.
4. **Inspect the exact incoming tree.** Run `git ls-tree -r <remote>/student`. Workforce may supply only `course/workforce/`, `workforce/`, `.claude/agents/`, `.codex/agents/`, `.claude/skills/`, `.agents/skills/`, and `.aibl/programs/agent-workforce.json`. Reject symlinks/submodules, root instructions/settings, personal folders, the four template-owned core skill folders, or paths outside that list. Existing symlinked destination ancestors also stop. Check ignored local files as well as tracked files for collisions; never overwrite them. For another program, require its reviewed file boundary before merging.
5. **Preview and approve.** List the additions and all tracked overlapping paths; compare overlapping blobs with `git diff HEAD <remote>/student -- <paths>`. Identical overlaps are expected after a package installation. For different files show both versions and ask keep mine, take the program's, or combine specified changes. Explain that taking the program's discards edits in that file; keeping mine omits its incoming fixes. For Chief's personalized name recommend the program's improvements plus the student's original display-name line, only after approval. Preserve role IDs and TOML syntax. Do not silently rewrite any other customization. Record the choices in the conversation, then obtain approval for the whole preview. Pin the reviewed branch's commit with `git rev-parse <remote>/student`; ref movement or changed local state requires a new preview.
6. **Merge the reviewed edition.** Recheck cleanliness and the reviewed ref, then `git merge --allow-unrelated-histories --no-ff --no-commit <remote>/student`. Resolve only approved collisions using `git checkout --ours -- <file>` or `git checkout --theirs -- <file>`, or the specifically approved combination, then `git add -- <file>`. A surprise collision stops for a decision. Show `git diff --cached` and commit the approved result with `git commit -m "Add Agent Workforce"` (use the selected program's name). If the student cancels while the merge is unfinished, `git merge --abort` restores the clean pre-merge state. Retain historical `.aibl` package records unchanged: they describe the old installation, not the now-updated Git files. Do not run package repair/update after Git adoption.
7. **Verify and start.** Inspect the commit and verify personal files, settings, and root instructions were unchanged. Report the installed student-branch commit and any deliberately retained customizations. Do not claim installation means a worker ran. Ask the student to start a new session in the same folder, then run `aibl-workforce` (slash skill in Claude, dollar-sign skill in Codex). Check actual named-agent discovery and a real response using the installed program's supported instructions. Missing discovery stops for diagnosis; never copy/link agents into global folders. Offer `aibl-checkpoint` for the student's private origin, separately from enrollment.

Never merge `main`, change permissions, send work, manufacture setup records, or push to a program remote. Student approval covers only the exact preview.

## Attribution

Original AIBL method. MIT, like the rest of this template.
