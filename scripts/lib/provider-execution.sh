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
  local trace="$1" line record input cached uncached output reasoning turn tool worker compact
  MANA_USAGE_INPUT=""; MANA_USAGE_CACHED=""; MANA_USAGE_UNCACHED=""; MANA_USAGE_OUTPUT=""; MANA_USAGE_REASONING=""
  MANA_USAGE_TURNS=""; MANA_USAGE_TOOL_CALLS=""; MANA_USAGE_WORKERS=""; MANA_USAGE_COMPACTIONS=""; MANA_USAGE_PARSE_ERRORS=0
  [ -f "$trace" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    record="$(printf '%s' "$line" | jq -cer '
      def nonnegative: select(type == "number" and . >= 0);
      def first_number($values): ($values | map(select(type == "number" and . >= 0)) | first // null);
      if type != "object" then error("object expected") else
        {input:first_number([.usage.input_tokens?, .usage.inputTokens?, .usage.input?]),
         cached:first_number([.usage.cached_input_tokens?, .usage.cachedInputTokens?, .usage.cached_input?, .usage.cachedInput?]),
         uncached:first_number([.usage.uncached_input_tokens?, .usage.uncachedInputTokens?, .usage.uncached_input?, .usage.uncachedInput?]),
         output:first_number([.usage.output_tokens?, .usage.outputTokens?, .usage.output?]),
         reasoning:first_number([.usage.reasoning_tokens?, .usage.reasoningTokens?, .usage.reasoning?]),
         turn:((.type? == "turn.completed") or (.event? == "turn.completed")),
         tool:((.type? == "item.completed") and ((.item.type? == "function_call") or (.item.type? == "tool_call") or (.item.type? == "command_execution"))) or (.type? == "tool.completed"),
         worker:((.type? == "agent.completed") or (.type? == "worker.completed")),
         compaction:((.type? == "compaction.completed") or (.type? == "context.compacted"))}
      end' 2>/dev/null)" || { MANA_USAGE_PARSE_ERRORS=$((MANA_USAGE_PARSE_ERRORS + 1)); continue; }
    # A count of zero is meaningful only after at least one well-formed event
    # has been observed. Otherwise preserve the provider's absence as null.
    [ -n "$MANA_USAGE_TURNS" ] || { MANA_USAGE_TURNS=0; MANA_USAGE_TOOL_CALLS=0; MANA_USAGE_WORKERS=0; }
    input="$(jq -r '.input // empty' <<<"$record")"; cached="$(jq -r '.cached // empty' <<<"$record")"; uncached="$(jq -r '.uncached // empty' <<<"$record")"; output="$(jq -r '.output // empty' <<<"$record")"; reasoning="$(jq -r '.reasoning // empty' <<<"$record")"
    [ -z "$input" ] || MANA_USAGE_INPUT=$(( ${MANA_USAGE_INPUT:-0} + input ))
    [ -z "$cached" ] || MANA_USAGE_CACHED=$(( ${MANA_USAGE_CACHED:-0} + cached ))
    [ -z "$uncached" ] || MANA_USAGE_UNCACHED=$(( ${MANA_USAGE_UNCACHED:-0} + uncached ))
    [ -z "$output" ] || MANA_USAGE_OUTPUT=$(( ${MANA_USAGE_OUTPUT:-0} + output ))
    [ -z "$reasoning" ] || MANA_USAGE_REASONING=$(( ${MANA_USAGE_REASONING:-0} + reasoning ))
    [ "$(jq -r .turn <<<"$record")" = true ] && MANA_USAGE_TURNS=$((MANA_USAGE_TURNS + 1))
    [ "$(jq -r .tool <<<"$record")" = true ] && MANA_USAGE_TOOL_CALLS=$((MANA_USAGE_TOOL_CALLS + 1))
    [ "$(jq -r .worker <<<"$record")" = true ] && MANA_USAGE_WORKERS=$((MANA_USAGE_WORKERS + 1))
    if [ "$(jq -r .compaction <<<"$record")" = true ]; then MANA_USAGE_COMPACTIONS=$(( ${MANA_USAGE_COMPACTIONS:-0} + 1 )); fi
  done < "$trace"
}

mana_provider_execute() (
  # $1 provider $2 project root $3 profile id $4 prompt $5 provider program.
  # MANA_PROVIDER_ARGS is supplied by provider-dispatch.sh.
  local provider="$1" project_root="$2" profile_id="$3" prompt="$4" provider_program="$5"
  local execution_id="${MANA_RUNTIME_EXECUTION_ID:-execution-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  local metrics_dir="$project_root/.mana/runtime/metrics/$execution_id" trace final_message status=0 summary_status usage_status raw_retained=false retain_raw=false
  local input="" cached="" uncached="" output="" reasoning="" turns="" tool_calls="" workers="" compactions="" parse_errors=0
  umask 077
  case "$execution_id" in execution-?*) ;; *) echo 'ERROR: MANA_RUNTIME_EXECUTION_ID must begin with execution- and contain an identifier' >&2; exit 2 ;; esac
  case "$execution_id" in *[!A-Za-z0-9._-]*) echo 'ERROR: MANA_RUNTIME_EXECUTION_ID contains unsafe characters' >&2; exit 2 ;; esac
  retain_raw="$(mana_usage_bool "${MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE:-false}")" || { echo 'ERROR: MANA_RUNTIME_USAGE_RETAIN_RAW_TRACE must be true or false' >&2; exit 2; }
  mkdir -p "$metrics_dir" || { echo "WARNING: usage metric storage unavailable: $metrics_dir" >&2; "${provider_program}" "${MANA_PROVIDER_ARGS[@]}" "$prompt"; exit $?; }
  trace="$(mktemp "${TMPDIR:-/tmp}/mana-provider-events.XXXXXX")" || exit 1
  final_message="$(mktemp "${TMPDIR:-/tmp}/mana-provider-final.XXXXXX")" || { rm -f "$trace"; exit 1; }
  rm -f "$final_message"
  cleanup_provider_execution() {
    [ "$retain_raw" = true ] || rm -f "${trace:-}"
    rm -f "${final_message:-}"
  }
  trap cleanup_provider_execution EXIT HUP INT TERM

  if [ "$provider" = codex ]; then
    mana_provider_usage_args codex "$final_message" || exit 2
    "${provider_program}" "${MANA_PROVIDER_ARGS[@]}" "${MANA_PROVIDER_USAGE_ARGS[@]}" "$prompt" > "$trace"
    status=$?
    [ -f "$final_message" ] && cat "$final_message"
    mana_usage_parse_codex_trace "$trace"
    input="$MANA_USAGE_INPUT"; cached="$MANA_USAGE_CACHED"; uncached="$MANA_USAGE_UNCACHED"; output="$MANA_USAGE_OUTPUT"; reasoning="$MANA_USAGE_REASONING"; turns="$MANA_USAGE_TURNS"; tool_calls="$MANA_USAGE_TOOL_CALLS"; workers="$MANA_USAGE_WORKERS"; compactions="$MANA_USAGE_COMPACTIONS"; parse_errors="$MANA_USAGE_PARSE_ERRORS"
    if [ -n "$input$cached$uncached$output$reasoning" ]; then usage_status=measured; else usage_status=unavailable; fi
  else
    "${provider_program}" "${MANA_PROVIDER_ARGS[@]}" "$prompt"
    status=$?
    usage_status=unavailable
  fi
  case "$status" in 0) summary_status=complete ;; 130|143) summary_status=interrupted ;; *) summary_status=failed ;; esac
  if [ "$retain_raw" = true ] && [ "$provider" = codex ]; then
    mv "$trace" "$metrics_dir/raw-provider-events.jsonl" && chmod 600 "$metrics_dir/raw-provider-events.jsonl"
    trace=""; raw_retained=true
    echo 'WARNING: raw provider event retention is enabled locally; the trace may contain private data.' >&2
  fi
  mana_usage_write_summary "$metrics_dir" "$execution_id" "$profile_id" "$provider" "$summary_status" "$usage_status" "$input" "$cached" "$uncached" "$output" "$reasoning" "$turns" "$tool_calls" "$workers" "$compactions" "$raw_retained" "$parse_errors" || echo "WARNING: usage summary could not be written for $execution_id" >&2
  exit "$status"
)
