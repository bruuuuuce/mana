#!/usr/bin/env bash
# Provider-neutral argument construction. Callers retain responsibility for
# provider discovery, prompt construction, supervision, and lifecycle events.

mana_provider_profile_args() {
  local provider="$1" project="$2" model="$3" max_threads="$4" max_depth="$5" subagents="${6:-true}"
  MANA_PROVIDER_ARGS=()
  MANA_PROVIDER_OPENCODE_CONFIG_CONTENT=""
  case "$subagents" in true|false) ;; *) return 1 ;; esac
  case "$provider" in
    codex)
      MANA_PROVIDER_ARGS=(--ask-for-approval on-request exec --model "$model" --cd "$project" --sandbox workspace-write)
      if [ "$subagents" = true ]; then
        MANA_PROVIDER_ARGS+=(-c "agents.max_threads=$max_threads" -c "agents.max_depth=$max_depth" -c "agents.interrupt_message=false")
      else
        # Codex rejects max_threads=0. Disabling both known multi-agent
        # features removes child tools; depth zero and one inert thread keep
        # the remaining config valid. User config and stale managed agent
        # definitions cannot re-enable a disabled feature.
        MANA_PROVIDER_ARGS+=(--ephemeral --ignore-user-config --disable multi_agent --disable multi_agent_v2 -c "agents.max_threads=1" -c "agents.max_depth=0" -c "agents.interrupt_message=false")
      fi ;;
    claude)
      if [ "$subagents" = true ]; then
        MANA_PROVIDER_ARGS=(-p --agent mana-orchestrator --model "$model" --permission-mode default)
      else
        # Safe mode excludes project/user custom agents while the explicit
        # tool deny removes the provider-managed Agent entry point.
        MANA_PROVIDER_ARGS=(-p --model "$model" --permission-mode default --safe-mode --no-session-persistence --disable-slash-commands --disallowedTools Agent)
      fi ;;
    opencode)
      if [ "$subagents" = true ]; then
        MANA_PROVIDER_ARGS=(run --dir "$project" --model "$model" --agent mana_orchestrator)
      else
        # OPENCODE_CONFIG_CONTENT selects an invocation-local primary whose
        # built-in Task permission is denied. OpenCode still merges other
        # config surfaces, so this is real Task containment but not proof of
        # complete user/project configuration isolation.
        MANA_PROVIDER_OPENCODE_CONFIG_CONTENT="$(jq -cn --arg model "$model" '{agent:{mana_ctx02_no_children:{description:"Mana primary with child execution disabled",mode:"primary",model:$model,permission:{task:"deny"}}}}')" || return 1
        MANA_PROVIDER_ARGS=(run --dir "$project" --model "$model" --agent mana_ctx02_no_children --pure)
      fi ;;
    *) return 1 ;;
  esac
}

# CTX-01 only: Codex owns these invocation flags.  The neutral wrapper owns
# parsing and the public metric shape; profiles never see provider flags.
mana_provider_usage_args() {
  local provider="$1" final_message="$2"
  MANA_PROVIDER_USAGE_ARGS=()
  case "$provider" in
    codex) MANA_PROVIDER_USAGE_ARGS=(--json --output-last-message "$final_message") ;;
    *) return 1 ;;
  esac
}

# CTX-06C fresh phase worker.  Every adapter is read-only and mechanically
# disables provider-managed children; optional children are a CTX-07 concern.
# The final argument states whether the current CTX-02 probe proved native
# schema enforcement.  Host validation remains mandatory in either case.
mana_provider_phase_args() {
  local provider="$1" project="$2" model="$3" output_schema="$4" native_schema="${5:-false}" schema_json=""
  MANA_PROVIDER_ARGS=()
  MANA_PROVIDER_OPENCODE_CONFIG_CONTENT=""
  MANA_PROVIDER_PHASE_OUTPUT_MODE="direct-json"
  case "$native_schema" in true|false) ;; *) return 1 ;; esac
  [ -f "$output_schema" ] && [ ! -L "$output_schema" ] || return 1
  case "$provider" in
    codex)
      MANA_PROVIDER_ARGS=(--ask-for-approval never exec)
      [ "$native_schema" = false ] || MANA_PROVIDER_ARGS+=(--output-schema "$output_schema")
      MANA_PROVIDER_ARGS+=(--model "$model" --cd "$project" --sandbox read-only --ephemeral --ignore-user-config)
      MANA_PROVIDER_ARGS+=(--disable multi_agent --disable multi_agent_v2 -c "agents.max_threads=1" -c "agents.max_depth=0" -c "agents.interrupt_message=false")
      ;;
    claude)
      MANA_PROVIDER_ARGS=(-p --model "$model" --permission-mode default --safe-mode --no-session-persistence --disable-slash-commands --disallowedTools 'Agent,Bash,Edit,Write,WebFetch,WebSearch')
      if [ "$native_schema" = true ]; then
        schema_json="$(jq -c . "$output_schema")" || return 1
        MANA_PROVIDER_ARGS+=(--output-format json --json-schema "$schema_json")
        MANA_PROVIDER_PHASE_OUTPUT_MODE="claude-structured-json"
      fi
      ;;
    opencode)
      # CTX-02 proves the inline Task deny but does not currently prove hard
      # subagent disable.  CTX-06C's capability gate therefore rejects this
      # adapter before invocation; keep its argv deterministic for a future
      # capability improvement without claiming support now.
      MANA_PROVIDER_OPENCODE_CONFIG_CONTENT="$(jq -cn --arg model "$model" '{agent:{mana_ctx06_phase:{description:"Mana read-only fresh phase worker",mode:"primary",model:$model,permission:{task:"deny",edit:"deny",bash:"deny"}}}}')" || return 1
      MANA_PROVIDER_ARGS=(run --dir "$project" --model "$model" --agent mana_ctx06_phase --pure)
      ;;
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
