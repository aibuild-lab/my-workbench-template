#!/bin/sh
set -eu
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
template_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if grep -F 'git checkout template/main -- .claude/skills/aibl-personalize' "$template_root/.claude/skills/aibl-update/SKILL.md"; then exit 1; fi
# decision 40: unsaved lesson work is offered a save (the update continues), and a partial merge is never recommended
for app in .claude .agents; do
  grep -qF 'Save it now and continue the update? (yes / no)' "$template_root/$app/skills/aibl-update/SKILL.md"
  grep -qF 'Never call a partial update recommended.' "$template_root/$app/skills/aibl-update/SKILL.md"
  if grep -qE 'skip the [0-9]+ \(Recommended\)' "$template_root/$app/skills/aibl-update/SKILL.md"; then exit 1; fi
done
template="$root/template"
workbench="$root/workbench"
mkdir -p "$template/.claude/skills/aibl-update" "$template/.claude/skills/aibl-enroll" "$workbench/.claude/skills/aibl-update" "$workbench/.claude/skills/aibl-enroll"
printf 'template update\n' > "$template/.claude/skills/aibl-update/SKILL.md"
printf 'template enroll\n' > "$template/.claude/skills/aibl-enroll/SKILL.md"
git -C "$template" init -q -b main
git -C "$template" add . && git -C "$template" -c user.name=test -c user.email=test@example.invalid commit -qm template
printf 'old update\n' > "$workbench/.claude/skills/aibl-update/SKILL.md"
printf 'my enrollment choice\n' > "$workbench/.claude/skills/aibl-enroll/SKILL.md"
git -C "$workbench" init -q -b main
git -C "$workbench" add . && git -C "$workbench" -c user.name=test -c user.email=test@example.invalid commit -qm workbench
git -C "$workbench" remote add template "$template"
git -C "$workbench" fetch -q template main
set +e
git -C "$workbench" diff --quiet HEAD template/main -- .claude/skills/aibl-enroll
status=$?
set -e
test "$status" -eq 1
git -C "$workbench" checkout -q template/main -- .claude/skills/aibl-update
test "$(cat "$workbench/.claude/skills/aibl-enroll/SKILL.md")" = 'my enrollment choice'
test "$(cat "$workbench/.claude/skills/aibl-update/SKILL.md")" = 'template update'
