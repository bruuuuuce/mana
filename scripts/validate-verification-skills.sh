#!/usr/bin/env bash
set -u
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
. "$root/scripts/lib/verification.sh"
status=0
command -v jq >/dev/null 2>&1 || { echo 'ERROR: jq is required to validate verification skills' >&2; exit 1; }

for skill_file in "$root"/skills/*/SKILL.md; do
  [ -f "$skill_file" ] || continue
  id="$(verification_frontmatter_field "$skill_file" name)"
  capability="$(verification_frontmatter_field "$skill_file" capability)"
  spec_name="$(verification_frontmatter_field "$skill_file" verification_spec)"
  if [ "$capability" = verification ]; then
    [ -n "$spec_name" ] || { echo "ERROR: $skill_file verification capability requires verification_spec" >&2; status=1; continue; }
    case "$spec_name" in */*|*..*|'') echo "ERROR: $skill_file verification_spec must be a sibling filename" >&2; status=1; continue;; esac
    spec="$(dirname "$skill_file")/$spec_name"
    [ -f "$spec" ] || { echo "ERROR: $skill_file missing verification spec: $spec_name" >&2; status=1; continue; }
    if ! verification_spec_validate "$spec" "$id"; then echo "ERROR: invalid verification spec for $id: $spec" >&2; status=1; fi
  elif [ -n "$spec_name" ]; then
    echo "ERROR: $skill_file declares verification_spec without capability: verification" >&2; status=1
  fi
done

for spec in "$root"/skills/*/verification.yaml; do
  [ -f "$spec" ] || continue
  skill_file="$(dirname "$spec")/SKILL.md"
  [ "$(verification_frontmatter_field "$skill_file" capability)" = verification ] || { echo "ERROR: orphan verification spec: $spec" >&2; status=1; }
done
[ "$status" -eq 0 ] && echo 'Verification skills validation passed'
exit "$status"
