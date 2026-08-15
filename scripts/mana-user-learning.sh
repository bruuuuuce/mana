#!/usr/bin/env bash
# External, deterministic capture of explicit governed developer decisions.
# This is intentionally separate from project-local mana-learning.sh.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
command=""
json=false
dry_run=false
force=false
review_action=""
review_edit=""
review_scope=""
override_rejected=false
positionals=()
. "$root/scripts/lib/json.sh"
. "$root/scripts/lib/run-identity.sh"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/user-context.sh"

usage() {
  cat <<'USAGE' >&2
Usage: mana user-learning capture [--json]
       mana user-learning aggregate [--json]
       mana user-learning synthesize [--dry-run] [--force] [--json]
       mana user-learning candidates [--json]
       mana user-learning show <candidate-id> [--json]
       mana user-learning review <candidate-id> (--accept|--edit <guidance>|--reject|--defer) [--scope <scope>] [--override-rejected] [--json]
       mana user-learning promote <review-id> [--dry-run] [--json]

Captures eligible confirmed Developer Choice Log rows into host-owned User
Learning state. This command never invokes a model, changes project-local
learning, or writes User Context.

`aggregate` deterministically materializes cross-project recurring evidence
clusters from external UserChoiceSignal records. It never infers preferences.

`synthesize` performs at most one bounded T1 model invocation per eligible
semantic unit. It produces proposals only; it never writes User Context.

`review` records an explicit human decision. `promote` is the separate,
explicit command that may publish an accepted review to external User Context.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 2; }
sha256() {
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  else
    fail 'shasum or sha256sum is required for stable User Learning identities'
  fi
}
file_sha256() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    fail 'shasum or sha256sum is required for stable User Learning identities'
  fi
}
now() { mana_generated_at; }

state_root() {
  local base
  if [ -n "${MANA_USER_STATE_HOME:-}" ]; then base="$MANA_USER_STATE_HOME"
  elif [ -n "${XDG_STATE_HOME:-}" ]; then base="$XDG_STATE_HOME/mana"
  elif [ -n "${HOME:-}" ]; then base="$HOME/.local/state/mana"
  else fail 'MANA_USER_STATE_HOME, XDG_STATE_HOME, or HOME must provide an absolute User Learning state location'; fi
  case "$base" in /*) printf '%s' "$base";; *) fail 'User Learning state location must be absolute';; esac
}

validate_signal() {
  local file="$1" expected_id="${2:-}"
  mana_json_valid_object "$file" && jq -e '
    .schemaVersion == "2" and
    (.signalId | type == "string" and test("^user-choice-[0-9a-f]{64}$")) and
    ($expected == "" or .signalId == $expected) and
    (.sourceProject | type == "object" and (.projectId | type == "string")) and
    (.sourceDecision | type == "object" and (.reference | type == "string") and (.choiceOrdinal | type == "number" and . >= 1) and (.status == "confirmed") and (.subject | type == "string") and (.confirmedChoice | type == "string")) and
    (.provenance | type == "object" and (.sourceType == "developer-choice-log") and (.sourceArtifact | type == "object")) and
    (.capture | type == "object" and (.processor == "deterministic-developer-choice-log-v1") and (.modelCalls == 0))
  ' --arg expected "$expected_id" "$file" >/dev/null || fail "malformed stored UserChoiceSignal: $file"
}

# Emits one unit-separator-delimited record per standard Choices-table row.
# The choice ordinal is the stable decision identity within its canonical log;
# source lines remain diagnostic only. Malformed rows have only kind, path, and
# source line and are reported as skipped. The non-whitespace delimiter
# preserves empty Markdown cells.
extract_rows() {
  local file="$1" rel="$2"
  awk -v path="$rel" '
    BEGIN { FS="|"; sep=sprintf("%c", 28) }
    function trim(value) { sub(/^[[:space:]]+/, "", value); sub(/[[:space:]]+$/, "", value); return value }
    function header() { return $2 == "Date" && $3 == "Story" && $4 == "Area" && $5 == "Question Or Choice" && $6 == "Developer Answer" && $7 == "Evidence" && $8 == "Confirmed By" && $9 == "Status" && $10 == "Follow-Up" }
    /^##[[:space:]]/ { in_choices=0 }
    /^\|/ {
      separator=($0 ~ /^\|[[:space:]|:-]+\|[[:space:]]*$/)
      for (i=2; i<NF; i++) $i=trim($i)
      if (NF == 11 && header()) { in_choices=1; next }
      if (!in_choices || separator) next
      if (NF != 11 || $0 ~ /\t/) { print "malformed" sep path sep NR; next }
      for (i=2; i<=10; i++) if ($i ~ /[\t\r\n\034]/) { print "malformed" sep path sep NR; next }
      choice_ordinal++
      printf "row%s%s%s%d%s%d", sep, path, sep, NR, sep, choice_ordinal
      for (i=2; i<=10; i++) printf "%s%s", sep, $i
      printf "\n"
    }
  ' "$file"
}

write_signal() {
  local file="$1" payload="$2" tmp
  [ ! -e "$file" ] || return 1
  tmp="$(mktemp "$(dirname "$file")/.${file##*/}.tmp.XXXXXX")" || fail 'could not create User Learning staging file'
  umask 077
  printf '%s\n' "$payload" > "$tmp" || { rm -f "$tmp"; fail 'could not write UserChoiceSignal'; }
  mv "$tmp" "$file" || { rm -f "$tmp"; fail 'could not publish UserChoiceSignal'; }
}

m2_add_skip() {
  local file="$1" reason="$2"
  jq -cn --arg path "${file#"$signals_dir"/}" --arg reason "$reason" '{path:$path,reason:$reason}' >> "$aggregation_skips_file"
}

m2_valid_signal() {
  jq -e '
    def only($allowed): (keys - $allowed | length) == 0;
    type == "object" and only(["schemaVersion","signalId","sourceProject","sourceDecision","provenance","capture"]) and .schemaVersion == "2" and
    (.signalId | type == "string" and test("^user-choice-[0-9a-f]{64}$")) and
    (.sourceProject | type == "object" and only(["projectId","repositoryRoot"]) and (.projectId | type == "string" and test("^project-[0-9a-f]{64}$")) and (.repositoryRoot | type == "string" and startswith("/"))) and
    (.sourceDecision | type == "object" and only(["reference","logPath","line","choiceOrdinal","status","subject","confirmedChoice","confirmedBy","decisionDate","story","area"]) and (.reference | type == "string") and (.logPath | type == "string" and startswith(".mana/")) and (.line | type == "number" and floor == . and . >= 1) and (.choiceOrdinal | type == "number" and floor == . and . >= 1) and (.status == "confirmed") and (.subject | type == "string" and length > 0) and (.confirmedChoice | type == "string" and length > 0) and (.confirmedBy | type == "string" and length > 0) and (if has("decisionDate") then (.decisionDate | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")) else true end) and (if has("story") then (.story | type == "string" and length > 0) else true end) and (if has("area") then (.area | type == "string" and length > 0) else true end)) and
    (.provenance | type == "object" and only(["sourceType","sourceArtifact","evidence","followUp"]) and (.sourceType == "developer-choice-log") and (.sourceArtifact | type == "object" and only(["path","sha256"]) and (.path | type == "string" and startswith(".mana/")) and (.sha256 | type == "string" and test("^[0-9a-f]{64}$"))) and (.evidence | type == "array" and length <= 1 and all(.[]; type == "string" and length > 0)) and (if has("followUp") then (.followUp | type == "string" and length > 0) else true end)) and
    (.capture | type == "object" and only(["processor","modelCalls","capturedAt"]) and (.processor == "deterministic-developer-choice-log-v1") and (.modelCalls == 0) and (.capturedAt | type == "string"))
  ' "$1" >/dev/null 2>&1
}

m2_normalized_signal() {
  jq -ce '
    def normalize: gsub("\\r\\n"; "\\n") | gsub("\\r"; "\\n") | gsub("^[[:space:]]+"; "") | gsub("[[:space:]]+$"; "") | gsub("[[:space:]]+"; " ");
    {signalId, projectId:.sourceProject.projectId, normalizedSubject:(.sourceDecision.subject | normalize), normalizedConfirmedChoice:(.sourceDecision.confirmedChoice | normalize)}
    | select(.normalizedSubject != "" and .normalizedConfirmedChoice != "")
  ' "$1"
}

# M3 uses a bounded T1 synthesis contract. Values are configurable downward;
# hard caps prevent a configuration change from creating an unbounded runner.
m3_init_limits() {
  m3_max_clusters="${MANA_USER_LEARNING_MAX_CLUSTERS_PER_UNIT:-8}"; m3_max_signals="${MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER:-3}"
  # This is deliberately an estimate, not a provider tokenizer guarantee.
  # The independently configured byte limit below is the actual host gate.
  m3_max_input_tokens="${MANA_USER_LEARNING_MAX_INPUT_TOKENS:-3600}"; m3_max_input_bytes="${MANA_USER_LEARNING_MAX_INPUT_BYTES:-12000}"; m3_max_output_tokens="${MANA_USER_LEARNING_MAX_OUTPUT_TOKENS:-500}"
  m3_max_units="${MANA_USER_LEARNING_MAX_SYNTHESIS_UNITS:-32}"; m3_timeout_seconds="${MANA_USER_LEARNING_SYNTHESIS_TIMEOUT_SECONDS:-120}"
  for value in "$m3_max_clusters" "$m3_max_signals" "$m3_max_input_tokens" "$m3_max_input_bytes" "$m3_max_output_tokens" "$m3_max_units" "$m3_timeout_seconds"; do [[ "$value" =~ ^[1-9][0-9]*$ ]] || fail 'M3 limits must be positive integers'; done
  [ "$m3_max_clusters" -le 8 ] || fail 'M3 max clusters per unit hard limit is 8'; [ "$m3_max_signals" -le 4 ] || fail 'M3 max supporting signals per cluster hard limit is 4'
  [ "$m3_max_input_tokens" -le 4000 ] || fail 'M3 max estimated input tokens hard limit is 4000'; [ "$m3_max_input_bytes" -le 16000 ] || fail 'M3 max serialized input bytes hard limit is 16000'; [ "$m3_max_output_tokens" -le 600 ] || fail 'M3 max output tokens hard limit is 600'
  [ "$m3_max_units" -le 64 ] || fail 'M3 max synthesis units hard limit is 64'; [ "$m3_timeout_seconds" -le 300 ] || fail 'M3 synthesis timeout hard limit is 300 seconds'
  m3_max_output_bytes=$((m3_max_output_tokens * 4)); m3_provider="${MANA_USER_LEARNING_T1_PROVIDER:-codex}"; m3_codex_reasoning_effort="${MANA_USER_LEARNING_CODEX_REASONING_EFFORT:-}"
  case "$m3_codex_reasoning_effort" in ''|minimal|low|medium|high|xhigh) ;; *) fail 'M3 Codex reasoning effort must be minimal, low, medium, high, or xhigh' ;; esac
  case "$m3_provider" in
    codex) m3_model="${MANA_USER_LEARNING_T1_MODEL:-${MANA_CODEX_MODEL:-gpt-5.4-mini}}" ;;
    claude) m3_model="${MANA_USER_LEARNING_T1_MODEL:-${MANA_CLAUDE_MODEL:-haiku}}" ;;
    opencode) m3_model="${MANA_USER_LEARNING_T1_MODEL:-${MANA_OPENCODE_MODEL:-opencode/gpt-5.1-codex}}" ;;
    stub) m3_model="${MANA_USER_LEARNING_T1_MODEL:-deterministic-stub}" ;;
    *) fail 'M3 T1 provider must be codex, claude, opencode, or explicit test stub' ;;
  esac
}

# A stable character-based planning estimate. It intentionally does not claim
# to match any selected provider's tokenizer; serialized bytes are enforced.
m3_estimate_tokens() { local bytes="$1"; printf '%s' "$(( (bytes + 3) / 4 ))"; }

# Transport diagnostics are returned only for failed provider executions. Keep
# them bounded and redact the credential forms used by verification evidence.
m3_redact_provider_diagnostic() {
  awk '/-----BEGIN .*PRIVATE KEY-----/ { print "[REDACTED PRIVATE KEY]"; private_key=1; next } /-----END .*PRIVATE KEY-----/ { private_key=0; next } !private_key { print }' | sed -E \
    -e 's/((PASSWORD|TOKEN|SECRET|API[_-]?KEY|AWS_SECRET_ACCESS_KEY)[[:space:]]*[:=][[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/(Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/(X-API-Key:[[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's#(://[^:/[:space:]]+:)[^@/[:space:]]+@#\1[REDACTED]@#g'
}

m3_add_provider_failure_diagnostic() {
  local stderr_file exit_code signal timed_out descendants stderr_bytes stderr_truncated reason diagnostic
  stderr_file="$1"; exit_code="$2"; signal="$3"; timed_out="$4"; descendants="$5"; stderr_bytes="$6"; stderr_truncated="$7"; reason="$8"
  if [ -n "$stderr_file" ] && [ -f "$stderr_file" ]; then
    diagnostic="$(LC_ALL=C head -c 4096 "$stderr_file" | m3_redact_provider_diagnostic)"
  else
    diagnostic=""
  fi
  provider_failure_diagnostics="$(jq -cn --argjson existing "$provider_failure_diagnostics" --arg provider "$m3_provider" --arg model "$m3_model" --argjson exitCode "$exit_code" --argjson signal "$signal" --argjson timedOut "$timed_out" --argjson descendantsTerminated "$descendants" --argjson stderrBytes "$stderr_bytes" --argjson stderrTruncated "$stderr_truncated" --arg stderr "$diagnostic" --arg reason "$reason" '$existing + [{provider:$provider,model:$model,exitCode:$exitCode,signal:$signal,timedOut:$timedOut,descendantsTerminated:$descendantsTerminated,stderrBytes:$stderrBytes,stderrTruncated:$stderrTruncated,stderr:$stderr} + (if $reason == "" then {} else {reason:$reason} end)]')"
}

m3_build_package() {
  local unit="$1" selected_signals="$2"
  jq -cn --arg version 'm3-bounded-semantic-synthesis-v1' --argjson maxClusters "$m3_max_clusters" --argjson maxSignals "$selected_signals" --argjson maxInput "$m3_max_input_tokens" --argjson maxBytes "$m3_max_input_bytes" --argjson maxOutput "$m3_max_output_tokens" --argjson unit "$unit" --slurpfile signals "$m3_scratch/signals.json" '
    def clip($n): if length>$n then .[0:$n] else . end; ($signals[0]|map({key:.signalId,value:.})|from_entries) as $signalMap |
    {contractVersion:$version,modelTier:"T1",budgets:{maxEvidenceClusters:$maxClusters,maxSupportingSignalsPerCluster:$maxSignals,estimatedInputTokensBudget:$maxInput,hardSerializedInputBytes:$maxBytes,maxOutputTokens:$maxOutput},preselectionKey:$unit.unitKey,evidenceFamilies:[$unit.clusters[]|{clusterId,aggregationKey,occurrenceCount,distinctProjectCount,supportingProjectIds,alternativeConfirmedEvidence:[],supportingSignals:[.supportingSignalIds[0:$maxSignals][] as $id|$signalMap[$id]|{signalId,projectId:.sourceProject.projectId,subject:(.sourceDecision.subject|clip(120)),confirmedChoice:(.sourceDecision.confirmedChoice|clip(120)),area:(.sourceDecision.area // ""|clip(80)),evidence:(.provenance.evidence[0] // ""|clip(160))}]}]}
  '
}

m3_valid_cluster() {
  jq -e '
    def only($allowed): (keys - $allowed | length) == 0;
    type == "object" and only(["schemaVersion","clusterId","aggregationKey","supportingSignalIds","supportingProjectIds","occurrenceCount","distinctProjectCount","alternativeConfirmedEvidence","derivation"]) and .schemaVersion == "1" and (.clusterId|type == "string" and test("^cluster-[0-9a-f]{64}$")) and
    (.aggregationKey|type == "object" and .aggregationVersion == "1" and (.normalizedSubject|type == "string" and length > 0) and (.normalizedConfirmedChoice|type == "string" and length > 0)) and
    (.supportingSignalIds|type == "array" and length > 0 and all(.[]; type == "string" and test("^user-choice-[0-9a-f]{64}$"))) and
    (.supportingProjectIds|type == "array" and length > 0 and all(.[]; type == "string" and test("^project-[0-9a-f]{64}$"))) and
    (.occurrenceCount|type == "number" and floor == . and . >= 1) and (.distinctProjectCount|type == "number" and floor == . and . >= 1) and
    (.derivation|type == "object" and .processor == "deterministic-user-learning-aggregation-v1" and .modelCalls == 0)
  ' "$1" >/dev/null 2>&1
}

m3_write_json() {
  local file="$1" payload="$2" tmp
  [ ! -L "$file" ] || fail "unsafe M3 state symlink: $file"; mkdir -p "$(dirname "$file")" || fail 'could not create M3 state directory'
  tmp="$(mktemp "$(dirname "$file")/.${file##*/}.tmp.XXXXXX")" || fail 'could not create M3 staging file'; umask 077
  printf '%s\n' "$payload" > "$tmp" || { rm -f "$tmp"; fail 'could not write M3 state'; }
  case "$file" in */candidates/*.json) m3_candidate_valid "$tmp" || { rm -f "$tmp"; fail 'constructed UserContextCandidate failed validation'; };; esac
  mv "$tmp" "$file" || { rm -f "$tmp"; fail 'could not publish M3 state'; }
}

m3_prompt() {
  local package="$1"
  cat <<'CONTRACT'
Use only supplied evidence/IDs; one JSON object, no Markdown. Do not infer personality/motive, inspect other data, alter User Context, invent/hide evidence, or generalize.
Each confirmedChoice is an explicit developer choice. If all support is fully explained by external requirements (customer/platform, compatibility, legal/compliance, or another non-discretionary dependency), MUST return NO_CANDIDATE. Evidence must identify that outside source/dependency; "must" alone may state rationale. Never turn "X required" into "use X when required." In mixed evidence, use only discretionary support.
CANDIDATE needs a common justified discretionary judgment. Different implementations may support one higher-level principle when rationales converge. Return NO_CANDIDATE for no common judgment or events only.
Return one flat transport object; all fields required, arrays for limitations/IDs. CANDIDATE: reason "", scope "unspecified" unless explicit. NO_CANDIDATE: guidance/scope/rationale "", limitations [].
CONTRACT
  printf '\nBOUNDED_EVIDENCE_PACKAGE\n%s\n' "$package"
}

m3_output_valid() {
  local output="$1" clusters="$2" signals="$3"
  jq -e --argjson clusters "$clusters" --argjson signals "$signals" '
    def only($allowed): (keys - $allowed | length) == 0;
    def provenance_set($items; $minimum; $maximum):
      type == "array" and length >= $minimum and length <= $maximum and
      all(.[]; type == "string") and length == (unique | length) and
      all(.[]; . as $id | $items | index($id) != null);
    type == "object" and if .result == "CANDIDATE" then
      only(["result","guidance","scope","rationale","limitations","relatedClusterIds","supportingSignalIds"]) and (.guidance|type == "string" and length > 0 and length <= 600) and (.scope|type == "string" and length > 0 and length <= 120) and (.rationale|type == "string" and length > 0 and length <= 900) and (.limitations|type == "array" and length <= 6 and all(.[]; type == "string" and length > 0 and length <= 240)) and (.relatedClusterIds|provenance_set($clusters; 1; 8)) and (.supportingSignalIds|provenance_set($signals; 2; 32))
    elif .result == "NO_CANDIDATE" then
      only(["result","reason","relatedClusterIds","supportingSignalIds"]) and (.reason|type == "string" and length > 0 and length <= 900) and (.relatedClusterIds|provenance_set($clusters; 1; 8)) and (.supportingSignalIds|provenance_set($signals; 2; 32))
    else false end
  ' "$output" >/dev/null 2>&1
}

m3_canonicalize_provenance() {
  jq -ce '.relatedClusterIds |= sort | .supportingSignalIds |= sort' "$1"
}

# Codex's native output-schema subset requires one object shape rather than
# the domain contract's discriminated result variants. This adapter is only
# used for that provider transport: non-empty inapplicable fields are rejected
# before the existing host-owned domain validator sees a canonical result.
m3_codex_transport_to_domain() {
  local output="$1"
  jq -ce '
    def only($allowed): (keys - $allowed | length) == 0;
    def flat: only(["result","guidance","scope","rationale","reason","limitations","relatedClusterIds","supportingSignalIds"])
      and (["result","guidance","scope","rationale","reason","limitations","relatedClusterIds","supportingSignalIds"] - keys | length) == 0
      and (.result|type == "string") and (.guidance|type == "string") and (.scope|type == "string")
      and (.rationale|type == "string") and (.reason|type == "string") and (.limitations|type == "array")
      and (.relatedClusterIds|type == "array") and (.supportingSignalIds|type == "array");
    if flat and .result == "CANDIDATE" then
      if .reason == "" then del(.reason) else error("CANDIDATE reason must be empty") end
    elif flat and .result == "NO_CANDIDATE" then
      if .guidance == "" and .scope == "" and .rationale == "" and .limitations == [] then del(.guidance,.scope,.rationale,.limitations)
      else error("NO_CANDIDATE candidate fields must be empty") end
    else error("invalid flat M3 transport") end
  ' "$output"
}

# This is deliberately diagnostic-only.  Acceptance remains m3_output_valid;
# these stable paths let a live harness distinguish bad JSON from a rejected
# M3 contract without attempting to repair provider output.
m3_output_validation_diagnostic() {
  local output="$1" clusters="$2" signals="$3"
  if ! jq -e 'type == "object"' "$output" >/dev/null 2>&1; then
    jq -cn '{valid:false,error:"malformed_json_or_non_object",path:"$"}'; return
  fi
  if m3_output_valid "$output" "$clusters" "$signals"; then jq -cn '{valid:true}'; return; fi
  jq -cn --argjson value "$(cat "$output")" --argjson clusters "$clusters" --argjson signals "$signals" '
    def failure($error; $path): {valid:false,error:$error,path:$path};
    if ($value.result|type) != "string" then failure("missing_or_invalid_result";".result")
    elif ($value.result != "CANDIDATE" and $value.result != "NO_CANDIDATE") then failure("result_enum_mismatch";".result")
    elif $value.result == "CANDIDATE" and (($value|keys)-["result","guidance","scope","rationale","limitations","relatedClusterIds","supportingSignalIds"]|length)>0 then failure("unknown_field";"$")
    elif $value.result == "NO_CANDIDATE" and (($value|keys)-["result","reason","relatedClusterIds","supportingSignalIds"]|length)>0 then failure("unknown_field";"$")
    elif $value.result == "CANDIDATE" and ([$value.guidance,$value.scope,$value.rationale,$value.limitations,$value.relatedClusterIds,$value.supportingSignalIds]|any(. == null)) then failure("missing_required_field";"$")
    elif $value.result == "NO_CANDIDATE" and ([$value.reason,$value.relatedClusterIds,$value.supportingSignalIds]|any(. == null)) then failure("missing_required_field";"$")
    elif $value.result == "CANDIDATE" and ($value.limitations|type) != "array" then failure("invalid_field_type";".limitations")
    elif $value.result == "CANDIDATE" and (($value.guidance|type) != "string" or ($value.scope|type) != "string" or ($value.rationale|type) != "string") then failure("invalid_field_type";".guidance/.scope/.rationale")
    elif $value.result == "NO_CANDIDATE" and ($value.reason|type) != "string" then failure("invalid_field_type";".reason")
    elif ($value.relatedClusterIds|type) != "array" then failure("invalid_related_cluster_ids";".relatedClusterIds")
    elif ($value.relatedClusterIds|any(.[]; type != "string")) then failure("non_string_cluster_id";".relatedClusterIds")
    elif ($value.relatedClusterIds|length) < 1 or ($value.relatedClusterIds|length) > 8 then failure("related_cluster_ids_cardinality";".relatedClusterIds")
    elif ($value.relatedClusterIds|length) != ($value.relatedClusterIds|unique|length) then failure("duplicate_cluster_id";".relatedClusterIds")
    elif (($value.relatedClusterIds - $clusters)|length)>0 then failure("fabricated_or_unexposed_cluster_id";".relatedClusterIds")
    elif ($value.supportingSignalIds|type) != "array" then failure("invalid_supporting_signal_ids";".supportingSignalIds")
    elif ($value.supportingSignalIds|any(.[]; type != "string")) then failure("non_string_signal_id";".supportingSignalIds")
    elif ($value.supportingSignalIds|length) < 2 or ($value.supportingSignalIds|length) > 32 then failure("supporting_signal_ids_cardinality";".supportingSignalIds")
    elif ($value.supportingSignalIds|length) != ($value.supportingSignalIds|unique|length) then failure("duplicate_signal_id";".supportingSignalIds")
    elif (($value.supportingSignalIds - $signals)|length)>0 then failure("fabricated_or_unexposed_signal_id";".supportingSignalIds")
    else failure("structured_contract_validation_failed";"$") end'
}

m3_write_diagnostic() {
  # Opt-in only: live tests provide a disposable directory.  Nothing is
  # retained in normal user state, and all captured transport data is capped.
  local unit="$1" eligibility="$2" skip_reason="$3" package="$4" input_bytes="$5" input_tokens="$6" invocations="$7" stdout_file="$8" stderr_file="$9" validation="${10}" accepted="${11:-}"
  local dir="${MANA_USER_LEARNING_DIAGNOSTICS_DIR:-}" stdout='' stderr='' raw=''
  [ -n "$dir" ] || return 0
  case "$dir" in /*) ;; *) fail 'M3 diagnostic directory must be absolute';; esac
  mkdir -p "$dir" || fail 'could not create M3 diagnostic directory'
  [ -n "$stdout_file" ] && [ -f "$stdout_file" ] && { raw="$(LC_ALL=C head -c "$m3_max_output_bytes" "$stdout_file")"; stdout="$raw"; }
  [ -n "$stderr_file" ] && [ -f "$stderr_file" ] && stderr="$(LC_ALL=C head -c 4096 "$stderr_file" | m3_redact_provider_diagnostic)"
  jq -cn --argjson unit "$unit" --arg eligibility "$eligibility" --arg skip "$skip_reason" --argjson package "${package:-null}" --argjson bytes "$input_bytes" --argjson tokens "$input_tokens" --argjson calls "$invocations" --arg stdout "$stdout" --arg stderr "$stderr" --arg raw "$raw" --argjson validation "$validation" --argjson accepted "${accepted:-null}" '{scenario:(env.MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO // "unspecified"),unit:$unit,deterministicEligibility:$eligibility,skipReason:(if $skip=="" then null else $skip end),sourceClusterIds:($unit.clusters|map(.clusterId)),sourceSignalCounts:($unit.clusters|map({clusterId,signalCount:(.supportingSignalIds|length)})),distinctProjectCounts:($unit.clusters|map({clusterId,distinctProjectCount})),semanticInputPackage:$package,serializedInputBytes:$bytes,estimatedInputTokens:$tokens,providerInvocationCount:$calls,boundedProviderStdout:$stdout,boundedRedactedProviderStderr:$stderr,rawBoundedModelResult:$raw,structuredOutputValidation:$validation,acceptedResult:$accepted}' > "$dir/unit-$(jq -r '.unitKey' <<<"$unit" | shasum -a 256 | awk '{print $1}').json"
}

m3_candidate_valid() {
  jq -e '
    def only($allowed): (keys - $allowed | length) == 0;
    type == "object" and only(["schemaVersion","kind","candidateId","synthesisVersion","lifecycleState","guidance","scope","sourceClusterIds","supportingSignalIds","supportingProjectIds","counterEvidence","synthesis","createdAt","updatedAt"]) and
    .schemaVersion == "1" and .kind == "user-context-candidate" and (.candidateId|type == "string" and test("^user-context-candidate-[0-9a-f]{64}$")) and .synthesisVersion == "m3-bounded-semantic-synthesis-v1" and (.lifecycleState == "proposed" or .lifecycleState == "deferred-for-review") and
    (.guidance|type == "string" and length > 0 and length <= 600) and (.scope|type == "string" and length > 0 and length <= 120) and
    (.sourceClusterIds|type == "array" and length >= 1 and all(.[]; type == "string" and test("^cluster-[0-9a-f]{64}$"))) and (.supportingSignalIds|type == "array" and length >= 2 and all(.[]; type == "string" and test("^user-choice-[0-9a-f]{64}$"))) and (.supportingProjectIds|type == "array" and length >= 1 and all(.[]; type == "string" and test("^project-[0-9a-f]{64}$"))) and
    (.counterEvidence|type == "array") and (.synthesis|type == "object" and (.modelTier == "T1") and (.provider|type == "string") and (.model|type == "string") and (.inputFingerprint|type == "string" and test("^m3-input-[0-9a-f]{64}$")) and (.invocation|type == "object") and (.rationale|type == "string") and (.limitations|type == "array")) and
    (.createdAt|type == "string") and (.updatedAt|type == "string")
  ' "$1" >/dev/null 2>&1
}

# M4 is T0 only. Reviews are immutable audit records; the small status record
# is derived state used only to present the latest explicit disposition.
m4_review_valid() {
  jq -e '
    def only($allowed): (keys - $allowed | length) == 0;
    type == "object" and only(["schemaVersion","kind","reviewId","candidateId","candidateInputFingerprint","action","reviewedGuidance","reviewedScope","reviewedAt","toolVersion","modelCalls"]) and
    .schemaVersion=="1" and .kind=="user-context-candidate-review" and (.reviewId|type=="string" and test("^review-[0-9a-f]{64}$")) and (.candidateId|type=="string" and test("^user-context-candidate-[0-9a-f]{64}$")) and (.candidateInputFingerprint|type=="string" and test("^m3-input-[0-9a-f]{64}$")) and (.action=="ACCEPT" or .action=="EDIT_AND_ACCEPT" or .action=="REJECT" or .action=="DEFER") and
    (if (.action=="ACCEPT" or .action=="EDIT_AND_ACCEPT") then (.reviewedGuidance|type=="string" and length>0 and length<=600) and (.reviewedScope|type=="string" and length>0 and length<=120) else (.reviewedGuidance==null and .reviewedScope==null) end) and
    (.reviewedAt|type=="string") and .toolVersion=="m4-human-review-v1" and .modelCalls==0
  ' "$1" >/dev/null 2>&1
}

m4_status_valid() {
  jq -e '
    type=="object" and (keys|sort)==["action","candidateId","candidateInputFingerprint","reviewId","schemaVersion"] and .schemaVersion=="1" and (.reviewId|type=="string" and test("^review-[0-9a-f]{64}$")) and (.candidateId|type=="string" and test("^user-context-candidate-[0-9a-f]{64}$")) and (.candidateInputFingerprint|type=="string" and test("^m3-input-[0-9a-f]{64}$")) and (.action=="ACCEPT" or .action=="EDIT_AND_ACCEPT" or .action=="REJECT" or .action=="DEFER")
  ' "$1" >/dev/null 2>&1
}

m4_write_json() {
  local file="$1" payload="$2" tmp
  [ ! -L "$file" ] || fail "unsafe M4 state symlink: $file"; mkdir -p "$(dirname "$file")" || fail 'could not create M4 state directory'
  tmp="$(mktemp "$(dirname "$file")/.${file##*/}.tmp.XXXXXX")" || fail 'could not create M4 staging file'; umask 077
  printf '%s\n' "$payload" > "$tmp" || { rm -f "$tmp"; fail 'could not write M4 state'; }
  case "$file" in */reviews/*.json) m4_review_valid "$tmp" || { rm -f "$tmp"; fail 'constructed review failed validation'; };; */review-status/*.json) m4_status_valid "$tmp" || { rm -f "$tmp"; fail 'constructed review status failed validation'; };; esac
  mv "$tmp" "$file" || { rm -f "$tmp"; fail 'could not publish M4 state'; }
}

m4_candidate_file() { printf '%s/user-learning/candidates/%s.json' "$state" "$1"; }
m4_status_file() { printf '%s/user-learning/review-status/%s--%s.json' "$state" "$1" "$2"; }
m4_review_file() { printf '%s/user-learning/reviews/%s.json' "$state" "$1"; }

m4_validate_candidate_evidence() {
  local candidate="$1" cluster signal id
  m3_candidate_valid "$candidate" || return 1
  while IFS= read -r id; do
    cluster="$state/user-learning/clusters/$id.json"; [ -f "$cluster" ] && [ ! -L "$cluster" ] && m3_valid_cluster "$cluster" || return 1
  done < <(jq -r '.sourceClusterIds[]' "$candidate")
  while IFS= read -r id; do
    signal="$signals_dir/$id.json"; [ -f "$signal" ] && [ ! -L "$signal" ] && m2_valid_signal "$signal" || return 1
  done < <(jq -r '.supportingSignalIds[]' "$candidate")
  # Candidate support may only name signals available through its source M2
  # clusters, preserving the M4→M3→M2→M1 provenance chain.
  jq -s --argjson candidate "$(cat "$candidate")" '([.[] | select(.clusterId as $id | $candidate.sourceClusterIds | index($id)) | .supportingSignalIds[]] | unique) as $available | ($candidate.supportingSignalIds - $available | length)==0' "$state/user-learning/clusters"/*.json >/dev/null 2>&1
}

m4_review_status() {
  local candidate="$1" fingerprint="$2" status_file
  status_file="$(m4_status_file "$candidate" "$fingerprint")"
  if [ -f "$status_file" ] && [ ! -L "$status_file" ] && m4_status_valid "$status_file"; then cat "$status_file"; else printf '{"action":"PENDING","reviewId":null}\n'; fi
}

m4_promotion_for_review() {
  local review_id="$1" file
  for file in "$state/user-learning/promotions"/*.json; do
    [ -f "$file" ] && [ ! -L "$file" ] || continue
    jq -e --arg id "$review_id" '.reviewId==$id and (.status=="promoted" or .status=="source_published_refresh_failed")' "$file" >/dev/null 2>&1 && { cat "$file"; return 0; }
  done
  return 1
}

candidates() {
  local candidates_dir="$state/user-learning/candidates" file candidate fp status promoted items='[]'
  [ ! -L "$candidates_dir" ] || fail 'User Learning candidates directory must not be a symlink'
  if [ -d "$candidates_dir" ]; then while IFS= read -r file; do
    m3_candidate_valid "$file" || continue; candidate="$(cat "$file")"; fp="$(jq -r .synthesis.inputFingerprint "$file")"; status="$(m4_review_status "$(jq -r .candidateId "$file")" "$fp")"; promoted=false; m4_promotion_for_review "$(jq -r '.reviewId // empty' <<<"$status")" >/dev/null 2>&1 && promoted=true
    items="$(jq -cn --argjson existing "$items" --argjson candidate "$candidate" --argjson status "$status" --argjson promoted "$promoted" '$existing + [$candidate | {candidateId,guidance,scope,rationale:.synthesis.rationale,limitations:.synthesis.limitations,sourceClusterIds,supportingProjectCount:(.supportingProjectIds|length),supportingSignalCount:(.supportingSignalIds|length),counterEvidence,model:{tier:.synthesis.modelTier,provider:.synthesis.provider,model:.synthesis.model},createdAt,synthesisVersion,reviewState:$status.action,reviewId:$status.reviewId,promoted:$promoted}]')"
  done < <(find "$candidates_dir" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | LC_ALL=C sort); fi
  items="$(jq -c 'sort_by(.candidateId)' <<<"$items")"
  if [ "$json" = true ]; then jq -cn --argjson candidates "$items" '{schemaVersion:"1",command:"candidates",modelCalls:0,candidates:$candidates}'; else jq -r '.[] | "\(.candidateId) [\(.reviewState)]\(if .promoted then " [promoted]" else "" end) — \(.guidance)"' <<<"$items"; fi
}

show_candidate() {
  local id="$1" file candidate fp status promoted=false
  file="$(m4_candidate_file "$id")"; [ -f "$file" ] && [ ! -L "$file" ] || fail 'unknown candidate ID'; m4_validate_candidate_evidence "$file" || fail 'candidate or its provenance is malformed'
  candidate="$(cat "$file")"; fp="$(jq -r .synthesis.inputFingerprint "$file")"; status="$(m4_review_status "$id" "$fp")"; m4_promotion_for_review "$(jq -r '.reviewId // empty' <<<"$status")" >/dev/null 2>&1 && promoted=true
  if [ "$json" = true ]; then jq -cn --argjson candidate "$candidate" --argjson status "$status" --argjson promoted "$promoted" '{schemaVersion:"1",command:"show",modelCalls:0,candidate:($candidate+{supportingSignalCount:($candidate.supportingSignalIds|length),supportingProjectCount:($candidate.supportingProjectIds|length),reviewState:$status.action,reviewId:$status.reviewId,promoted:$promoted})}'; else jq -r '"Candidate: \(.candidateId)\nReview: '"$(jq -r .action <<<"$status")"'\nPromoted: '"$promoted"'\nScope: \(.scope)\nGuidance: \(.guidance)\nRationale: \(.synthesis.rationale)\nLimitations: \(.synthesis.limitations|join("; "))\nClusters: \(.sourceClusterIds|join(", "))\nSignals: \(.supportingSignalIds|length) across \(.supportingProjectIds|length) projects\nCounter evidence: \(.counterEvidence|tojson)"' "$file"; fi
}

review_candidate() {
  local id="$1" file candidate fingerprint current action guidance scope review_id review_file status_file review status
  file="$(m4_candidate_file "$id")"; [ -f "$file" ] && [ ! -L "$file" ] || fail 'unknown candidate ID'; m4_validate_candidate_evidence "$file" || fail 'candidate or its provenance is malformed'
  candidate="$(cat "$file")"; fingerprint="$(jq -r .synthesis.inputFingerprint "$file")"; current="$(m4_review_status "$id" "$fingerprint")"
  case "$review_action" in
    accept) action=ACCEPT; guidance="$(jq -r .guidance "$file")"; scope="$(jq -r .scope "$file")" ;;
    edit) action=EDIT_AND_ACCEPT; guidance="$review_edit"; scope="${review_scope:-$(jq -r .scope "$file")}" ;;
    reject) action=REJECT; guidance=null; scope=null ;;
    defer) action=DEFER; guidance=null; scope=null ;;
    *) fail 'an explicit review action is required' ;;
  esac
  if { [ "$action" = ACCEPT ] || [ "$action" = EDIT_AND_ACCEPT ]; } && m4_promotion_for_review "$(jq -r '.reviewId // empty' <<<"$current")" >/dev/null 2>&1; then fail 'candidate evidence is already promoted; explicit supersession is future work'; fi
  if [ "$(jq -r .action <<<"$current")" = REJECT ] && { [ "$action" = ACCEPT ] || [ "$action" = EDIT_AND_ACCEPT ]; } && [ "$override_rejected" != true ]; then fail 'candidate is rejected for this evidence fingerprint; --override-rejected is required for a new acceptance'; fi
  if [ "$action" = EDIT_AND_ACCEPT ]; then [ -n "$guidance" ] && [ "${#guidance}" -le 600 ] || fail 'edited guidance must be 1–600 characters'; [ -n "$scope" ] && [ "${#scope}" -le 120 ] || fail 'edited scope must be 1–120 characters'; fi
  if [ "$action" != EDIT_AND_ACCEPT ] && [ -n "${review_scope:-}" ]; then fail '--scope is supported only with --edit'; fi
  review_id="review-$(sha256 "$(jq -cn --arg id "$id" --arg fp "$fingerprint" --arg action "$action" --arg guidance "$guidance" --arg scope "$scope" '{identityVersion:"1",candidateId:$id,candidateInputFingerprint:$fp,action:$action,reviewedGuidance:$guidance,reviewedScope:$scope}')")"
  review_file="$(m4_review_file "$review_id")"; status_file="$(m4_status_file "$id" "$fingerprint")"
  review="$(jq -cn --arg rid "$review_id" --arg id "$id" --arg fp "$fingerprint" --arg action "$action" --arg guidance "$guidance" --arg scope "$scope" --arg at "$(now)" '{schemaVersion:"1",kind:"user-context-candidate-review",reviewId:$rid,candidateId:$id,candidateInputFingerprint:$fp,action:$action,reviewedGuidance:(if ($action=="ACCEPT" or $action=="EDIT_AND_ACCEPT") then $guidance else null end),reviewedScope:(if ($action=="ACCEPT" or $action=="EDIT_AND_ACCEPT") then $scope else null end),reviewedAt:$at,toolVersion:"m4-human-review-v1",modelCalls:0}')"
  if [ -e "$review_file" ]; then m4_review_valid "$review_file" || fail 'existing review identity is malformed'; else m4_write_json "$review_file" "$(jq -cS . <<<"$review")"; fi
  status="$(jq -cn --arg rid "$review_id" --arg id "$id" --arg fp "$fingerprint" --arg action "$action" '{schemaVersion:"1",reviewId:$rid,candidateId:$id,candidateInputFingerprint:$fp,action:$action}')"; m4_write_json "$status_file" "$(jq -cS . <<<"$status")"
  if [ "$json" = true ]; then jq -cn --argjson review "$review" '{schemaVersion:"1",command:"review",modelCalls:0,review:$review,promotionRequired:($review.action=="ACCEPT" or $review.action=="EDIT_AND_ACCEPT")}'; else echo "M4 review recorded: $review_id ($action)"; [ "$action" != ACCEPT ] && [ "$action" != EDIT_AND_ACCEPT ] || echo 'Run mana user-learning promote <review-id> to publish this explicitly accepted guidance.'; fi
}

m4_managed_entry_valid() {
  local file="$1" entry="$2" review="$3" candidate="$4" fp="$5"
  [ -f "$file" ] && [ ! -L "$file" ] && head -n 6 "$file" | grep -Fxq '<!-- mana-user-learning-promotion-v1 -->' && grep -Fxq "entryId: $entry" "$file" && grep -Fxq "reviewId: $review" "$file" && grep -Fxq "candidateId: $candidate" "$file" && grep -Fxq "inputFingerprint: $fp" "$file"
}

promote_review() {
  local review_id="$1" review_file review candidate_file candidate fp action guidance scope entry_id source managed target parent tmp content promotion_file promotion result=0 target_state refresh_needed=true
  [[ "$review_id" =~ ^review-[0-9a-f]{64}$ ]] || fail 'review ID must be a stable review hash'
  review_file="$(m4_review_file "$review_id")"; [ -f "$review_file" ] && [ ! -L "$review_file" ] || fail 'unknown review ID'; m4_review_valid "$review_file" || fail 'review is malformed'
  review="$(cat "$review_file")"; action="$(jq -r .action "$review_file")"; case "$action" in ACCEPT|EDIT_AND_ACCEPT) ;; *) fail 'only an explicitly accepted review may be promoted';; esac
  candidate_file="$(m4_candidate_file "$(jq -r .candidateId "$review_file")")"; [ -f "$candidate_file" ] && [ ! -L "$candidate_file" ] || fail 'review candidate is unavailable'; m4_validate_candidate_evidence "$candidate_file" || fail 'candidate or its provenance is malformed'
  candidate="$(cat "$candidate_file")"; fp="$(jq -r .candidateInputFingerprint "$review_file")"; [ "$fp" = "$(jq -r .synthesis.inputFingerprint "$candidate_file")" ] || fail 'review is stale because candidate evidence fingerprint changed'
  guidance="$(jq -r .reviewedGuidance "$review_file")"; scope="$(jq -r .reviewedScope "$review_file")"; [ -n "$guidance" ] && [ -n "$scope" ] || fail 'accepted review lacks explicit approved guidance or scope'
  mana_user_context_resolve_config || fail "$MANA_UC_ERROR"; [ "$MANA_UC_CONFIGURED" = true ] || fail 'User Context is not configured'; mana_user_context_validate_source "$project_root" || fail "$MANA_UC_ERROR"; source="$MANA_UC_SOURCE"
  entry_id="user-learning-entry-$(sha256 "$(jq -cn --arg review "$review_id" '{identityVersion:"1",reviewId:$review}')")"; [[ "$entry_id" =~ ^user-learning-entry-[0-9a-f]{64}$ ]] || fail 'could not derive stable managed promotion identity'; managed="$source/learned"; target="$managed/$entry_id.md"; target_state=new
  if [ -e "$managed" ] || [ -L "$managed" ]; then [ -d "$managed" ] && [ ! -L "$managed" ] || fail 'managed User Context namespace is unsafe'; fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    m4_managed_entry_valid "$target" "$entry_id" "$review_id" "$(jq -r .candidateId "$review_file")" "$fp" || fail 'managed User Context target collision is not owned by this review'
    target_state=already_promoted
  fi
  if [ "$dry_run" = true ]; then
    if [ "$json" = true ]; then jq -cn --arg review "$review_id" --arg entry "$entry_id" --arg target "$target" --arg targetState "$target_state" --arg guidance "$guidance" --arg scope "$scope" '{schemaVersion:"1",command:"promote",dryRun:true,modelCalls:0,reviewId:$review,entryId:$entry,target:$target,targetState:$targetState,guidance:$guidance,scope:$scope,refresh:"would_run"}'; else echo "M4 promotion dry run: $target_state → $target"; fi
    return 0
  fi
  if [ ! -e "$managed" ]; then mkdir "$managed" || fail 'could not create managed User Context namespace'; fi
  parent="$(cd "$managed" && pwd -P)"; [ "$parent" = "$source/learned" ] || fail 'managed User Context namespace escaped configured source'
  if [ "$target_state" = new ]; then
    content="<!-- mana-user-learning-promotion-v1 -->
entryId: $entry_id
reviewId: $review_id
candidateId: $(jq -r .candidateId "$review_file")
inputFingerprint: $fp
scope: $scope
-->
# Mana-promoted User Learning

$guidance
"
    tmp="$(mktemp "$managed/.${entry_id}.tmp.XXXXXX")" || fail 'could not stage managed User Context entry'; umask 077
    printf '%s' "$content" > "$tmp" || { rm -f "$tmp"; fail 'could not write managed User Context entry'; }
    # link(2) is atomic and fails if a manual file appeared after the ownership
    # check; unlike rename it cannot silently replace that file.
    if ! ln "$tmp" "$target"; then rm -f "$tmp"; fail 'managed User Context target changed or collided during publication'; fi
    rm -f "$tmp" || fail 'could not finalize managed User Context entry'
  fi
  promotion_file="$state/user-learning/promotions/$entry_id.json"
  if mana_user_context_refresh "$project_root"; then target_state=promoted; else target_state=source_published_refresh_failed; result=3; fi
  promotion="$(jq -cn --arg entry "$entry_id" --arg review "$review_id" --arg candidate "$(jq -r .candidateId "$review_file")" --arg fp "$fp" --arg target "$target" --arg status "$target_state" --arg at "$(now)" '{schemaVersion:"1",kind:"user-context-promotion",entryId:$entry,reviewId:$review,candidateId:$candidate,candidateInputFingerprint:$fp,target:$target,status:$status,publishedAt:$at,modelCalls:0}')"; m4_write_json "$promotion_file" "$(jq -cS . <<<"$promotion")"
  if [ "$json" = true ]; then jq -cn --argjson promotion "$promotion" --argjson refreshed "$([ "$result" -eq 0 ] && echo true || echo false)" '{schemaVersion:"1",command:"promote",dryRun:false,modelCalls:0,promotion:$promotion,refreshSucceeded:$refreshed}'; else echo "M4 promotion: $target_state ($target)"; fi
  return "$result"
}

synthesize() {
  local learning_dir="$state/user-learning" clusters_dir="$state/user-learning/clusters" candidates_dir="$state/user-learning/candidates" synthesis_dir="$state/user-learning/synthesis" scratch file unit package serialized_input fingerprint cache_file output_file domain_output_file canonical_output_file status_file output cluster_ids exposed_ids candidate_id candidate_file family_candidate_id synthesis result_json input_bytes estimated_input_tokens selected_signals minimum_signals schema_template reduced=false
  local files_scanned=0 valid_clusters=0 skipped_clusters=0 unit_count=0 considered=0 skipped=0 cached=0 ready=0 calls=0 avoided=0 candidate_results=0 no_candidate_results=0 failures=0 transport_failures=0 invalid_responses=0 estimated_output_tokens=0 reduced_units=0 irreducibly_oversized=0 estimated_input_tokens_total=0 serialized_input_bytes_total=0 provider_failure_diagnostics='[]'
  m3_init_limits; [ ! -L "$clusters_dir" ] || fail 'User Learning clusters directory must not be a symlink'; [ ! -L "$candidates_dir" ] || fail 'User Learning candidates directory must not be a symlink'; [ ! -L "$synthesis_dir" ] || fail 'User Learning synthesis directory must not be a symlink'
  mkdir -p "$candidates_dir" "$synthesis_dir" || fail 'could not create M3 state directory'
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-synthesize.XXXXXX")" || fail 'could not create M3 scratch directory'; m3_scratch="$scratch"; trap 'rm -rf "$scratch"' RETURN
  : > "$scratch/clusters.jsonl"; : > "$scratch/signals.jsonl"
  if [ -d "$clusters_dir" ]; then while IFS= read -r file; do [ -n "$file" ] || continue; files_scanned=$((files_scanned+1)); if m3_valid_cluster "$file" && [ "${file##*/}" = "$(jq -r .clusterId "$file").json" ]; then cat "$file" >> "$scratch/clusters.jsonl"; printf '\n' >> "$scratch/clusters.jsonl"; valid_clusters=$((valid_clusters+1)); else skipped_clusters=$((skipped_clusters+1)); fi; done < <(find "$clusters_dir" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | LC_ALL=C sort); fi
  if [ -d "$signals_dir" ]; then while IFS= read -r file; do [ -n "$file" ] || continue; if m2_valid_signal "$file" && [ "${file##*/}" = "$(jq -r .signalId "$file").json" ]; then cat "$file" >> "$scratch/signals.jsonl"; printf '\n' >> "$scratch/signals.jsonl"; fi; done < <(find "$signals_dir" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | LC_ALL=C sort); fi
  if [ -s "$scratch/clusters.jsonl" ]; then jq -sc 'sort_by(.clusterId)' "$scratch/clusters.jsonl" > "$scratch/clusters.json"; else printf '[]\n' > "$scratch/clusters.json"; fi
  if [ -s "$scratch/signals.jsonl" ]; then jq -sc 'sort_by(.signalId)' "$scratch/signals.jsonl" > "$scratch/signals.json"; else printf '[]\n' > "$scratch/signals.json"; fi
  # Lexical token buckets are preselection only: they form bounded windows and
  # never assert that two clusters are semantically equivalent.
  jq --argjson max "$m3_max_clusters" --argjson maxUnits "$m3_max_units" '
    def tokens: ascii_downcase | gsub("[^a-z0-9]+"; " ") | split(" ") | map(select(length >= 4) | gsub("s$"; "")) | unique;
    [ .[] | . + {tokens:(.aggregationKey.normalizedSubject | tokens)} ] as $clusters |
    [ $clusters[] as $c | $c.tokens[] | {key:("token:" + .),cluster:$c} ] | sort_by(.key,.cluster.clusterId) | group_by(.key)
    | map({unitKey:.[0].key,clusters:(map(.cluster)|unique_by(.clusterId)|sort_by(.clusterId)|.[0:$max])}) | map(select(.clusters|length >= 2)) as $multi |
      [$clusters[] | {unitKey:("cluster:" + .clusterId),clusters:[.]}] as $single |
      (($multi | map(. + {rank:0})) + ($single | map(. + {rank:1})))
      | sort_by(.rank,.unitKey) | unique_by(.clusters|map(.clusterId)) | .[0:$maxUnits] | map(del(.rank))
  ' "$scratch/clusters.json" > "$scratch/units.json"; unit_count="$(jq length "$scratch/units.json")"
  while IFS= read -r unit; do
    [ -n "$unit" ] || continue; considered=$((considered+1)); cluster_ids="$(jq -c '[.clusters[].clusterId]|sort' <<<"$unit")"
    reduced=false
    # A longitudinal exact recurrence can require semantic judgment too: T1
    # decides whether it is reusable guidance or merely repeated constraint.
    # Weak evidence remains a deterministic no-spend outcome.
    if ! jq -e '[.clusters[].supportingSignalIds[]]|unique|length >= 3' <<<"$unit" >/dev/null; then
      skipped=$((skipped+1)); avoided=$((avoided+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE insufficient_distinct_signals null 0 0 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue
    fi
    if ! jq -e '[.clusters[].supportingProjectIds[]]|unique|length >= 2' <<<"$unit" >/dev/null; then
      skipped=$((skipped+1)); avoided=$((avoided+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE insufficient_distinct_projects null 0 0 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue
    fi
    family_candidate_id="user-context-candidate-$(sha256 "$(jq -cn --argjson ids "$cluster_ids" '{identityVersion:"1",synthesisVersion:"m3-bounded-semantic-synthesis-v1",semanticTask:"bounded-evidence-family",sourceClusterIds:$ids}')")"
    candidate_file="$candidates_dir/$family_candidate_id.json"
    # A future review workflow may deliberately defer a candidate. M3 respects
    # that host-owned state and neither spends another call nor overwrites it.
    if [ -f "$candidate_file" ] && m3_candidate_valid "$candidate_file" && [ "$(jq -r .lifecycleState "$candidate_file")" = deferred-for-review ]; then skipped=$((skipped+1)); avoided=$((avoided+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE deferred_for_review null 0 0 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue; fi
    selected_signals="$m3_max_signals"
    # A response must be able to cite two exposed signals. For a singleton
    # family, retain two; a multi-cluster family can retain one per cluster.
    if [ "$(jq '.clusters|length' <<<"$unit")" -eq 1 ]; then minimum_signals=2; else minimum_signals=1; fi
    if [ "$selected_signals" -lt "$minimum_signals" ]; then skipped=$((skipped+1)); avoided=$((avoided+1)); irreducibly_oversized=$((irreducibly_oversized+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE insufficient_exposed_signals null 0 0 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue; fi
    package="$(m3_build_package "$unit" "$selected_signals")"; serialized_input="$(m3_prompt "$package")"
    input_bytes="$(printf '%s' "$serialized_input" | wc -c | tr -d ' ')"; estimated_input_tokens="$(m3_estimate_tokens "$input_bytes")"
    while { [ "$input_bytes" -gt "$m3_max_input_bytes" ] || [ "$estimated_input_tokens" -gt "$m3_max_input_tokens" ]; } && [ "$selected_signals" -gt "$minimum_signals" ]; do
      selected_signals=$((selected_signals - 1)); reduced=true
      package="$(m3_build_package "$unit" "$selected_signals")"; serialized_input="$(m3_prompt "$package")"
      input_bytes="$(printf '%s' "$serialized_input" | wc -c | tr -d ' ')"; estimated_input_tokens="$(m3_estimate_tokens "$input_bytes")"
    done
    if ! jq -e 'all(.evidenceFamilies[].supportingSignals[]; .signalId != null and .projectId != null)' <<<"$package" >/dev/null; then skipped=$((skipped+1)); avoided=$((avoided+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE missing_exposed_signal_provenance "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue; fi
    if [ "$input_bytes" -gt "$m3_max_input_bytes" ] || [ "$estimated_input_tokens" -gt "$m3_max_input_tokens" ]; then skipped=$((skipped+1)); avoided=$((avoided+1)); irreducibly_oversized=$((irreducibly_oversized+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE irreducibly_oversized "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"not_invoked","path":"$"}'; continue; fi
    if [ "$reduced" = true ]; then reduced_units=$((reduced_units+1)); fi
    estimated_input_tokens_total=$((estimated_input_tokens_total + estimated_input_tokens)); serialized_input_bytes_total=$((serialized_input_bytes_total + input_bytes))
    fingerprint="m3-input-$(sha256 "$(jq -cS . <<<"$package")")"; cache_file="$synthesis_dir/$fingerprint.json"
    if [ "$force" = false ] && [ -f "$cache_file" ] && jq -e --arg fp "$fingerprint" '.schemaVersion=="1" and .inputFingerprint==$fp and (.result=="CANDIDATE" or .result=="NO_CANDIDATE")' "$cache_file" >/dev/null 2>&1; then cached=$((cached+1)); avoided=$((avoided+1)); m3_write_diagnostic "$unit" NOT_ELIGIBLE cached_valid_result "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":true,"cached":true}'; continue; fi
    ready=$((ready+1))
    if [ "$dry_run" = true ]; then m3_write_diagnostic "$unit" ELIGIBLE dry_run "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"not_invoked_dry_run","path":"$"}'; continue; fi
    exposed_ids="$(jq -c '[.evidenceFamilies[].supportingSignals[].signalId]|unique|sort' <<<"$package")"; output_schema=""
    if [ "$m3_provider" = codex ]; then
      schema_template="$root/docs/standards/user-learning-m3-codex-transport.schema.json"; output_schema="$scratch/codex-output-schema-$considered.json"
      if [ ! -f "$schema_template" ] || [ -L "$schema_template" ]; then failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic '' 127 0 false false 0 false 'Codex M3 transport schema is unavailable'; m3_write_diagnostic "$unit" PROVIDER_FAILURE codex_transport_schema_unavailable "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"codex_transport_schema_unavailable","path":"$"}'; continue; fi
      if ! jq -e --argjson clusters "$cluster_ids" --argjson signals "$exposed_ids" '
        .properties.relatedClusterIds.items.enum = $clusters |
        .properties.supportingSignalIds.items.enum = $signals
      ' "$schema_template" > "$output_schema"; then failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic '' 127 0 false false 0 false 'could not bind Codex M3 schema to exposed provenance'; m3_write_diagnostic "$unit" PROVIDER_FAILURE codex_transport_schema_generation_failed "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"codex_transport_schema_generation_failed","path":"$"}'; continue; fi
    fi
    mkdir -p "$scratch/empty"; MANA_PROVIDER_PROGRAM="$m3_provider"; mana_provider_synthesis_args "$m3_provider" "$scratch/empty" "$m3_model" host-disposable-non-git "$output_schema" "$m3_codex_reasoning_effort" || { failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic '' 127 0 false false 0 false 'could not construct provider runner arguments'; m3_write_diagnostic "$unit" PROVIDER_FAILURE provider_argument_construction_failed "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"provider_argument_construction_failed","path":"$"}'; continue; }; runner_program="${MANA_PROVIDER_PROGRAM:-$m3_provider}"
    if ! command -v "$runner_program" >/dev/null 2>&1; then failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic '' 127 0 false false 0 false 'provider executable is unavailable'; m3_write_diagnostic "$unit" PROVIDER_FAILURE provider_executable_unavailable "$package" "$input_bytes" "$estimated_input_tokens" 0 '' '' '{"valid":false,"error":"provider_executable_unavailable","path":"$"}'; continue; fi
    output_file="$scratch/output-$considered.json"; status_file="$scratch/status-$considered"; perl "$root/scripts/lib/verification-exec.pl" --timeout "$m3_timeout_seconds" --output-cap "$m3_max_output_bytes" --stderr-cap 4096 --stdout "$output_file" --stderr "$scratch/stderr-$considered" --status "$status_file" -- "$runner_program" "${MANA_PROVIDER_ARGS[@]}" "$serialized_input" || true; calls=$((calls+1))
    if [ ! -f "$status_file" ]; then failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic "$scratch/stderr-$considered" 125 0 false false 0 false 'provider execution supervisor did not produce status'; m3_write_diagnostic "$unit" PROVIDER_FAILURE supervisor_status_missing "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" '{"valid":false,"error":"supervisor_status_missing","path":"$"}'; continue; fi
    IFS=$'\t' read -r runner_code runner_signal runner_timeout runner_descendants runner_out_bytes runner_err_bytes runner_duration < "$status_file"; estimated_output_tokens=$((estimated_output_tokens + (runner_out_bytes + 3) / 4))
    if [ "$runner_code" -ne 0 ] || [ "$runner_timeout" != 0 ] || [ "$runner_descendants" != 0 ]; then failures=$((failures+1)); transport_failures=$((transport_failures+1)); m3_add_provider_failure_diagnostic "$scratch/stderr-$considered" "$runner_code" "$runner_signal" "$([ "$runner_timeout" = 1 ] && echo true || echo false)" "$([ "$runner_descendants" = 1 ] && echo true || echo false)" "$runner_err_bytes" "$([ "$runner_err_bytes" -gt "$m3_max_output_bytes" ] && echo true || echo false)" ''; m3_write_diagnostic "$unit" PROVIDER_FAILURE provider_execution_failed "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" '{"valid":false,"error":"provider_execution_failed","path":"$"}'; continue; fi
    domain_output_file="$output_file"
    if [ "$m3_provider" = codex ]; then
      domain_output_file="$scratch/domain-output-$considered.json"
      if ! m3_codex_transport_to_domain "$output_file" > "$domain_output_file" 2>/dev/null; then validation='{"valid":false,"error":"invalid_codex_flat_transport_semantics","path":"$"}'; failures=$((failures+1)); invalid_responses=$((invalid_responses+1)); m3_write_diagnostic "$unit" INVALID_STRUCTURED_OUTPUT invalid_codex_flat_transport_semantics "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" "$validation"; continue; fi
    fi
    validation="$(m3_output_validation_diagnostic "$domain_output_file" "$cluster_ids" "$exposed_ids")"
    if ! m3_output_valid "$domain_output_file" "$cluster_ids" "$exposed_ids"; then failures=$((failures+1)); invalid_responses=$((invalid_responses+1)); m3_write_diagnostic "$unit" INVALID_STRUCTURED_OUTPUT invalid_structured_output "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" "$validation"; continue; fi
    canonical_output_file="$scratch/canonical-output-$considered.json"
    if ! m3_canonicalize_provenance "$domain_output_file" > "$canonical_output_file"; then failures=$((failures+1)); invalid_responses=$((invalid_responses+1)); validation='{"valid":false,"error":"provenance_canonicalization_failed","path":"$"}'; m3_write_diagnostic "$unit" INVALID_STRUCTURED_OUTPUT provenance_canonicalization_failed "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" "$validation"; continue; fi
    domain_output_file="$canonical_output_file"
    output="$(cat "$domain_output_file")"; candidate_id="$family_candidate_id"
    if [ "$(jq -r .result <<<"$output")" = CANDIDATE ]; then
      candidate_file="$candidates_dir/$candidate_id.json"; created_at="$(jq -r '.createdAt // empty' "$candidate_file" 2>/dev/null || true)"; [ -n "$created_at" ] || created_at="$(now)"
      candidate="$(jq -cn --arg id "$candidate_id" --arg created "$created_at" --arg updated "$(now)" --arg fp "$fingerprint" --arg provider "$m3_provider" --arg model "$m3_model" --argjson clusters "$cluster_ids" --argjson unit "$unit" --argjson package "$package" --argjson response "$output" --argjson outTokens "$(( (runner_out_bytes + 3) / 4 ))" --argjson inTokens "$estimated_input_tokens" --argjson inBytes "$input_bytes" --argjson reduced "$reduced" '{schemaVersion:"1",kind:"user-context-candidate",candidateId:$id,synthesisVersion:"m3-bounded-semantic-synthesis-v1",lifecycleState:"proposed",guidance:$response.guidance,scope:$response.scope,sourceClusterIds:$clusters,supportingSignalIds:$response.supportingSignalIds,supportingProjectIds:([$package.evidenceFamilies[].supportingSignals[].projectId]|unique|sort),counterEvidence:([$unit.clusters[].alternativeConfirmedEvidence[]?]),synthesis:{modelTier:"T1",provider:$provider,model:$model,inputFingerprint:$fp,invocation:{count:1,inputTokensEstimated:$inTokens,serializedInputBytes:$inBytes,evidenceReduced:$reduced,outputTokensEstimated:$outTokens},rationale:$response.rationale,limitations:$response.limitations},createdAt:$created,updatedAt:$updated}')"
      m3_write_json "$candidate_file" "$(jq -cS . <<<"$candidate")"; candidate_results=$((candidate_results+1)); synthesis="$(jq -cn --arg fp "$fingerprint" --arg candidate "$candidate_id" --argjson clusters "$cluster_ids" '{schemaVersion:"1",kind:"user-learning-synthesis",synthesisVersion:"m3-bounded-semantic-synthesis-v1",inputFingerprint:$fp,result:"CANDIDATE",candidateId:$candidate,sourceClusterIds:$clusters}')"
    else
      no_candidate_results=$((no_candidate_results+1)); synthesis="$(jq -cn --arg fp "$fingerprint" --arg reason "$(jq -r .reason <<<"$output")" --argjson clusters "$cluster_ids" '{schemaVersion:"1",kind:"user-learning-synthesis",synthesisVersion:"m3-bounded-semantic-synthesis-v1",inputFingerprint:$fp,result:"NO_CANDIDATE",reason:$reason,sourceClusterIds:$clusters}')"
    fi
    m3_write_json "$cache_file" "$(jq -cS . <<<"$synthesis")"
    m3_write_diagnostic "$unit" VALID_STRUCTURED_RESULT '' "$package" "$input_bytes" "$estimated_input_tokens" 1 "$output_file" "$scratch/stderr-$considered" "$validation" "$output"
  done < <(jq -c '.[]' "$scratch/units.json")
  result_json="$(jq -cn --arg state "$learning_dir" --arg provider "$m3_provider" --arg model "$m3_model" --argjson scanned "$files_scanned" --argjson valid "$valid_clusters" --argjson skippedClusters "$skipped_clusters" --argjson units "$unit_count" --argjson considered "$considered" --argjson skipped "$skipped" --argjson cached "$cached" --argjson ready "$ready" --argjson calls "$calls" --argjson avoided "$avoided" --argjson candidates "$candidate_results" --argjson none "$no_candidate_results" --argjson failures "$failures" --argjson transportFailures "$transport_failures" --argjson invalidResponses "$invalid_responses" --argjson estimatedOutput "$estimated_output_tokens" --argjson estimatedInput "$estimated_input_tokens_total" --argjson serializedInput "$serialized_input_bytes_total" --argjson reduced "$reduced_units" --argjson oversized "$irreducibly_oversized" --argjson dry "$dry_run" --argjson maxClusters "$m3_max_clusters" --argjson maxSignals "$m3_max_signals" --argjson maxInput "$m3_max_input_tokens" --argjson maxBytes "$m3_max_input_bytes" --argjson maxOutput "$m3_max_output_tokens" --argjson failureDiagnostics "$provider_failure_diagnostics" '{schemaVersion:"1",command:"synthesize",statePath:$state,modelTier:"T1",provider:$provider,model:$model,dryRun:$dry,budgets:{maxEvidenceClusters:$maxClusters,maxSupportingSignalsPerCluster:$maxSignals,estimatedInputTokensBudget:$maxInput,hardSerializedInputBytes:$maxBytes,maxOutputTokens:$maxOutput,invocationsPerUnit:1},clustersScanned:$scanned,validClusters:$valid,skippedClusters:$skippedClusters,synthesisUnits:$units,unitsConsidered:$considered,unitsSkippedDeterministically:$skipped,unitsReducedBeforeProviderCall:$reduced,unitsSkippedIrreduciblyOversized:$oversized,unitsAlreadySynthesized:$cached,unitsReadyToCall:$ready,modelCalls:$calls,modelCallsAvoided:$avoided,estimatedInputTokens:$estimatedInput,serializedInputBytes:$serializedInput,estimatedOutputTokens:$estimatedOutput,candidateResults:$candidates,noCandidateResults:$none,providerFailures:$failures,providerTransportFailures:$transportFailures,invalidProviderResponses:$invalidResponses} + (if ($failureDiagnostics|length)>0 then {providerFailureDiagnostics:$failureDiagnostics} else {} end)')"
  if [ "$json" = true ]; then printf '%s\n' "$result_json"; else echo 'MANA USER LEARNING SYNTHESIZE'; echo "T1 provider/model: $m3_provider/$m3_model"; echo "Units: $unit_count; ready: $ready; calls: $calls; avoided: $avoided; candidates: $candidate_results; no candidate: $no_candidate_results; failures: $failures"; echo "Budgets: $m3_max_clusters clusters, $m3_max_signals signals/cluster, $m3_max_input_tokens estimated input tokens, $m3_max_input_bytes hard serialized-input bytes, $m3_max_output_tokens output tokens"; fi
  trap - RETURN; rm -rf "$scratch"
}

aggregate() {
  local learning_dir="$state/user-learning" clusters_dir="$state/user-learning/clusters" scratch stage backup file base signal_id normalized candidates cluster_count recurring_count distinct_projects skipped_json cluster_json result
  [ ! -L "$signals_dir" ] || fail 'User Learning signals directory must not be a symlink'
  [ ! -L "$clusters_dir" ] || fail 'User Learning clusters directory must not be a symlink'
  mkdir -p "$learning_dir" || fail 'could not create User Learning state directory'
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-aggregate.XXXXXX")" || fail 'could not create aggregation scratch directory'
  aggregation_valid_file="$scratch/valid.jsonl"; aggregation_skips_file="$scratch/skipped.jsonl"; mkdir -p "$scratch/seen"
  aggregation_files_scanned=0; aggregation_valid_count=0; aggregation_skipped_count=0; aggregation_duplicate_count=0
  if [ -d "$signals_dir" ]; then
    while IFS= read -r file; do
      [ -n "$file" ] || continue
      aggregation_files_scanned=$((aggregation_files_scanned + 1))
      if ! jq -e 'type == "object"' "$file" >/dev/null 2>&1; then m2_add_skip "$file" malformed_json; aggregation_skipped_count=$((aggregation_skipped_count + 1)); continue; fi
      if ! jq -e '.schemaVersion == "2"' "$file" >/dev/null 2>&1; then m2_add_skip "$file" unsupported_schema_version; aggregation_skipped_count=$((aggregation_skipped_count + 1)); continue; fi
      if ! m2_valid_signal "$file"; then m2_add_skip "$file" schema_invalid; aggregation_skipped_count=$((aggregation_skipped_count + 1)); continue; fi
      signal_id="$(jq -r .signalId "$file")"; base="${file##*/}"
      if [ -d "$scratch/seen/$signal_id" ]; then m2_add_skip "$file" duplicate_signal_id; aggregation_skipped_count=$((aggregation_skipped_count + 1)); aggregation_duplicate_count=$((aggregation_duplicate_count + 1)); continue; fi
      if [ "$base" != "$signal_id.json" ]; then m2_add_skip "$file" filename_id_mismatch; aggregation_skipped_count=$((aggregation_skipped_count + 1)); continue; fi
      mkdir "$scratch/seen/$signal_id"
      if ! normalized="$(m2_normalized_signal "$file")"; then m2_add_skip "$file" empty_aggregation_field; aggregation_skipped_count=$((aggregation_skipped_count + 1)); continue; fi
      printf '%s\n' "$normalized" >> "$aggregation_valid_file"; aggregation_valid_count=$((aggregation_valid_count + 1))
    done < <(find "$signals_dir" -maxdepth 1 -type f -name '*.json' -print 2>/dev/null | LC_ALL=C sort)
    while IFS= read -r file; do
      [ -n "$file" ] || continue
      aggregation_files_scanned=$((aggregation_files_scanned + 1)); aggregation_skipped_count=$((aggregation_skipped_count + 1)); m2_add_skip "$file" unsafe_symlink
    done < <(find "$signals_dir" -maxdepth 1 -type l -name '*.json' -print 2>/dev/null | LC_ALL=C sort)
  fi
  if [ -s "$aggregation_valid_file" ]; then
    jq -sc '
      def grouped:
        sort_by(.normalizedSubject, .normalizedConfirmedChoice, .signalId)
        | group_by([.normalizedSubject, .normalizedConfirmedChoice])
        | map({aggregationKey:{aggregationVersion:"1",normalizedSubject:.[0].normalizedSubject,normalizedConfirmedChoice:.[0].normalizedConfirmedChoice},supportingSignalIds:(map(.signalId) | sort),supportingProjectIds:(map(.projectId) | unique | sort),occurrenceCount:length,distinctProjectCount:(map(.projectId) | unique | length)});
      grouped as $clusters
      | $clusters
      | map(. as $cluster | . + {alternativeConfirmedEvidence:($clusters | map(select(.aggregationKey.normalizedSubject == $cluster.aggregationKey.normalizedSubject and .aggregationKey.normalizedConfirmedChoice != $cluster.aggregationKey.normalizedConfirmedChoice) | {normalizedConfirmedChoice:.aggregationKey.normalizedConfirmedChoice,supportingSignalIds,supportingProjectIds}))})
      | sort_by(.aggregationKey.normalizedSubject, .aggregationKey.normalizedConfirmedChoice)
    ' "$aggregation_valid_file" > "$scratch/candidates.json"
  else
    printf '[]\n' > "$scratch/candidates.json"
  fi
  cluster_count="$(jq 'length' "$scratch/candidates.json")"; recurring_count="$(jq '[.[] | select(.occurrenceCount > 1)] | length' "$scratch/candidates.json")"
  if [ -s "$aggregation_valid_file" ]; then distinct_projects="$(jq -sc 'map(.projectId) | unique | length' "$aggregation_valid_file")"; else distinct_projects=0; fi
  stage="$(mktemp -d "$learning_dir/.clusters-stage.XXXXXX")" || fail 'could not create cluster staging directory'
  while IFS= read -r candidates; do
    [ -n "$candidates" ] || continue
    identity_key="$(jq -c .aggregationKey <<<"$candidates")"; cluster_id="cluster-$(sha256 "$identity_key")"
    jq -cn --arg id "$cluster_id" --argjson candidate "$candidates" '{schemaVersion:"1",clusterId:$id} + $candidate + {derivation:{processor:"deterministic-user-learning-aggregation-v1",aggregationVersion:"1",normalization:"trim-collapse-whitespace-preserve-case-v1",modelCalls:0}}' | jq -S . > "$stage/$cluster_id.json"
  done < <(jq -c '.[]' "$scratch/candidates.json")
  backup="$learning_dir/.clusters-previous-$$"
  if [ -e "$clusters_dir" ] || [ -L "$clusters_dir" ]; then mv "$clusters_dir" "$backup" || fail 'could not stage previous cluster state'; fi
  if ! mv "$stage" "$clusters_dir"; then [ ! -e "$backup" ] || mv "$backup" "$clusters_dir"; fail 'could not publish cluster state'; fi
  [ ! -e "$backup" ] || rm -rf "$backup"
  if [ "$cluster_count" -gt 0 ]; then cluster_json="$(jq -s 'sort_by(.clusterId)' "$clusters_dir"/*.json)"; else cluster_json='[]'; fi
  if [ -s "$aggregation_skips_file" ]; then skipped_json="$(jq -sc 'sort_by(.path, .reason)' "$aggregation_skips_file")"; else skipped_json='[]'; fi
  result="$(jq -cn --arg state "$learning_dir" --argjson files "$aggregation_files_scanned" --argjson valid "$aggregation_valid_count" --argjson skipped "$aggregation_skipped_count" --argjson duplicates "$aggregation_duplicate_count" --argjson clusters "$cluster_count" --argjson recurring "$recurring_count" --argjson relationships "$aggregation_valid_count" --argjson projects "$distinct_projects" --argjson cluster_records "$cluster_json" --argjson skipped_items "$skipped_json" '{schemaVersion:"1",command:"aggregate",statePath:$state,signalFilesScanned:$files,validSignals:$valid,skippedSignals:$skipped,duplicateSignals:$duplicates,clustersProduced:$clusters,recurringClusters:$recurring,totalSupportingRelationships:$relationships,distinctProjects:$projects,modelCalls:0,clusters:$cluster_records,skippedItems:$skipped_items}')"
  rm -rf "$scratch"
  if [ "$json" = true ]; then printf '%s\n' "$result"; else
    echo 'MANA USER LEARNING AGGREGATE'; echo "Valid signals: $aggregation_valid_count"; echo "Skipped signals: $aggregation_skipped_count"; echo "Clusters: $cluster_count ($recurring_count recurring)"; echo "Distinct projects: $distinct_projects"; echo 'Model calls: 0'
    jq -r '.clusters[] | "\(.clusterId) — \(.occurrenceCount) signals across \(.distinctProjectCount) projects"' <<<"$result"
    jq -r '.skippedItems[] | "Skipped: \(.path) — \(.reason)"' <<<"$result"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2 ;;
    --json) json=true; shift ;;
    --dry-run) dry_run=true; shift ;;
    --force) force=true; shift ;;
    --accept) [ -z "$review_action" ] || fail 'review actions are mutually exclusive'; review_action=accept; shift ;;
    --edit) [ -z "$review_action" ] || fail 'review actions are mutually exclusive'; review_action=edit; review_edit="${2:-}"; [ -n "$review_edit" ] || fail '--edit requires guidance'; shift 2 ;;
    --reject) [ -z "$review_action" ] || fail 'review actions are mutually exclusive'; review_action=reject; shift ;;
    --defer) [ -z "$review_action" ] || fail 'review actions are mutually exclusive'; review_action=defer; shift ;;
    --scope) review_scope="${2:-}"; [ -n "$review_scope" ] || fail '--scope requires a value'; shift 2 ;;
    --override-rejected) override_rejected=true; shift ;;
    --help|-h) usage; exit 0 ;;
    capture|aggregate|synthesize|candidates|show|review|promote) [ -z "$command" ] || { usage; exit 2; }; command="$1"; shift ;;
    *) positionals+=("$1"); shift ;;
  esac
done
[ -n "$command" ] || { usage; exit 2; }
case "$command" in
  show|review|promote) [ "${#positionals[@]}" -eq 1 ] || fail "$command requires one explicit ID" ;;
  candidates|capture|aggregate|synthesize) [ "${#positionals[@]}" -eq 0 ] || fail "$command does not accept positional arguments" ;;
esac
[ "$command" = review ] || { [ -z "$review_action" ] && [ -z "$review_scope" ] && [ "$override_rejected" = false ]; } || fail 'review action options are valid only with review'
[ "$dry_run" = false ] || { [ "$command" = synthesize ] || [ "$command" = promote ]; } || fail '--dry-run is supported only by synthesize or promote'
[ "$force" = false ] || [ "$command" = synthesize ] || fail '--force is supported only by synthesize'
mana_json_require
[ -d "$project_root" ] || fail "project root not found: $project_root"
project_root="$(cd "$project_root" && pwd -P)"
state="$(state_root)"
case "$state/" in "$project_root/"*) fail 'User Learning state location must be outside the project repository';; esac
umask 077
mkdir -p "$state/user-learning" || fail 'could not create User Learning state directory'
state="$(cd "$state" && pwd -P)"
case "$state/" in "$project_root/"*) fail 'User Learning state location must be outside the project repository';; esac
signals_dir="$state/user-learning/signals"

if [ "$command" = aggregate ]; then
  aggregate
  exit 0
fi

if [ "$command" = synthesize ]; then
  synthesize
  exit 0
fi

case "$command" in
  candidates) candidates; exit 0 ;;
  show) show_candidate "${positionals[0]}"; exit 0 ;;
  review) review_candidate "${positionals[0]}"; exit 0 ;;
  promote) promote_review "${positionals[0]}"; exit $? ;;
esac

mkdir -p "$signals_dir" || fail 'could not create User Learning signals directory'

remote="$(git -C "$project_root" config --get remote.origin.url 2>/dev/null || true)"
project_identity="${remote:-path:$project_root}"
project_id="project-$(sha256 "$project_identity")"
logs="$(find "$project_root/.mana/features" "$project_root/.mana/sessions" -type f -path '*/decisions/developer-choice-log.md' -print 2>/dev/null | LC_ALL=C sort || true)"
discovered=0; stored=0; known=0; skipped=0
skipped_json='[]'; source_json='[]'

while IFS= read -r log; do
  [ -n "$log" ] || continue
  rel="${log#"$project_root"/}"
  artifact_digest="$(file_sha256 "$log")"
  source_json="$(jq -cn --argjson existing "$source_json" --arg path "$rel" --arg digest "$artifact_digest" '$existing + [{path:$path,digest:$digest}]')"
  while IFS=$'\034' read -r kind source line choice_ordinal date story area subject answer evidence confirmed_by status follow_up; do
    [ -n "$kind" ] || continue
    if [ "$kind" = malformed ]; then
      skipped=$((skipped + 1))
      skipped_json="$(jq -cn --argjson existing "$skipped_json" --arg path "$source" --argjson line "$line" '$existing + [{source:$path,line:$line,reason:"malformed_choice_row"}]')"
      continue
    fi
    if [ "$status" != confirmed ]; then
      skipped=$((skipped + 1))
      skipped_json="$(jq -cn --argjson existing "$skipped_json" --arg path "$source" --argjson line "$line" --arg status "$status" '$existing + [{source:$path,line:$line,reason:(if $status == "" then "missing_status" else "status_not_eligible" end),status:$status}]')"
      continue
    fi
    if [ -z "$subject" ] || [ -z "$answer" ] || [ -z "$confirmed_by" ]; then
      skipped=$((skipped + 1))
      skipped_json="$(jq -cn --argjson existing "$skipped_json" --arg path "$source" --argjson line "$line" '$existing + [{source:$path,line:$line,reason:"confirmed_choice_missing_required_explicit_data"}]')"
      continue
    fi
    identity_key="$(jq -cn --arg project "$project_id" --arg log "$source" --argjson ordinal "$choice_ordinal" '{identityVersion:"1",projectId:$project,sourceLog:$log,choiceOrdinal:$ordinal}')"
    signal_id="user-choice-$(sha256 "$identity_key")"
    signal_file="$signals_dir/$signal_id.json"
    decision_ref="$source#choice-$choice_ordinal"
    payload="$(jq -cn \
      --arg id "$signal_id" --arg project_id "$project_id" --arg project_root "$project_root" \
      --arg ref "$decision_ref" --arg path "$source" --argjson line "$line" --argjson choice_ordinal "$choice_ordinal" \
      --arg date "$date" --arg story "$story" --arg area "$area" --arg subject "$subject" --arg choice "$answer" --arg confirmed_by "$confirmed_by" --arg evidence "$evidence" --arg follow_up "$follow_up" \
      --arg artifact_digest "$artifact_digest" --arg captured_at "$(now)" \
      '{schemaVersion:"2",signalId:$id,sourceProject:{projectId:$project_id,repositoryRoot:$project_root},sourceDecision:({reference:$ref,logPath:$path,line:$line,choiceOrdinal:$choice_ordinal,status:"confirmed",subject:$subject,confirmedChoice:$choice,confirmedBy:$confirmed_by} + (if ($date | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")) then {decisionDate:$date} else {} end) + (if $story != "" then {story:$story} else {} end) + (if $area != "" then {area:$area} else {} end)),provenance:({sourceType:"developer-choice-log",sourceArtifact:{path:$path,sha256:$artifact_digest},evidence:(if $evidence != "" then [$evidence] else [] end)} + (if $follow_up != "" then {followUp:$follow_up} else {} end)),capture:{processor:"deterministic-developer-choice-log-v1",modelCalls:0,capturedAt:$captured_at}}')"
    discovered=$((discovered + 1))
    if [ -e "$signal_file" ]; then
      validate_signal "$signal_file" "$signal_id"
      known=$((known + 1))
    else
      write_signal "$signal_file" "$payload" || { validate_signal "$signal_file" "$signal_id"; known=$((known + 1)); continue; }
      stored=$((stored + 1))
    fi
  done < <(extract_rows "$log" "$rel")
done <<EOF
$logs
EOF

result="$(jq -cn --arg state "$state/user-learning" --arg project "$project_id" --argjson discovered "$discovered" --argjson stored "$stored" --argjson known "$known" --argjson skipped "$skipped" --argjson sources "$source_json" --argjson skipped_items "$skipped_json" '{schemaVersion:"1",command:"capture",statePath:$state,sourceProjectId:$project,modelCalls:0,discoveredSignals:$discovered,newlyStored:$stored,alreadyKnown:$known,skipped:$skipped,sources:$sources,skippedItems:$skipped_items}')"
if [ "$json" = true ]; then
  printf '%s\n' "$result"
else
  echo 'MANA USER LEARNING CAPTURE'
  echo "Signals discovered: $discovered"
  echo "Newly stored: $stored"
  echo "Already known: $known"
  echo "Skipped: $skipped"
  [ "$skipped" -eq 0 ] || jq -r '.skippedItems[] | "Skipped: \(.source):\(.line) — \(.reason)"' <<<"$result"
fi
