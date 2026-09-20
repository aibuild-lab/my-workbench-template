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

## Three skills came with it

Type a forward slash in the Claude app, or a dollar sign in the Codex app, and you will see them.

- **aibl-personalize**: the interview. Three or four questions, then it writes `context/project.md` and shows you before it saves.
- **aibl-checkpoint**: save a snapshot of your work and send it to your private copy on GitHub, in one move. Also brings a file back.
- **aibl-enroll**: to check program access and preview supported additions. Access follows your cohort schedule.

Open any of them and read it. A skill is a folder with one file in it, `SKILL.md`. Read one before you run it, especially one you did not write.

## Ground rules

- Never paste a password, an API key, or a sign-in code into the chat. Sign-ins happen in your browser.
- Keep private things out of this folder, or in `.aibl-local/`, which never goes to GitHub.
- If something breaks, stop and take a screenshot. Ask the agent what it is before you click.

## When a program starts

Every AI Build Lab program you join lands inside this same folder. You never set up a second one. When your course access opens, run `aibl-enroll`. It checks your account, previews supported additions and preserves the work you already made.
