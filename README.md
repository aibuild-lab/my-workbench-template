# My workbench

This is your workbench: one private folder where you and your agent do your work. Open it in the Claude app or the Codex app, tell the agent what you want to make, and it works here, with your notes and your files. It is yours. Nobody else can see the copy on GitHub.

## What is in it

- `CLAUDE.md` and `AGENTS.md`: the note your agent reads first, every time. Claude reads the first one, Codex reads the second. Same note.
- `context/`: what the agent knows about you. Your project, what it may touch, decisions you have made, where you left off. You write it and correct it; the agent reads it every session.
- `library/`: what you hand the agent to read. Transcripts, articles, documents.
- `blueprints/`: plans the agent can follow, one file each.
- `work/`: what the agent makes for you.
- `.claude/skills/` and `.agents/skills/`: your skills, the same set for both apps.
- `.aibl/`: housekeeping. Leave it alone.

## Four skills come with current workbenches

Type a forward slash in the Claude app, or a dollar sign in the Codex app, and you will see them.

- **aibl-personalize**: the interview. Three or four questions, then it writes `context/project.md` and shows you before it saves.
- **aibl-checkpoint**: save a snapshot of your work and send it to your private copy on GitHub, in one move. Also brings a file back.
- **aibl-enroll**: connect a program you have joined. It shows what will be added and waits for your yes. Before your program opens your access, it lists nothing, and that is expected.
- **aibl-update**: update your programs. It refreshes this workbench's own skills from the template, then checks each connected program for a newer edition, shows what would change, and merges it in after your yes. Your own files are never overwritten. A check also runs quietly at the start of every new conversation and says if an update is waiting.

Open any of them and read it. A skill is a folder with one file in it, `SKILL.md`. Read one before you run it, especially one you did not write.

## Ground rules

- Never paste a password, an API key, or a sign-in code into the chat. Sign-ins happen in your browser.
- Keep private things out of this folder, or in `.aibl-local/`, which never goes to GitHub.
- If something breaks, stop and take a screenshot. Ask the agent what it is before you click.

## When a program starts, and when it changes

Every AI Build Lab program you join lands inside this same folder. You never set up a second one. When your access opens, GitHub emails you an invitation to join `aibuild-lab` at the address on your GitHub account; accept it first (it is also waiting at https://github.com/settings/organizations). Then run `aibl-enroll`: it shows you what the program adds, you say yes, and it merges the program's files in next to yours. When the course team publishes a change, `aibl-update` shows you what changed and merges it in the same way. Your `context`, `library` and `work` folders are yours; a program never contains them.


## From Essentials to Workforce

Open your existing `my-workbench`. If its skills are older, use the official
[update prompt](https://github.com/aibuild-lab/aibl-installer/blob/main/START-HERE.md#later-update-your-workbench).
Run `aibl-enroll`, choose Workforce, review the changes, and approve them.
Workforce comes from `aibuild-lab/agent-workforce`, branch `student`.
Start a new session in this folder and run `aibl-workforce`.
If access fails, check the signed-in GitHub account with the team; Learn access
and repository access are separate. Keep existing Camp/OS folders separate.

Already installed a Workforce package? Enrollment compares its files with the
student branch and asks about differences before joining. Keep the old receipts;
future course updates use `aibl-update`, not package repair. It reports changes,
preserves settings and personal work, and asks before applying anything.

## Agent-menu reliability candidate, 2026-09-24

Enrollment and update can preview Claude agent-menu copies after course installation.
The student approves the exact changes; custom agents and copies owned by another
workbench are preserved, and replaced or retired managed entries have backups.
Session-start checks report only. A new session and an observed agent reply are
required after the student restarts the app. Codex discovery is checked separately.
