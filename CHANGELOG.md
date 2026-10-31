# Changelog

## 2026-10-30

- Camp detection in `--joining-from` now matches what the Agent Native OS workshop installer and Camp leave on a camper's computer. A verified sign is any one of: Camp's clone holding its descriptor; Camp's clone whose own `.git/config` names `aibuild-lab/agent-native-camp` or a private `agent-native-camp-private` mirror (a clone last updated before the descriptor reached Camp on 09-02 has only this); or `~/context-repo` holding Camp's `.camp-context-repo` marker. The clone is looked for at `~/GitHub` first, then at a few fixed places (`~`, Documents, Documents/GitHub, Desktop, and Windows' OneDrive Documents and Desktop). Reasons to ask: a Camp-named folder without either mark, `~/context-repo` without the marker, or `~/Documents/Agent-Native-Camp`. `~/.hermes` is no longer a sign: the Agent Native OS workshop teaches a local Hermes there too, so workshop alumni who never took Camp were asked. Still read only: fixed paths, three small files in Camp folders, no Git command in a Camp folder. `~/context-repo` opened by mistake stops like the Camp folder. The Camp question is now asked at most once, ever: the report gives `camp.next` (`say`, `ask` or `none`), and `--camp-record yes|no` writes `~/.aibl/camp.json` (schema `aibl.camp-answer/v1`, the same record the installer writes after its Camp line), after which neither surface asks or says it again. A strong sign never asks. Tests: old-installer layouts for Mac and Windows, and the once-only record, in `tests/joining_from.py`.
- `aibl-enroll` step 1 now says the right thing to students joining from another program. A new read-only report, `node .claude/hooks/update-check.mjs --joining-from`, looks for two groups and changes nothing. Agent Team HQ graduates (the program's stamp, `team-hq/`, `work/team-hq/` or its remote, plus the night shift `aibl-hq-night-shift` in `.aibl-local/schedule/`) hear to save first, because the night shift rewrites Team HQ files every morning, and that the six shared agents come as one choice with the Workforce copies recommended; step 7 confirms `work/team-hq/` and the night shift were untouched. Agent Native Camp alumni (`~/GitHub/agent-native-camp` with Camp's descriptor) hear that Camp is never touched and the program goes beside it; a weak sign (`~/context-repo`) gets one plain question instead of a guess, and nothing found says nothing. A Camp folder opened by mistake stops with its own words. Everyone else sees no change. New `tests/joining_from.py` (throwaway home folders only).
- `aibl-update` step 6.1: on an Agent Workforce workbench whose edition ships Start fresh, the course's own read-only check decides whether to offer run two to a returning student; the offer hands over the course's Start fresh step and never runs it in the update.
- `aibl-update` step 6: a conflict in `workforce/shed/registry.yaml` takes the program's copy without asking, because the file is generated and step 6.5 rebuilds it from the seat profiles and the student's own connector record. Found in the 10-30 returning-students test merge (a pretend Cohort 1 workbench taking Agent Workforce v2): the registry was the only conflict, and the step gave no recommendation. It works in the same update run, because step 2 refreshes `aibl-update` first.

## 2026-10-29

- `aibl-enroll` step 4: Agent Team HQ now ships six agents under Agent Workforce's names (adds `aibl-riff`), so a workbench taking both programs can see up to thirteen differing files (six agents in each app plus `.aibl/course-agents.json`), not eleven. Checked against both student branches. The Team HQ test fixture follows; the checks pinned to the first published edition (e8e36a38, five agents) keep five.

## 2026-10-15

- Reuse the existing accountable-owner slug in discovery metadata.


## 2026-10-15

- Upgrade repository discovery metadata to descriptor v2; retain existing ownership, privacy, lifecycle, and execution boundaries.

