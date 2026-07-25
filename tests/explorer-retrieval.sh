#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-explorer.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
project="$tmp/project"; mkdir -p "$project/src" "$project/.mana/global"
printf 'Kafka contract producer order source\n' > "$project/src/order-contract.yaml"
printf 'integration contract\n' > "$project/.mana/global/integration-map.md"
printf 'architecture\n' > "$project/.mana/global/architecture.md"
printf 'guards\n' > "$project/.mana/global/engineering-guards.md"
. "$root/scripts/lib/explorer-retrieval.sh"
explorer_retrieve "$project" 'Find the order source' || fail 'single-cycle retrieval failed'
[ "$EXPLORER_STATUS" = sufficient ] || fail 'single-cycle sufficiency missing'
[ "$(printf '%s\n' "$EXPLORER_CYCLES" | awk 'END {print NR}')" = 1 ] || fail 'single-cycle completion was not preserved'
explorer_retrieve "$project" 'Find the Kafka contract' || fail 'one/two-cycle retrieval failed'
[ "$EXPLORER_STATUS" = sufficient ] || fail 'expected sufficient evidence'
[ "$(printf '%s\n' "$EXPLORER_CYCLES" | awk 'END {print NR}')" = 3 ] || fail 'maximum-cycle stop was not enforced'
printf '%s\n' "$EXPLORER_EVIDENCE" | grep -Fq 'repository-local' || fail 'provenance missing'
printf '%s\n' "$EXPLORER_REJECTED" | grep -Fq 'already retrieved' || fail 'repeated evidence was not suppressed'
MANA_EXPLORER_TOOL_BLOCKED=true explorer_retrieve "$project" 'Find contract' || fail 'blocked retrieval failed'
[ "$EXPLORER_STATUS" = blocked ] || fail 'tool boundary did not block'
MANA_EXPLORER_HUMAN_INPUT_REQUIRED=true explorer_retrieve "$project" 'Find contract' || fail 'human input retrieval failed'
[ "$EXPLORER_STATUS" = human-input-required ] || fail 'human input status missing'
rm "$project/.mana/global/integration-map.md"
explorer_retrieve "$project" 'Find the integration contract' || fail 'missing contract retrieval failed'
[ "$EXPLORER_STATUS" = partial ] || fail 'missing integration contract not reported'
printf '%s\n' "$EXPLORER_GAPS" | grep -Fq 'missing integration contract' || fail 'contract gap missing'
explorer_retrieve "$project" 'zzzznonexistent' || true
[ "$EXPLORER_STATUS" = insufficient-evidence ] || fail 'insufficient evidence status missing'
grep -Fq 'Do not recursively delegate to another explorer.' "$root/.codex/agents/mana-explorer.toml" || fail 'recursive delegation guard missing'
one="$($root/scripts/mana-explore.sh --project-root "$project" 'zzzznonexistent' --json)"; two="$($root/scripts/mana-explore.sh --project-root "$project" 'zzzznonexistent' --json)"; [ "$one" = "$two" ] || fail 'explorer JSON is not stable'
echo 'Explorer retrieval tests passed'
