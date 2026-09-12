#!/usr/bin/env bash

mana_provider_capabilities_probe_opencode() {
  local binary="$1" probe_dir="$2" isolated raw project_config user_config
  isolated="$probe_dir/isolated"
  raw="$probe_dir/config-probe.raw.json"
  project_config="$isolated/project/opencode.json"
  user_config="$isolated/config/opencode/opencode.json"
  "$binary" --version > "$probe_dir/version.txt" 2>/dev/null || {
    mana_provider_capabilities_error 'opencode --version failed'
    return 4
  }
  "$binary" --help > "$probe_dir/root-help.txt" 2>&1 || {
    mana_provider_capabilities_error 'opencode --help failed'
    return 5
  }
  "$binary" run --help > "$probe_dir/run-help.txt" 2>&1 || {
    mana_provider_capabilities_error 'opencode run --help failed'
    return 5
  }
  mkdir -p "$isolated/project" "$isolated/config/opencode"
  printf '%s\n' '{"agent":{"mana_ctx02_user_marker":{"description":"user config survives merge","mode":"primary"},"mana_ctx02_no_children":{"description":"colliding user agent","mode":"primary","permission":{"task":"allow"}}}}' > "$user_config"
  printf '%s\n' '{"agent":{"mana_ctx02_project_marker":{"description":"project config survives merge","mode":"primary"},"mana_ctx02_no_children":{"description":"colliding project agent","mode":"primary","permission":{"task":"allow"}}}}' > "$project_config"
  local content='{"agent":{"mana_ctx02_no_children":{"description":"Mana capability probe root","mode":"primary","permission":{"task":"deny"}},"mana_ctx02_child":{"description":"Mana capability probe child","mode":"subagent","model":"probe/child","permission":{"task":"deny"}}}}'
  if (cd "$isolated/project" && XDG_DATA_HOME="$isolated/data" XDG_STATE_HOME="$isolated/state" XDG_CACHE_HOME="$isolated/cache" XDG_CONFIG_HOME="$isolated/config" OPENCODE_CONFIG_CONTENT="$content" "$binary" debug config --pure) > "$raw" 2>/dev/null; then
    jq -e '
      (.agent.mana_ctx02_no_children.permission.task == "deny") and
      (.agent.mana_ctx02_child.permission.task == "deny") and
      (.agent.mana_ctx02_child.model == "probe/child") and
      (.agent.mana_ctx02_user_marker.description == "user config survives merge") and
      (.agent.mana_ctx02_project_marker.description == "project config survives merge")
    ' "$raw" >/dev/null 2>&1 &&
      printf '%s\n' '{"probeStatus":"ok","rootTaskDeny":true,"childTaskDeny":true,"childModelConfigured":true,"userConfigLoaded":true,"projectConfigLoaded":true,"nonConflictingConfigPreserved":true,"inlineCollisionResolvedToDeny":true}' > "$probe_dir/config-probe.json" ||
      printf '%s\n' '{"probeStatus":"malformed","rootTaskDeny":false,"childTaskDeny":false,"childModelConfigured":false,"userConfigLoaded":false,"projectConfigLoaded":false,"nonConflictingConfigPreserved":false,"inlineCollisionResolvedToDeny":false}' > "$probe_dir/config-probe.json"
  else
    rm -f "$raw"
    rm -rf "$isolated"
    mana_provider_capabilities_error 'opencode config probe failed'
    return 5
  fi
  rm -f "$raw"
  rm -rf "$isolated"
}

mana_provider_capabilities_validate_opencode_fixture() {
  local fixture="$1"
  mana_provider_capabilities_validate_fixture_files "$fixture" version.txt root-help.txt run-help.txt config-probe.json || return $?
  jq -e '
    type == "object" and
    (.probeStatus == "ok" or .probeStatus == "failed" or .probeStatus == "malformed") and
    (.rootTaskDeny | type == "boolean") and
    (.childTaskDeny | type == "boolean") and
    (.childModelConfigured | type == "boolean") and
    (.userConfigLoaded | type == "boolean") and
    (.projectConfigLoaded | type == "boolean") and
    (.nonConflictingConfigPreserved | type == "boolean") and
    (.inlineCollisionResolvedToDeny | type == "boolean") and
    (if .probeStatus == "ok" then
       .rootTaskDeny and
       .childTaskDeny and
       .childModelConfigured and
       .userConfigLoaded and
       .projectConfigLoaded and
       .nonConflictingConfigPreserved and
       .inlineCollisionResolvedToDeny
     else
       ((.rootTaskDeny or .childTaskDeny or .childModelConfigured or
         .userConfigLoaded or .projectConfigLoaded or
         .nonConflictingConfigPreserved or
         .inlineCollisionResolvedToDeny) | not)
     end)
  ' "$fixture/config-probe.json" >/dev/null 2>&1 || {
    mana_provider_capabilities_error 'capability fixture is malformed: semantically invalid config-probe.json'
    return 2
  }
}

mana_provider_capabilities_opencode_config_probe_complete() {
  jq -e '
    .probeStatus == "ok" and
    .rootTaskDeny == true and
    .childTaskDeny == true and
    .childModelConfigured == true and
    .userConfigLoaded == true and
    .projectConfigLoaded == true and
    .nonConflictingConfigPreserved == true and
    .inlineCollisionResolvedToDeny == true
  ' "$1" >/dev/null 2>&1
}

mana_provider_capabilities_opencode_help_valid() {
  local file="$1" surface="$2"
  awk -v surface="$surface" '
    surface == "root" && $0 == "Commands:" { commands=1 }
    surface == "root" && $0 ~ /^  opencode run \[message\.\.\][[:space:]]+run opencode with a message[[:space:]]*$/ { title=1 }
    surface == "run" && $0 == "opencode run [message..]" { command=1 }
    surface == "run" && $0 == "run opencode with a message" { title=1 }
    $0 == "Options:" { options=1 }
    END { exit(title && options && (surface != "root" || commands) && (surface != "run" || command) ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_opencode_option_proven() {
  local file="$1" option="$2"
  awk -v option="$option" '
    option == "format" && $0 ~ /^[[:space:]]+--format[[:space:]]+format: default \(formatted\) or json \(raw JSON events\)[[:space:]]*$/ { declaration=1; next }
    option == "format" && declaration && $0 ~ /^[[:space:]]+\[string\] \[choices: "default", "json"\] \[default: "default"\][[:space:]]*$/ { found=1 }
    option == "model" && $0 ~ /^[[:space:]]+-m, --model[[:space:]]+model to use in the format of provider\/model[[:space:]]+\[string\][[:space:]]*$/ { found=1 }
    option == "variant" && $0 ~ /^[[:space:]]+--variant[[:space:]]+model variant \(provider-specific reasoning effort, e\.g\., high, max, minimal\)[[:space:]]*$/ { declaration=1; next }
    option == "variant" && declaration && $0 ~ /^[[:space:]]+\[string\][[:space:]]*$/ { found=1 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_opencode_explicitly_unsupported() {
  local file="$1" capability="$2"
  awk -v capability="$capability" '
    $0 == "OpenCode capability status:" { section=1; next }
    section && $0 == "  " capability " unsupported" { found=1 }
    section && $0 !~ /^  [a-z0-9-]+ (supported|unsupported)$/ { section=0 }
    END { exit(found ? 0 : 1) }
  ' "$file"
}

mana_provider_capabilities_render_opencode() {
  local probe_dir run_help config
  probe_dir="$1"
  run_help="$probe_dir/run-help.txt"
  config="$probe_dir/config-probe.json"
  local stream_p=false stream_n=false final_p=false final_n=false schema_p=false schema_n=false
  local fresh_p=false fresh_n=false model_p=false model_n=false effort_p=false effort_n=false
  local subagents_p=false subagents_n=false
  if mana_provider_capabilities_opencode_help_valid "$run_help" run; then
    mana_provider_capabilities_opencode_option_proven "$run_help" format && stream_p=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" structured-event-stream && stream_n=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" separate-final-output-file && final_n=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" structured-output-schema && schema_n=true
    fresh_p=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" fresh-invocation && fresh_n=true
    mana_provider_capabilities_opencode_option_proven "$run_help" model && model_p=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" explicit-model-selection && model_n=true
    mana_provider_capabilities_opencode_option_proven "$run_help" variant && effort_p=true
    mana_provider_capabilities_opencode_explicitly_unsupported "$run_help" explicit-reasoning-effort && effort_n=true
  fi
  if mana_provider_capabilities_opencode_config_probe_complete "$config"; then
    subagents_p=true
  fi
  jq -n \
    --argjson streamP "$stream_p" --argjson streamN "$stream_n" --argjson finalP "$final_p" --argjson finalN "$final_n" \
    --argjson schemaP "$schema_p" --argjson schemaN "$schema_n" --argjson freshP "$fresh_p" --argjson freshN "$fresh_n" \
    --argjson modelP "$model_p" --argjson modelN "$model_n" --argjson effortP "$effort_p" --argjson effortN "$effort_n" \
    --argjson subagentsP "$subagents_p" --argjson subagentsN "$subagents_n" '
    def ev($p;$pe;$n;$ne;$ue): {
      positiveEvidence:(if $p then [$pe] else [] end),
      negativeEvidence:(if $n then [$ne] else [] end),
      unknownEvidence:[$ue]
    };
    {
      structuredEventStream:ev($streamP;"help:run-format-json-declaration";$streamN;"help:structured-event-stream-explicit-unsupported";"help:json-format-unverified"),
      separateFinalOutputFile:ev($finalP;"help:final-output-file-declaration";$finalN;"help:final-output-file-explicit-unsupported";"help:final-output-file-unverified"),
      structuredOutputSchema:ev($schemaP;"help:structured-schema-declaration";$schemaN;"help:structured-schema-explicit-unsupported";"help:structured-schema-unverified"),
      freshInvocation:ev($freshP;"help:run-command-declaration";$freshN;"help:fresh-invocation-explicit-unsupported";"help:run-command-unverified"),
      ephemeralSession:ev(false;"";false;"";"probe:session-persistence-not-observable"),
      explicitModelSelection:ev($modelP;"help:model-declaration";$modelN;"help:model-explicit-unsupported";"help:model-unverified"),
      explicitReasoningEffort:ev($effortP;"help:variant-reasoning-declaration";$effortN;"help:variant-explicit-unsupported";"help:variant-unverified"),
      managedChildExecutionAttestation:ev(false;"";false;"";"probe:provider-native-child-attestation-not-observable"),
      providerManagedSubagents:ev($subagentsP;"config:agent-configuration-surface";$subagentsN;"config:agent-configuration-explicit-unsupported";"config:agent-probe-unavailable"),
      hardSubagentDisable:ev(false;"";false;"";"config:task-deny-does-not-prove-isolation"),
      childContextInheritanceControl:ev(false;"";false;"";"probe:child-context-not-observable"),
      childModelRouting:ev(false;"";false;"";"probe:child-model-not-runtime-verified"),
      childReasoningEffortRouting:ev(false;"";false;"";"probe:child-effort-not-runtime-verified"),
      recursiveDelegationPrevention:ev(false;"";false;"";"config:task-deny-not-runtime-verified"),
      maximumChildConcurrency:ev(false;"";false;"";"config:child-concurrency-not-exposed"),
      maximumChildDepth:ev(false;"";false;"";"config:child-depth-not-exposed"),
      toolOutputRetentionTokenLimit:ev(false;"";false;"";"config:tool-output-limit-not-exposed"),
      automaticCompactionThreshold:ev(false;"";false;"";"probe:compaction-threshold-not-observable"),
      customCompactionPrompt:ev(false;"";false;"";"probe:custom-compaction-prompt-not-observable"),
      compactionScope:ev(false;"";false;"";"probe:compaction-scope-not-observable"),
      userConfigurationIsolation:ev(false;"";false;"";"help:pure-does-not-claim-full-config-isolation")
    }' | mana_provider_capabilities_resolve_evidence_map
}

mana_provider_capabilities_evidence_opencode() {
  local status
  status="$(jq -r '.probeStatus' "$1/config-probe.json")"
  printf '["version:ok","help:root","help:run","config:%s"]\n' "$status"
}
