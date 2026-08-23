#!/usr/bin/env bash

mana_provider_capabilities_probe_codex() {
  local binary="$1" probe_dir="$2"
  "$binary" --version > "$probe_dir/version.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'codex --version failed'
    return 4
  }
  "$binary" --help > "$probe_dir/root-help.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'codex --help failed'
    return 5
  }
  "$binary" exec --help > "$probe_dir/run-help.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'codex exec --help failed'
    return 5
  }
  "$binary" features list > "$probe_dir/features.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'codex feature probe failed'
    return 5
  }
}

mana_provider_capabilities_validate_codex_fixture() {
  mana_provider_capabilities_validate_fixture_files "$1" version.txt root-help.txt run-help.txt features.txt
}

mana_provider_capabilities_codex_features_valid() {
  local file="$1"
  [ -s "$file" ] || return 1
  ! grep -Ev '^[A-Za-z0-9_]+[[:space:]]+(stable|experimental|under development|deprecated|removed)[[:space:]]+(true|false)$' "$file" | grep -q .
}

mana_provider_capabilities_codex_help_valid() {
  local file="$1" surface="$2"
  awk -v surface="$surface" '
    surface == "root" && $0 == "Codex CLI" { title=1 }
    surface == "root" && $0 ~ /^Usage: codex \[OPTIONS\]/ { usage=1 }
    surface == "root" && $0 == "Commands:" { commands=1 }
    surface == "exec" && $0 == "Run Codex non-interactively" { title=1 }
    surface == "exec" && $0 ~ /^Usage: codex exec \[OPTIONS\]/ { usage=1 }
    $0 == "Options:" { options=1 }
    END { exit(title && usage && options && (surface != "root" || commands) ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_codex_option_proven() {
  local file="$1" option="$2"
  awk -v option="$option" '
    function option_start(line) {
      return line ~ /^[[:space:]]+(-[[:alnum:]], )?--[[:alnum:]][[:alnum:]-]*/
    }
    function evaluate() {
      if (!capture) return
      if (option == "json" && block ~ /^[[:space:]]+--json[[:space:]]+Print events to stdout as JSONL[[:space:]]*$/) found=1
      if (option == "final" && block ~ /^[[:space:]]+-o, --output-last-message <FILE>[[:space:]]+Specifies file where the last message from the agent should be written[[:space:]]*$/) found=1
      if (option == "schema" && block ~ /^[[:space:]]+--output-schema <FILE>[[:space:]]+Path to a JSON Schema file describing the model.s final response shape[[:space:]]*$/) found=1
      if (option == "ephemeral" && block ~ /^[[:space:]]+--ephemeral[[:space:]]+Run without persisting session files to disk[[:space:]]*$/) found=1
      if (option == "model" && block ~ /^[[:space:]]+-m, --model <MODEL>[[:space:]]+Model the agent should use[[:space:]]*$/) found=1
      if (option == "ignore-user-config" && block ~ /^[[:space:]]+--ignore-user-config[[:space:]]+Do not load `?\$CODEX_HOME\/config.toml`?; auth still uses `?CODEX_HOME`?[[:space:]]*$/) found=1
      if (option == "disable" && block ~ /^[[:space:]]+--disable <FEATURE>[[:space:]]+Disable a feature \(repeatable\)\. Equivalent to `-c features\.<name>=false`[[:space:]]*$/) found=1
    }
    {
      if (option_start($0)) {
        evaluate()
        capture=0
        if ((option == "json" && $0 ~ /^[[:space:]]+--json[[:space:]]*$/) ||
            (option == "final" && $0 ~ /^[[:space:]]+-o, --output-last-message <FILE>[[:space:]]*$/) ||
            (option == "schema" && $0 ~ /^[[:space:]]+--output-schema <FILE>[[:space:]]*$/) ||
            (option == "ephemeral" && $0 ~ /^[[:space:]]+--ephemeral[[:space:]]*$/) ||
            (option == "model" && $0 ~ /^[[:space:]]+-m, --model <MODEL>[[:space:]]*$/) ||
            (option == "ignore-user-config" && $0 ~ /^[[:space:]]+--ignore-user-config[[:space:]]*$/) ||
            (option == "disable" && $0 ~ /^[[:space:]]+--disable <FEATURE>[[:space:]]*$/)) {
          capture=1
          block=$0
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

mana_provider_capabilities_codex_explicitly_unsupported() {
  local file="$1" capability="$2"
  awk -v capability="$capability" '
    $0 == "Codex capability status:" { section=1; next }
    section && $0 == "  " capability " unsupported" { found=1 }
    section && $0 !~ /^  [a-z0-9-]+ (supported|unsupported)$/ { section=0 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_codex_feature_positive() {
  local file="$1" feature="$2"
  awk -v feature="$feature" '
    $1 != feature { next }
    $2 ~ /^(stable|experimental|deprecated)$/ && $3 ~ /^(true|false)$/ { found=1 }
    $2 == "under" && $3 == "development" && $4 ~ /^(true|false)$/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_codex_feature_negative() {
  local file="$1" feature="$2"
  awk -v feature="$feature" '
    $1 == feature && $2 == "removed" && $3 == "false" { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_render_codex() {
  local probe_dir root_help run_help features
  probe_dir="$1"
  root_help="$probe_dir/root-help.txt"
  run_help="$probe_dir/run-help.txt"
  features="$probe_dir/features.txt"
  local stream_p=false stream_n=false final_p=false final_n=false schema_p=false schema_n=false
  local fresh_p=false fresh_n=false ephemeral_p=false ephemeral_n=false model_p=false model_n=false
  local subagents_p=false subagents_n=false user_p=false user_n=false
  local multi_v2_p=false multi_v2_n=false disable_p=false hard_direct_n=false
  if mana_provider_capabilities_codex_help_valid "$run_help" exec; then
    mana_provider_capabilities_codex_option_proven "$run_help" json && stream_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" structured-event-stream && stream_n=true
    mana_provider_capabilities_codex_option_proven "$run_help" final && final_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" separate-final-output-file && final_n=true
    mana_provider_capabilities_codex_option_proven "$run_help" schema && schema_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" structured-output-schema && schema_n=true
    fresh_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" fresh-invocation && fresh_n=true
    mana_provider_capabilities_codex_option_proven "$run_help" ephemeral && ephemeral_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" ephemeral-session && ephemeral_n=true
    mana_provider_capabilities_codex_option_proven "$run_help" model && model_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" explicit-model-selection && model_n=true
    mana_provider_capabilities_codex_option_proven "$run_help" ignore-user-config && user_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$run_help" user-configuration-isolation && user_n=true
  fi
  if mana_provider_capabilities_codex_features_valid "$features"; then
    mana_provider_capabilities_codex_feature_positive "$features" multi_agent && subagents_p=true
    mana_provider_capabilities_codex_feature_negative "$features" multi_agent && subagents_n=true
    mana_provider_capabilities_codex_feature_positive "$features" multi_agent_v2 && multi_v2_p=true
    mana_provider_capabilities_codex_feature_negative "$features" multi_agent_v2 && multi_v2_n=true
  fi
  if mana_provider_capabilities_codex_help_valid "$root_help" root; then
    mana_provider_capabilities_codex_option_proven "$root_help" disable && disable_p=true
    mana_provider_capabilities_codex_explicitly_unsupported "$root_help" hard-subagent-disable && hard_direct_n=true
  fi
  if mana_provider_capabilities_codex_help_valid "$run_help" exec; then
    if mana_provider_capabilities_codex_explicitly_unsupported "$run_help" provider-managed-subagents; then
      subagents_n=true
    fi
    if mana_provider_capabilities_codex_explicitly_unsupported "$run_help" hard-subagent-disable; then
      hard_direct_n=true
    fi
  fi
  local resolved hard_derived hard_derived_evidence hard_direct_state hard_record
  resolved="$(jq -n \
    --argjson streamP "$stream_p" --argjson streamN "$stream_n" --argjson finalP "$final_p" --argjson finalN "$final_n" \
    --argjson schemaP "$schema_p" --argjson schemaN "$schema_n" --argjson freshP "$fresh_p" --argjson freshN "$fresh_n" \
    --argjson ephemeralP "$ephemeral_p" --argjson ephemeralN "$ephemeral_n" --argjson modelP "$model_p" --argjson modelN "$model_n" \
    --argjson subagentsP "$subagents_p" --argjson subagentsN "$subagents_n" \
    --argjson multiV2P "$multi_v2_p" --argjson multiV2N "$multi_v2_n" --argjson disableP "$disable_p" \
    --argjson userP "$user_p" --argjson userN "$user_n" '
    def ev($p;$pe;$n;$ne;$ue): {
      positiveEvidence:(if $p then [$pe] else [] end),
      negativeEvidence:(if $n then [$ne] else [] end),
      unknownEvidence:[$ue]
    };
    {
      structuredEventStream:ev($streamP;"help:exec-json-declaration";$streamN;"help:structured-event-stream-explicit-unsupported";"help:exec-json-unverified"),
      separateFinalOutputFile:ev($finalP;"help:final-output-file-declaration";$finalN;"help:final-output-file-explicit-unsupported";"help:final-output-file-unverified"),
      structuredOutputSchema:ev($schemaP;"help:output-schema-declaration";$schemaN;"help:output-schema-explicit-unsupported";"help:output-schema-unverified"),
      freshInvocation:ev($freshP;"help:exec-command-declaration";$freshN;"help:fresh-invocation-explicit-unsupported";"help:exec-command-unverified"),
      ephemeralSession:ev($ephemeralP;"help:ephemeral-declaration";$ephemeralN;"help:ephemeral-explicit-unsupported";"help:ephemeral-unverified"),
      explicitModelSelection:ev($modelP;"help:model-declaration";$modelN;"help:model-explicit-unsupported";"help:model-unverified"),
      explicitReasoningEffort:ev(false;"";false;"";"config:reasoning-effort-not-runtime-verified"),
      providerManagedSubagents:ev($subagentsP;"features:multi-agent-declaration";$subagentsN;"features:multi-agent-removed";"features:multi-agent-unverified"),
      _multiAgentV2:ev($multiV2P;"features:multi-agent-v2-declaration";$multiV2N;"features:multi-agent-v2-removed";"features:multi-agent-v2-unverified"),
      _featureDisableControl:ev($disableP;"help:feature-disable-declaration";false;"";"help:feature-disable-unverified"),
      childContextInheritanceControl:ev(false;"";false;"";"probe:child-context-not-observable"),
      childModelRouting:ev(false;"";false;"";"probe:child-model-not-runtime-verified"),
      childReasoningEffortRouting:ev(false;"";false;"";"probe:child-effort-not-runtime-verified"),
      recursiveDelegationPrevention:ev(false;"";false;"";"probe:enabled-child-recursion-not-runtime-verified"),
      maximumChildConcurrency:ev(false;"";false;"";"config:max-threads-not-runtime-verified"),
      maximumChildDepth:ev(false;"";false;"";"config:max-depth-not-runtime-verified"),
      toolOutputRetentionTokenLimit:ev(false;"";false;"";"config:tool-output-limit-not-help-exposed"),
      automaticCompactionThreshold:ev(false;"";false;"";"config:compaction-threshold-not-help-exposed"),
      customCompactionPrompt:ev(false;"";false;"";"config:compaction-prompt-not-help-exposed"),
      compactionScope:ev(false;"";false;"";"config:compaction-scope-not-help-exposed"),
      userConfigurationIsolation:ev($userP;"help:ignore-user-config-declaration";$userN;"help:user-config-isolation-explicit-unsupported";"help:user-config-isolation-unverified")
    }' | mana_provider_capabilities_resolve_evidence_map)" || return $?

  # hardSubagentDisable consumes only resolved prerequisite states. In
  # particular, a conflicted multi-agent declaration is unknown here; its raw
  # negative evidence cannot be reopened by the composite.
  hard_derived="$(mana_provider_capabilities_resolve_required_states \
    "$(jq -r '.providerManagedSubagents.status' <<<"$resolved")" \
    "$(jq -r '._multiAgentV2.status' <<<"$resolved")" \
    "$(jq -r '._featureDisableControl.status' <<<"$resolved")" \
    "$(jq -r '.ephemeralSession.status' <<<"$resolved")" \
    "$(jq -r '.userConfigurationIsolation.status' <<<"$resolved")")" || return $?
  case "$hard_derived" in
    supported) hard_derived_evidence='probe:codex-child-features-disable-proven' ;;
    unsupported) hard_derived_evidence='features:hard-disable-negative-evidence' ;;
    unknown) hard_derived_evidence='features:hard-disable-unverified' ;;
  esac
  if [ "$hard_direct_n" = true ]; then
    hard_direct_state="$(jq -nc '{direct:{negativeEvidence:["features:hard-disable-negative-evidence"]}}' |
      mana_provider_capabilities_resolve_evidence_map | jq -r '.direct.status')" || return $?
    hard_record="$(mana_provider_capabilities_composite_record "$hard_derived" "$hard_derived_evidence" \
      "$hard_direct_state" 'features:hard-disable-negative-evidence')" || return $?
  else
    hard_record="$(mana_provider_capabilities_composite_record "$hard_derived" "$hard_derived_evidence")" || return $?
  fi
  jq -c --argjson hard "$hard_record" 'del(._multiAgentV2, ._featureDisableControl) | .hardSubagentDisable=$hard' <<<"$resolved"
}

mana_provider_capabilities_evidence_codex() {
  if mana_provider_capabilities_codex_features_valid "$1/features.txt"; then
    printf '["version:ok","help:root","help:exec","features:list"]\n'
  else
    printf '["version:ok","help:root","help:exec","features:malformed"]\n'
  fi
}
