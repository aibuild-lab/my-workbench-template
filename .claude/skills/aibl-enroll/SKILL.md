---
name: aibl-enroll
description: Connect an accessible program to this workbench through a verified, student-confirmed enrollment preview.
---

# Connect Workforce

Use this skill only when the student chooses to connect a program. Keep their
existing workbench, context, work and selected client (Claude or Codex).

1. Read the official [Workforce handoff](https://github.com/aibuild-lab/aibl-installer/blob/main/WORKFORCE-HANDOFF.md).
   Reading that page does not authorize executing code from a moving branch.
   The course team must supply an independently admitted distribution file,
   its independent SHA-256, and the matching clean retained installer revision.
   If these are unavailable, say that verified delivery is not available yet.
   Never infer an invitation or access date, pull a newer installer, or copy
   replacement skills by hand.
2. From that exact installer, use its `scripts/enroll.py --workbench ABSOLUTE_PATH
   --check --json` to inspect access without changing the workbench. Report the
   actual result. Missing access needs the signed-in account and course-team
   check, not a guess about when the course starts.
3. For an Essentials workbench without a family record, use the verified
   installer to preview `--program agent-workforce --preview --harness claude`
   (or `codex`) with `--distribution FILE --distribution-sha256 SHA256`, the
   actual `--workbench`, and `--json`. For an already connected family workbench,
   use its installed adjacent enrollment helper and retained association instead.
4. Explain the exact preview, including any replacement of all three supplied
   core skills. Preserve edited skills and conflicts for review. Ask the student
   to confirm these changes. Selection or `--yes` is never installation approval.
5. Apply only the returned plan ID using the same exact installer and workbench:
   `scripts/enroll.py --workbench ABSOLUTE_PATH --apply-plan PLAN_ID --json`.
   Changed inputs require a new preview and confirmation. Follow the returned
   recovery instructions after interruption; do not delete records or start over.
6. After verified installation, refresh the selected app and use the supplied
   `aibl-workforce` skill and returned first action. File installation is not proof
   that a worker ran or that the student completed any course activity.

Never create another workbench, switch clients, grant access, send work, commit,
or push as part of enrollment. Browser sign-in and student decisions stay with
the student.
