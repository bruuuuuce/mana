#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

"$root/scripts/mana-workspace.sh" init --root "$tmp" --feature KNOW-1 --purpose knowledge-test --no-activate >/dev/null

knowledge_root="$tmp/.mana/global/knowledge"
[ -d "$knowledge_root/cards" ]
[ -d "$knowledge_root/candidates" ]
[ -f "$knowledge_root/index.md" ]
grep -q 'Service Knowledge Index' "$knowledge_root/index.md"

printf '%s\n' '# Project Knowledge Index' > "$knowledge_root/index.md"
"$root/scripts/mana-workspace.sh" init --root "$tmp" --feature KNOW-1 --purpose knowledge-test --no-activate >/dev/null
grep -q 'Project Knowledge Index' "$knowledge_root/index.md"

echo "Service knowledge bootstrap passed"
