#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; . "$root/scripts/lib/provider-dispatch.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }
join() { printf '<%s>' "$@"; }
mana_provider_profile_args codex '/repo path' model 3 1; [ "$(join "${MANA_PROVIDER_ARGS[@]}")" = '<--ask-for-approval><on-request><exec><--model><model><--cd></repo path><--sandbox><workspace-write><-c><agents.max_threads=3><-c><agents.max_depth=1><-c><agents.interrupt_message=false>' ] || fail 'Codex profile args changed'
mana_provider_profile_args claude '/repo path' model 3 1; [ "$(join "${MANA_PROVIDER_ARGS[@]}")" = '<-p><--agent><mana-orchestrator><--model><model><--permission-mode><default>' ] || fail 'Claude profile args changed'
mana_provider_profile_args opencode '/repo path' model 3 1; [ "$(join "${MANA_PROVIDER_ARGS[@]}")" = '<run><--dir></repo path><--model><model><--agent><mana_orchestrator>' ] || fail 'OpenCode profile args changed'
mana_provider_repair_args codex '/repo path' model; [ "$(join "${MANA_PROVIDER_ARGS[@]}")" = '<--ask-for-approval><never><exec><--model><model><--cd></repo path><--sandbox><workspace-write><--ephemeral><--ignore-user-config><--disable><multi_agent><--disable><multi_agent_v2><-c><agents.max_threads=1><-c><agents.max_depth=0><-c><agents.interrupt_message=false>' ] || fail 'Codex repair containment args incorrect'
printf '%s\n' "${MANA_PROVIDER_ARGS[@]}" | grep -Fxq 'agents.max_depth=0' || fail 'repair subagents not disabled'
echo 'Provider dispatch tests passed'
