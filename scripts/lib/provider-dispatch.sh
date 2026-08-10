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

# A single, prompt-only T1 synthesis invocation. The optional fourth argument
# is an explicit host-owned workspace contract; it is never inferred from a
# path or a failed Git probe.
mana_provider_synthesis_args() {
  local provider="$1" workspace="$2" model="$3" workspace_contract="${4:-}" output_schema="${5:-}" reasoning_effort="${6:-}"
  case "$workspace_contract" in ''|host-disposable-non-git) ;; *) return 1;; esac
  case "$reasoning_effort" in ''|minimal|low|medium|high|xhigh) ;; *) return 1;; esac
  MANA_PROVIDER_ARGS=()
  case "$provider" in
    codex)
      MANA_PROVIDER_ARGS=(--ask-for-approval never exec)
      [ "$workspace_contract" != host-disposable-non-git ] || MANA_PROVIDER_ARGS+=(--skip-git-repo-check)
      # Codex can enforce a final-message JSON Schema.  The schema remains
      # host-owned; this only improves the transport contract for this provider.
      [ -z "$output_schema" ] || MANA_PROVIDER_ARGS+=(--output-schema "$output_schema")
      MANA_PROVIDER_ARGS+=(--model "$model" --cd "$workspace" --sandbox read-only --ephemeral --ignore-user-config)
      # Keep the invocation isolated from user config while allowing one
      # explicit, validated M3 effort override to survive that isolation.
      [ -z "$reasoning_effort" ] || MANA_PROVIDER_ARGS+=(-c "model_reasoning_effort=\"$reasoning_effort\"")
      MANA_PROVIDER_ARGS+=(--disable multi_agent --disable multi_agent_v2 -c "agents.max_threads=1" -c "agents.max_depth=0" -c "agents.interrupt_message=false") ;;
    claude)
      MANA_PROVIDER_ARGS=(-p --model "$model" --permission-mode default --no-session-persistence --disable-slash-commands --disallowedTools Agent,Bash,Read,Edit,Write,WebFetch,WebSearch) ;;
    opencode)
      MANA_PROVIDER_ARGS=(run --dir "$workspace" --model "$model" --agent mana_explorer) ;;
    stub)
      [ "${MANA_USER_LEARNING_ALLOW_STUB:-false}" = true ] || return 1
      [ -n "${MANA_USER_LEARNING_STUB_COMMAND:-}" ] || return 1
      MANA_PROVIDER_PROGRAM="$MANA_USER_LEARNING_STUB_COMMAND"
      MANA_PROVIDER_ARGS=() ;;
    *) return 1 ;;
  esac
}
