# Changelog

## 2026-10-30

- `aibl-update` step 6: a conflict in `workforce/shed/registry.yaml` takes the program's copy without asking, because the file is generated and step 6.5 rebuilds it from the seat profiles and the student's own connector record. Found in the 10-30 returning-students test merge (a pretend Cohort 1 workbench taking Agent Workforce v2): the registry was the only conflict, and the step gave no recommendation. It works in the same update run, because step 2 refreshes `aibl-update` first.

## 2026-10-29

- `aibl-enroll` step 4: Agent Team HQ now ships six agents under Agent Workforce's names (adds `aibl-riff`), so a workbench taking both programs can see up to thirteen differing files (six agents in each app plus `.aibl/course-agents.json`), not eleven. Checked against both student branches. The Team HQ test fixture follows; the checks pinned to the first published edition (e8e36a38, five agents) keep five.

## 2026-10-15

- Reuse the existing accountable-owner slug in discovery metadata.


## 2026-10-15

- Upgrade repository discovery metadata to descriptor v2; retain existing ownership, privacy, lifecycle, and execution boundaries.

