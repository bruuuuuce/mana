#!/usr/bin/env bash

mana_provider_capabilities_probe_claude() {
  local binary="$1" probe_dir="$2"
  "$binary" --version > "$probe_dir/version.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'claude --version failed'
    return 4
  }
  "$binary" --help > "$probe_dir/root-help.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'claude --help failed'
    return 5
  }
}

mana_provider_capabilities_validate_claude_fixture() {
  mana_provider_capabilities_validate_fixture_files "$1" version.txt root-help.txt
}

mana_provider_capabilities_claude_help_valid() {
  local file="$1"
  awk '
    /^Usage: claude \[options\] \[command\] \[prompt\]$/ { usage=1 }
    /^Claude Code - starts an interactive session by default, use -p\/--print for$/ { title=1 }
    $0 == "Options:" { options=1 }
    END { exit(usage && title && options ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_claude_option_semantics() {
  local file="$1" option="$2" polarity="$3"
  awk -v option="$option" -v polarity="$polarity" '
    function option_start(line) { return line ~ /^[[:space:]]+(-[[:alnum:]], )?--[[:alnum:]][[:alnum:]-]*/ }
    function evaluate() {
      if (!capture) return
      lower=tolower(block)
      if (polarity == "negative") {
        if (lower ~ /(^|[ ;,.])(unsupported|unavailable)([ ;,.]|$)/ ||
            lower ~ /(this option|this setting|the option|the setting|it) (is )?ignored( at runtime)?/ ||
            lower ~ /(^|[ ;,.])ignored at runtime([ ;,.]|$)/ ||
            lower ~ /has no effect/ ||
            lower ~ /does not (work|apply|take effect)/ ||
            lower ~ /is not (supported|available)/) found=1
        return
      }
      if (option == "stream" && block ~ /--output-format <format> Output format \(only works with --print\):.*"stream-json" \(realtime streaming\).*choices: "text", "json", "stream-json"/) found=1
      if (option == "schema" && block ~ /--json-schema <schema> JSON Schema for structured output validation\./) found=1
      if (option == "print" && block ~ /-p, --print Print response and exit \(useful for pipes\)\./) found=1
      if (option == "ephemeral" && block ~ /--no-session-persistence Disable session persistence - sessions will not be saved to disk and cannot be resumed \(only works with --print\)/) found=1
      if (option == "model" && block ~ /--model <model> Model for the current session\./) found=1
      if (option == "effort" && block ~ /--effort <level> Effort level for the current session.*\(low, medium, high, xhigh, max\)/) found=1
      if (option == "agent" && block ~ /--agent <agent> Agent for the current session\. Overrides the .agent. setting\./) found=1
      if (option == "agents" && block ~ /--agents <json> JSON object defining custom agents/) found=1
      if (option == "safe-mode" && block ~ /--safe-mode Start with all customizations.*custom commands and agents.*disabled/) found=1
      if (option == "disallowed-tools" && block ~ /--disallowedTools, --disallowed-tools <tools\.\.\.> Comma or space-separated list of tool names to deny/) found=1
      if (option == "autocompact" && block ~ /--autocompact <auto\|tokens> Auto-compact window size \(auto, or 100k/) found=1
    }
    {
      if (option_start($0)) {
        evaluate()
        capture=0
        if ((option == "stream" && $0 ~ /^[[:space:]]+--output-format <format>[[:space:]]+/) ||
            (option == "schema" && $0 ~ /^[[:space:]]+--json-schema <schema>[[:space:]]+/) ||
            (option == "print" && $0 ~ /^[[:space:]]+-p, --print[[:space:]]+/) ||
            (option == "ephemeral" && $0 ~ /^[[:space:]]+--no-session-persistence[[:space:]]+/) ||
            (option == "model" && $0 ~ /^[[:space:]]+--model <model>[[:space:]]+/) ||
            (option == "effort" && $0 ~ /^[[:space:]]+--effort <level>[[:space:]]+/) ||
            (option == "agent" && $0 ~ /^[[:space:]]+--agent <agent>[[:space:]]+/) ||
            (option == "agents" && $0 ~ /^[[:space:]]+--agents <json>[[:space:]]+/) ||
            (option == "safe-mode" && $0 ~ /^[[:space:]]+--safe-mode[[:space:]]+/) ||
            (option == "disallowed-tools" && $0 ~ /^[[:space:]]+--disallowedTools, --disallowed-tools <tools\.\.\.>[[:space:]]*$/) ||
            (option == "autocompact" && $0 ~ /^[[:space:]]+--autocompact <auto\|tokens>[[:space:]]+/)) {
          capture=1
          block=$0
          gsub(/[[:space:]]+/, " ", block)
        }
        next
      }
      if (capture && $0 ~ /^[[:space:]]+/) {
        block=block " " $0
        gsub(/[[:space:]]+/, " ", block)
      } else if (capture) {
        evaluate()
        capture=0
      }
    }
    END { evaluate(); exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_claude_option_proven() {
  mana_provider_capabilities_claude_option_semantics "$1" "$2" positive
}

mana_provider_capabilities_claude_option_negated() {
  mana_provider_capabilities_claude_option_semantics "$1" "$2" negative
}

mana_provider_capabilities_claude_explicitly_unsupported() {
  local file="$1" capability="$2"
  awk -v capability="$capability" '
    $0 == "Claude Code capability status:" { section=1; next }
    section && $0 == "  " capability " unsupported" { found=1 }
    section && $0 !~ /^  [a-z0-9-]+ (supported|unsupported)$/ { section=0 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_render_claude() {
  local help="$1/root-help.txt"
  local stream_p=false stream_n=false final_p=false final_n=false schema_p=false schema_n=false
  local fresh_p=false fresh_n=false ephemeral_p=false ephemeral_n=false model_p=false model_n=false effort_p=false effort_n=false
  local agent_p=false agent_n=false agents_p=false agents_n=false subagents_direct_n=false
  local compact_p=false compact_n=false safe_p=false safe_n=false deny_p=false deny_n=false
  local hard_direct_n=false user_explicit_n=false
  if mana_provider_capabilities_claude_help_valid "$help"; then
    mana_provider_capabilities_claude_option_proven "$help" stream && stream_p=true
    mana_provider_capabilities_claude_option_negated "$help" stream && stream_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" structured-event-stream && stream_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" separate-final-output-file && final_n=true
    mana_provider_capabilities_claude_option_proven "$help" schema && schema_p=true
    mana_provider_capabilities_claude_option_negated "$help" schema && schema_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" structured-output-schema && schema_n=true
    mana_provider_capabilities_claude_option_proven "$help" print && fresh_p=true
    mana_provider_capabilities_claude_option_negated "$help" print && fresh_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" fresh-invocation && fresh_n=true
    mana_provider_capabilities_claude_option_proven "$help" ephemeral && ephemeral_p=true
    mana_provider_capabilities_claude_option_negated "$help" ephemeral && ephemeral_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" ephemeral-session && ephemeral_n=true
    mana_provider_capabilities_claude_option_proven "$help" model && model_p=true
    mana_provider_capabilities_claude_option_negated "$help" model && model_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" explicit-model-selection && model_n=true
    mana_provider_capabilities_claude_option_proven "$help" effort && effort_p=true
    mana_provider_capabilities_claude_option_negated "$help" effort && effort_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" explicit-reasoning-effort && effort_n=true
    mana_provider_capabilities_claude_option_proven "$help" agent && agent_p=true
    mana_provider_capabilities_claude_option_negated "$help" agent && agent_n=true
    mana_provider_capabilities_claude_option_proven "$help" agents && agents_p=true
    mana_provider_capabilities_claude_option_negated "$help" agents && agents_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" provider-managed-subagents && subagents_direct_n=true
    mana_provider_capabilities_claude_option_proven "$help" safe-mode && safe_p=true
    mana_provider_capabilities_claude_option_negated "$help" safe-mode && safe_n=true
    mana_provider_capabilities_claude_option_proven "$help" disallowed-tools && deny_p=true
    mana_provider_capabilities_claude_option_negated "$help" disallowed-tools && deny_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" user-configuration-isolation && user_explicit_n=true
    mana_provider_capabilities_claude_option_proven "$help" autocompact && compact_p=true
    mana_provider_capabilities_claude_option_negated "$help" autocompact && compact_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" automatic-compaction-threshold && compact_n=true
    mana_provider_capabilities_claude_explicitly_unsupported "$help" hard-subagent-disable && hard_direct_n=true
  fi
  # Safe mode proves only its declared customization scope. For the broader
  # user-configuration capability this is ambiguous evidence, not positive
  # evidence. An explicit negative without safe-mode evidence can still resolve
  # to unsupported; the combination remains unknown.
  local resolved subagents_derived subagents_derived_evidence subagents_record
  local hard_derived hard_derived_evidence hard_record
  resolved="$(jq -n \
    --argjson streamP "$stream_p" --argjson streamN "$stream_n" --argjson finalP "$final_p" --argjson finalN "$final_n" \
    --argjson schemaP "$schema_p" --argjson schemaN "$schema_n" --argjson freshP "$fresh_p" --argjson freshN "$fresh_n" \
    --argjson ephemeralP "$ephemeral_p" --argjson ephemeralN "$ephemeral_n" --argjson modelP "$model_p" --argjson modelN "$model_n" \
    --argjson effortP "$effort_p" --argjson effortN "$effort_n" \
    --argjson agentP "$agent_p" --argjson agentN "$agent_n" --argjson agentsP "$agents_p" --argjson agentsN "$agents_n" \
    --argjson compactP "$compact_p" --argjson compactN "$compact_n" \
    --argjson safeP "$safe_p" --argjson safeN "$safe_n" --argjson denyP "$deny_p" --argjson denyN "$deny_n" \
    --argjson userExplicitN "$user_explicit_n" '
    def ev($p;$pe;$n;$ne;$ue): {
      positiveEvidence:(if $p then [$pe] else [] end),
      negativeEvidence:(if $n then [$ne] else [] end),
      unknownEvidence:[$ue]
    };
    {
      structuredEventStream:ev($streamP;"help:stream-json-declaration";$streamN;"help:stream-json-negative-evidence";"help:stream-json-unverified"),
      separateFinalOutputFile:ev($finalP;"help:final-output-file-declaration";$finalN;"help:final-output-file-explicit-unsupported";"help:final-output-file-unverified"),
      structuredOutputSchema:ev($schemaP;"help:json-schema-declaration";$schemaN;"help:json-schema-negative-evidence";"help:json-schema-unverified"),
      freshInvocation:ev($freshP;"help:print-command-declaration";$freshN;"help:print-negative-evidence";"help:print-invocation-unverified"),
      ephemeralSession:ev($ephemeralP;"help:no-session-persistence-declaration";$ephemeralN;"help:no-session-persistence-negative-evidence";"help:no-session-persistence-unverified"),
      explicitModelSelection:ev($modelP;"help:model-declaration";$modelN;"help:model-negative-evidence";"help:model-unverified"),
      explicitReasoningEffort:ev($effortP;"help:effort-declaration";$effortN;"help:effort-negative-evidence";"help:effort-unverified"),
      _agentSelection:ev($agentP;"help:agent-selection-declaration";$agentN;"help:agent-selection-negative-evidence";"help:agent-selection-unverified"),
      _agentDefinitions:ev($agentsP;"help:agent-definitions-declaration";$agentsN;"help:agent-definitions-negative-evidence";"help:agent-definitions-unverified"),
      _safeMode:ev($safeP;"help:safe-mode-declaration";$safeN;"help:safe-mode-negative-evidence";"help:safe-mode-unverified"),
      _agentToolDeny:ev($denyP;"help:agent-tool-deny-declaration";$denyN;"help:agent-tool-deny-negative-evidence";"help:agent-tool-deny-unverified"),
      childContextInheritanceControl:ev(false;"";false;"";"probe:child-context-not-observable"),
      childModelRouting:ev(false;"";false;"";"probe:child-model-not-runtime-verified"),
      childReasoningEffortRouting:ev(false;"";false;"";"probe:child-effort-not-runtime-verified"),
      recursiveDelegationPrevention:ev(false;"";false;"";"probe:enabled-child-recursion-not-runtime-verified"),
      maximumChildConcurrency:ev(false;"";false;"";"config:child-concurrency-not-help-exposed"),
      maximumChildDepth:ev(false;"";false;"";"config:child-depth-not-help-exposed"),
      toolOutputRetentionTokenLimit:ev(false;"";false;"";"config:tool-output-limit-not-help-exposed"),
      automaticCompactionThreshold:ev($compactP;"help:autocompact-declaration";$compactN;"help:autocompact-negative-evidence";"help:autocompact-unverified"),
      customCompactionPrompt:ev(false;"";false;"";"probe:custom-compaction-prompt-not-observable"),
      compactionScope:ev(false;"";false;"";"probe:compaction-scope-not-observable"),
      userConfigurationIsolation:{
        positiveEvidence:[],
        negativeEvidence:(if $userExplicitN then ["help:user-config-isolation-explicit-unsupported"] else [] end),
        ambiguousEvidence:(if $safeP or $safeN then ["semantic:safe-mode-scope-insufficient"] else [] end),
        unknownEvidence:["help:user-config-isolation-unverified"]
      }
    }' | mana_provider_capabilities_resolve_evidence_map)" || return $?

  subagents_derived="$(mana_provider_capabilities_resolve_required_states \
    "$(jq -r '._agentSelection.status' <<<"$resolved")" \
    "$(jq -r '._agentDefinitions.status' <<<"$resolved")")" || return $?
  case "$subagents_derived" in
    supported) subagents_derived_evidence='help:agent-definitions-declaration' ;;
    unsupported) subagents_derived_evidence='help:agent-definitions-negative-evidence' ;;
    unknown) subagents_derived_evidence='help:agents-unverified' ;;
  esac
  if [ "$subagents_direct_n" = true ]; then
    local subagents_direct_state
    subagents_direct_state="$(jq -nc '{direct:{negativeEvidence:["help:agent-definitions-negative-evidence"]}}' |
      mana_provider_capabilities_resolve_evidence_map | jq -r '.direct.status')" || return $?
    subagents_record="$(mana_provider_capabilities_composite_record "$subagents_derived" "$subagents_derived_evidence" \
      "$subagents_direct_state" 'help:agent-definitions-negative-evidence')" || return $?
  else
    subagents_record="$(mana_provider_capabilities_composite_record "$subagents_derived" "$subagents_derived_evidence")" || return $?
  fi

  # hardSubagentDisable requires both resolved safe-mode semantics and a
  # resolved Agent-tool deny. Conflicted or incomplete option evidence reaches
  # this boundary only as unknown.
  hard_derived="$(mana_provider_capabilities_resolve_required_states \
    "$(jq -r '._safeMode.status' <<<"$resolved")" \
    "$(jq -r '._agentToolDeny.status' <<<"$resolved")")" || return $?
  case "$hard_derived" in
    supported) hard_derived_evidence='probe:claude-agent-tool-deny-proven' ;;
    unsupported) hard_derived_evidence='help:hard-disable-negative-evidence' ;;
    unknown) hard_derived_evidence='help:hard-disable-unverified' ;;
  esac
  if [ "$hard_direct_n" = true ]; then
    local hard_direct_state
    hard_direct_state="$(jq -nc '{direct:{negativeEvidence:["help:hard-disable-negative-evidence"]}}' |
      mana_provider_capabilities_resolve_evidence_map | jq -r '.direct.status')" || return $?
    hard_record="$(mana_provider_capabilities_composite_record "$hard_derived" "$hard_derived_evidence" \
      "$hard_direct_state" 'help:hard-disable-negative-evidence')" || return $?
  else
    hard_record="$(mana_provider_capabilities_composite_record "$hard_derived" "$hard_derived_evidence")" || return $?
  fi

  jq -c --argjson subagents "$subagents_record" --argjson hard "$hard_record" '
    del(._agentSelection, ._agentDefinitions, ._safeMode, ._agentToolDeny) |
    .providerManagedSubagents=$subagents | .hardSubagentDisable=$hard
  ' <<<"$resolved"
}

mana_provider_capabilities_evidence_claude() {
  printf '["version:ok","help:root"]\n'
}
