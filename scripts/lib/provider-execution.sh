#!/usr/bin/env bash
# Privacy-preserving provider execution and usage-summary writer.  This module
# deliberately keeps provider transcripts outside the repository unless local
# debugging explicitly requests otherwise.

mana_usage_bool() {
  case "${1:-false}" in
    true|TRUE|True|1|yes|YES|on|ON) printf 'true' ;;
    false|FALSE|False|0|no|NO|off|OFF|'') printf 'false' ;;
    *) return 1 ;;
  esac
}

mana_usage_json_number_or_null() {
  case "${1:-}" in ''|null) printf 'null' ;; *[!0-9]*) printf 'null' ;; *) printf '%s' "$1" ;; esac
}

# This is deliberately below Bash's signed-integer ceiling. Values arriving
# from a provider are validated by jq and again here before Bash sees them in
# arithmetic. Totals that exceed this supported domain become unavailable;
# Mana never rounds or invents a usage value.
MANA_USAGE_MAX_INTEGER=9007199254740991

mana_usage_supported_integer() {
  case "${1:-}" in ''|*[!0-9]*) return 1 ;; esac
  [ "${#1}" -lt "${#MANA_USAGE_MAX_INTEGER}" ] && return 0
  [ "${#1}" -gt "${#MANA_USAGE_MAX_INTEGER}" ] && return 1
  [[ "$1" < "$MANA_USAGE_MAX_INTEGER" || "$1" == "$MANA_USAGE_MAX_INTEGER" ]]
}

mana_usage_add() {
  # $1 current total (or empty), $2 already validated provider integer.
  # The caller receives the result in MANA_USAGE_ADD_RESULT.
  local current="$1" increment="$2"
  mana_usage_supported_integer "$increment" || return 1
  if [ -z "$current" ]; then
    MANA_USAGE_ADD_RESULT="$increment"
    return 0
  fi
  mana_usage_supported_integer "$current" || return 1
  (( current <= MANA_USAGE_MAX_INTEGER - increment )) || return 1
  MANA_USAGE_ADD_RESULT=$((current + increment))
}

mana_usage_write_summary() {
  # $1 metrics directory; the remaining arguments are controlled operational
  # values only.  Do not add arbitrary strings here: this artifact is a
  # privacy boundary, not an execution transcript.
  local metrics_dir="$1" execution_id="$2" profile_id="$3" provider="$4" status="$5" usage_status="$6" input="$7" cached="$8" uncached="$9" output="${10}" reasoning="${11}" turns="${12}" tool_calls="${13}" workers="${14}" compactions="${15}" raw_retained="${16}" parse_errors="${17}"
  local json_tmp="$metrics_dir/.usage-summary-v1.json.$$" md_tmp="$metrics_dir/.usage-summary-v1.md.$$"

  jq -n \
    --arg schemaVersion '1' \
    --arg executionId "$execution_id" \
    --arg profileId "$profile_id" \
    --arg provider "$provider" \
    --arg status "$status" \
    --arg usageStatus "$usage_status" \
    --argjson input "$(mana_usage_json_number_or_null "$input")" \
    --argjson cachedInput "$(mana_usage_json_number_or_null "$cached")" \
    --argjson uncachedInput "$(mana_usage_json_number_or_null "$uncached")" \
    --argjson output "$(mana_usage_json_number_or_null "$output")" \
    --argjson reasoning "$(mana_usage_json_number_or_null "$reasoning")" \
    --argjson turns "$(mana_usage_json_number_or_null "$turns")" \
    --argjson toolCalls "$(mana_usage_json_number_or_null "$tool_calls")" \
    --argjson workers "$(mana_usage_json_number_or_null "$workers")" \
    --argjson compactions "$(mana_usage_json_number_or_null "$compactions")" \
    --argjson rawTraceRetained "$raw_retained" \
    --argjson parseErrors "$parse_errors" \
    '{schemaVersion:$schemaVersion, executionId:$executionId, profileId:$profileId,
      provider:$provider, providerVersion:null, status:$status,
      usageStatus:$usageStatus, phases:[],
      totals:{input:$input, cachedInput:$cachedInput, uncachedInput:$uncachedInput,
              output:$output, reasoning:$reasoning},
      turns:$turns, toolCalls:$toolCalls, workers:$workers, compactions:$compactions,
      rawTraceRetained:$rawTraceRetained, parseErrors:$parseErrors}' > "$json_tmp" || return 1
  mv "$json_tmp" "$metrics_dir/usage-summary-v1.json" || return 1

  {
    printf '# Mana usage summary v1\n\n'
    printf '%-20s %s\n' 'Execution ID' "$execution_id"
    printf '%-20s %s\n' 'Profile ID' "$profile_id"
    printf '%-20s %s\n' 'Provider' "$provider"
    printf '%-20s %s\n' 'Status' "$status"
    printf '%-20s %s\n' 'Usage status' "$usage_status"
    printf '%-20s %s\n' 'Input' "$(mana_usage_json_number_or_null "$input")"
    printf '%-20s %s\n' 'Cached input' "$(mana_usage_json_number_or_null "$cached")"
    printf '%-20s %s\n' 'Uncached input' "$(mana_usage_json_number_or_null "$uncached")"
    printf '%-20s %s\n' 'Output' "$(mana_usage_json_number_or_null "$output")"
    printf '%-20s %s\n' 'Reasoning' "$(mana_usage_json_number_or_null "$reasoning")"
    printf '%-20s %s\n' 'Turns' "$(mana_usage_json_number_or_null "$turns")"
    printf '%-20s %s\n' 'Tool calls' "$(mana_usage_json_number_or_null "$tool_calls")"
    printf '%-20s %s\n' 'Workers' "$(mana_usage_json_number_or_null "$workers")"
    printf '%-20s %s\n' 'Compactions' "$(mana_usage_json_number_or_null "$compactions")"
    printf '%-20s %s\n' 'Raw trace retained' "$raw_retained"
    printf '%-20s %s\n' 'Parse errors' "$parse_errors"
  } > "$md_tmp" && mv "$md_tmp" "$metrics_dir/usage-summary-v1.md"
}

mana_usage_parse_codex_trace() {
  # $1 trace.  The compact record emitted for each valid JSON object contains
  # numbers and booleans only, so large tool payloads are never copied into a
  # metric or a parser intermediary.
  local trace="$1" line record input cached uncached output reasoning turn tool worker compact invalid
  MANA_USAGE_INPUT=""; MANA_USAGE_CACHED=""; MANA_USAGE_UNCACHED=""; MANA_USAGE_OUTPUT=""; MANA_USAGE_REASONING=""
  MANA_USAGE_TURNS=""; MANA_USAGE_TOOL_CALLS=""; MANA_USAGE_WORKERS=""; MANA_USAGE_COMPACTIONS=""; MANA_USAGE_PARSE_ERRORS=0
  [ -f "$trace" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    record="$(printf '%s' "$line" | jq -cer --argjson maxInteger "$MANA_USAGE_MAX_INTEGER" '
      def usage_field($keys):
        [$keys[] as $key | select((.usage? | type) == "object") | select(.usage | has($key)) | .usage[$key]] as $values |
        if ($values | length) == 0 then {value:null, invalid:false}
        elif ($values[0] | type == "number" and floor == . and . >= 0 and . <= $maxInteger) then {value:($values[0] | tostring), invalid:false}
        else {value:null, invalid:true}
        end;
      if type != "object" then error("object expected") else
        {input:usage_field(["input_tokens", "inputTokens", "input"]),
         cached:usage_field(["cached_input_tokens", "cachedInputTokens", "cached_input", "cachedInput"]),
         uncached:usage_field(["uncached_input_tokens", "uncachedInputTokens", "uncached_input", "uncachedInput"]),
         output:usage_field(["output_tokens", "outputTokens", "output"]),
         reasoning:usage_field(["reasoning_tokens", "reasoningTokens", "reasoning"]),
         turn:((.type? == "turn.completed") or (.event? == "turn.completed")),
         tool:((.type? == "item.completed") and ((.item.type? == "function_call") or (.item.type? == "tool_call") or (.item.type? == "command_execution"))) or (.type? == "tool.completed"),
         worker:((.type? == "agent.completed") or (.type? == "worker.completed")),
         compaction:((.type? == "compaction.completed") or (.type? == "context.compacted"))}
      end' 2>/dev/null)" || { MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); continue; }
    # A count of zero is meaningful only after at least one well-formed event
    # has been observed. Otherwise preserve the provider's absence as null.
    [ -n "$MANA_USAGE_TURNS" ] || { MANA_USAGE_TURNS=0; MANA_USAGE_TOOL_CALLS=0; MANA_USAGE_WORKERS=0; }
    invalid="$(jq -r '[.input.invalid, .cached.invalid, .uncached.invalid, .output.invalid, .reasoning.invalid] | any' <<<"$record")"
    [ "$invalid" = true ] && MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1))
    input="$(jq -r '.input.value // empty' <<<"$record")"; cached="$(jq -r '.cached.value // empty' <<<"$record")"; uncached="$(jq -r '.uncached.value // empty' <<<"$record")"; output="$(jq -r '.output.value // empty' <<<"$record")"; reasoning="$(jq -r '.reasoning.value // empty' <<<"$record")"
    if [ -n "$input" ]; then mana_usage_add "$MANA_USAGE_INPUT" "$input" && MANA_USAGE_INPUT="$MANA_USAGE_ADD_RESULT" || { MANA_USAGE_INPUT=""; MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); }; fi
    if [ -n "$cached" ]; then mana_usage_add "$MANA_USAGE_CACHED" "$cached" && MANA_USAGE_CACHED="$MANA_USAGE_ADD_RESULT" || { MANA_USAGE_CACHED=""; MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); }; fi
    if [ -n "$uncached" ]; then mana_usage_add "$MANA_USAGE_UNCACHED" "$uncached" && MANA_USAGE_UNCACHED="$MANA_USAGE_ADD_RESULT" || { MANA_USAGE_UNCACHED=""; MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); }; fi
    if [ -n "$output" ]; then mana_usage_add "$MANA_USAGE_OUTPUT" "$output" && MANA_USAGE_OUTPUT="$MANA_USAGE_ADD_RESULT" || { MANA_USAGE_OUTPUT=""; MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); }; fi
    if [ -n "$reasoning" ]; then mana_usage_add "$MANA_USAGE_REASONING" "$reasoning" && MANA_USAGE_REASONING="$MANA_USAGE_ADD_RESULT" || { MANA_USAGE_REASONING=""; MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); }; fi
    [ "$(jq -r .turn <<<"$record")" = true ] && MANA_USAGE_TURNS=$((MANA_USAGE_TURNS + 1))
    [ "$(jq -r .tool <<<"$record")" = true ] && MANA_USAGE_TOOL_CALLS=$((MANA_USAGE_TOOL_CALLS + 1))
    [ "$(jq -r .worker <<<"$record")" = true ] && MANA_USAGE_WORKERS=$((MANA_USAGE_WORKERS + 1))
    if [ "$(jq -r .compaction <<<"$record")" = true ]; then MANA_USAGE_COMPACTIONS=$(( ${MANA_USAGE_COMPACTIONS:-0} + 1 )); fi
  done < "$trace"
}

mana_provider_execute() {
  # $1 provider $2 project root $3 profile id $4 prompt $5 provider program;
  # $6... provider argv. Positional arguments are the transport contract: no
  # provider argv is serialized into an environment variable or reconstructed.
  local provider="$1" project_root="$2" profile_id="$3" prompt="$4" provider_program="$5"
  shift 5
  local provider_args=("$@") provider_usage_args=() provider_pid="" interrupted_status="" finalized=false
  local execution_id="${MANA_RUNTIME_EXECUTION_ID:-execution-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  local metrics_dir="$project_root/.mana/runtime/metrics/$execution_id" trace final_message status=0 summary_status usage_status=unavailable raw_retained=false retain_raw=false
  local input="" cached="" uncached="" output="" reasoning="" turns="" tool_calls="" workers="" compactions="" parse_errors=0
  umask 077
  case "$execution_id" in execution-?*) ;; *) echo 'ERROR: MANA_RUNTIME_EXECUTION_ID must begin with execution- and contain an identifier' >&2; return 2 ;; esac
  case "$execution_id" in *[!A-Za-z0-9._-]*) echo 'ERROR: MANA_RUNTIME_EXECUTION_ID contains unsafe characters' >&2; return 2 ;; esac
  retain_raw="$(mana_usage_bool "${MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE:-false}")" || { echo 'ERROR: MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE must be true or false' >&2; return 2; }
  mkdir -p "$metrics_dir" || { echo "WARNING: usage metric storage unavailable: $metrics_dir" >&2; "${provider_program}" "${provider_args[@]}" "$prompt"; return $?; }
  chmod 700 "$metrics_dir" || { echo "WARNING: usage metric storage permissions unavailable: $metrics_dir" >&2; "${provider_program}" "${provider_args[@]}" "$prompt"; return $?; }
  trace="$(mktemp "${TMPDIR:-/tmp}/mana-provider-events.XXXXXX")" || return 1
  chmod 600 "$trace" || { rm -f "$trace"; return 1; }
  final_message="$(mktemp "${TMPDIR:-/tmp}/mana-provider-final.XXXXXX")" || { rm -f "$trace"; return 1; }
  rm -f "$final_message"

  mana_provider_execute_finalize() {
    local exit_status="$1"
    [ "$finalized" = false ] || return 0
    finalized=true
    trap - EXIT HUP INT TERM
    if [ "$provider" = codex ] && [ -f "${trace:-}" ]; then
      mana_usage_parse_codex_trace "$trace"
      input="$MANA_USAGE_INPUT"; cached="$MANA_USAGE_CACHED"; uncached="$MANA_USAGE_UNCACHED"; output="$MANA_USAGE_OUTPUT"; reasoning="$MANA_USAGE_REASONING"; turns="$MANA_USAGE_TURNS"; tool_calls="$MANA_USAGE_TOOL_CALLS"; workers="$MANA_USAGE_WORKERS"; compactions="$MANA_USAGE_COMPACTIONS"; parse_errors="$MANA_USAGE_PARSE_ERRORS"
      if [ -n "$input$cached$uncached$output$reasoning" ]; then usage_status=measured; else usage_status=unavailable; fi
    fi
    case "$exit_status" in 0) summary_status=complete ;; 129|130|143) summary_status=interrupted ;; *) summary_status=failed ;; esac
    if [ "$retain_raw" = true ] && [ "$provider" = codex ] && [ -f "${trace:-}" ]; then
      if mv "$trace" "$metrics_dir/raw-provider-events.jsonl" && chmod 600 "$metrics_dir/raw-provider-events.jsonl"; then
        trace=""; raw_retained=true
        echo 'WARNING: raw provider event retention is enabled locally; the trace may contain private data.' >&2
      fi
    fi
    mana_usage_write_summary "$metrics_dir" "$execution_id" "$profile_id" "$provider" "$summary_status" "$usage_status" "$input" "$cached" "$uncached" "$output" "$reasoning" "$turns" "$tool_calls" "$workers" "$compactions" "$raw_retained" "$parse_errors" || echo "WARNING: usage summary could not be written for $execution_id" >&2
    rm -f "${trace:-}" "${final_message:-}"
    return 0
  }
  mana_provider_execute_signal() {
    local signal_name="$1" signal_status="$2"
    trap - "$signal_name"
    interrupted_status="$signal_status"
    [ -z "$provider_pid" ] || kill -TERM "$provider_pid" 2>/dev/null || true
  }
  trap 'mana_provider_execute_finalize "$?"' EXIT
  trap 'mana_provider_execute_signal HUP 129' HUP
  trap 'mana_provider_execute_signal INT 130' INT
  trap 'mana_provider_execute_signal TERM 143' TERM

  if [ "$provider" = codex ]; then
    if ! mana_provider_usage_args codex "$final_message"; then
      mana_provider_execute_finalize 2
      return 2
    fi
    provider_usage_args=("${MANA_PROVIDER_USAGE_ARGS[@]}")
    "${provider_program}" "${provider_args[@]}" "${provider_usage_args[@]}" "$prompt" > "$trace" &
    provider_pid=$!
    if wait "$provider_pid"; then status=0; else status=$?; fi
    if [ -n "$interrupted_status" ]; then
      # A trapped signal can interrupt wait before the provider has reaped.
      # The handler has already sent it SIGTERM; reap it before cleanup.
      wait "$provider_pid" 2>/dev/null || true
    fi
    provider_pid=""
    [ -z "$interrupted_status" ] || status="$interrupted_status"
    [ -f "$final_message" ] && cat "$final_message"
  else
    "${provider_program}" "${provider_args[@]}" "$prompt" &
    provider_pid=$!
    if wait "$provider_pid"; then status=0; else status=$?; fi
    if [ -n "$interrupted_status" ]; then
      wait "$provider_pid" 2>/dev/null || true
    fi
    provider_pid=""
    [ -z "$interrupted_status" ] || status="$interrupted_status"
    usage_status=unavailable
  fi
  mana_provider_execute_finalize "$status"
  return "$status"
}
