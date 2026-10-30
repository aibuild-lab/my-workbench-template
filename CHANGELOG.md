# Changelog

## 2026-10-30

- `aibl-enroll` step 1 now says the right thing to students joining from another program. A new read-only report, `node .claude/hooks/update-check.mjs --joining-from`, looks for two groups and changes nothing. Agent Team HQ graduates (the program's stamp, `team-hq/`, `work/team-hq/` or its remote, plus the night shift `aibl-hq-night-shift` in `.aibl-local/schedule/`) hear to save first, because the night shift rewrites Team HQ files every morning, and that the six shared agents come as one choice with the Workforce copies recommended; step 7 confirms `work/team-hq/` and the night shift were untouched. Agent Native Camp alumni (`~/GitHub/agent-native-camp` with Camp's descriptor) hear that Camp is never touched and the program goes beside it; a weak sign (`~/context-repo`, `~/.hermes`) gets one plain question instead of a guess, and nothing found says nothing. A Camp folder opened by mistake stops with its own words. Everyone else sees no change. New `tests/joining_from.py` (throwaway home folders only).
- `aibl-update` step 7: on an Agent Workforce workbench whose edition ships Start fresh, the course's own read-only check decides whether to offer run two to a returning student; the offer hands over the course's Start fresh step and never runs it in the update.

## 2026-10-29

- `aibl-enroll` step 4: Agent Team HQ now ships six agents under Agent Workforce's names (adds `aibl-riff`), so a workbench taking both programs can see up to thirteen differing files (six agents in each app plus `.aibl/course-agents.json`), not eleven. Checked against both student branches. The Team HQ test fixture follows; the checks pinned to the first published edition (e8e36a38, five agents) keep five.

## 2026-10-15

- Reuse the existing accountable-owner slug in discovery metadata.


## 2026-10-15

- Upgrade repository discovery metadata to descriptor v2; retain existing ownership, privacy, lifecycle, and execution boundaries.

