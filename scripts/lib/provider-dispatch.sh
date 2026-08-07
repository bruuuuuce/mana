#!/usr/bin/env bash
# Provider-neutral argument construction. Callers retain responsibility for
# provider discovery, prompt construction, supervision, and lifecycle events.

mana_provider_profile_args() {
  local provider="$1" project="$2" model="$3" max_threads="$4" max_depth="$5"
  MANA_PROVIDER_ARGS=()
  case "$provider" in
    codex)
      MANA_PROVIDER_ARGS=(--ask-for-approval on-request exec --model "$model" --cd "$project" --sandbox workspace-write -c "agents.max_threads=$max_threads" -c "agents.max_depth=$max_depth" -c "agents.interrupt_message=false") ;;
    claude)
      MANA_PROVIDER_ARGS=(-p --agent mana-orchestrator --model "$model" --permission-mode default) ;;
    opencode)
      MANA_PROVIDER_ARGS=(run --dir "$project" --model "$model" --agent mana_orchestrator) ;;
    *) return 1 ;;
  esac
}

mana_provider_repair_args() {
  local provider="$1" project="$2" model="$3"
  MANA_PROVIDER_ARGS=()
  case "$provider" in
    codex)
      MANA_PROVIDER_ARGS=(--ask-for-approval never exec --model "$model" --cd "$project" --sandbox workspace-write --ephemeral --ignore-user-config --disable multi_agent --disable multi_agent_v2 -c "agents.max_threads=1" -c "agents.max_depth=0" -c "agents.interrupt_message=false") ;;
    claude)
      MANA_PROVIDER_ARGS=(-p --model "$model" --permission-mode acceptEdits --safe-mode --no-session-persistence --disable-slash-commands --allowedTools Read,Edit,Write --disallowedTools Agent,Bash,WebFetch,WebSearch) ;;
    opencode)
      MANA_PROVIDER_ARGS=(run --dir "$project" --model "$model" --agent mana_worker) ;;
    stub)
      [ "${MANA_REPAIR_ALLOW_STUB:-false}" = true ] || return 1
      [ -n "${MANA_REPAIR_STUB_COMMAND:-}" ] || return 1
      MANA_PROVIDER_PROGRAM="$MANA_REPAIR_STUB_COMMAND"
      MANA_PROVIDER_ARGS=() ;;
    *) return 1 ;;
  esac
}
