#!/usr/bin/env bash
# Opt-in semantic acceptance only. This suite intentionally uses a real T1
# provider; it is never part of normal CI.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
fail() { echo "SEMANTIC ACCEPTANCE FAILURE: $*" >&2; exit 1; }
semantic_failures=0
semantic_fail() { echo "SEMANTIC ACCEPTANCE FAILURE: $*" >&2; semantic_failures=$((semantic_failures + 1)); }
if [ "${MANA_RUN_LIVE_MODEL_TESTS:-}" != 1 ]; then
  echo 'LIVE TEST OPT-IN REQUIRED: set MANA_RUN_LIVE_MODEL_TESTS=1 (no provider call was made).' >&2
  exit 2
fi
provider="${MANA_USER_LEARNING_T1_PROVIDER:-}"
model="${MANA_USER_LEARNING_T1_MODEL:-}"
only_case="${MANA_USER_LEARNING_LIVE_ONLY_CASE:-}"
case "$provider" in codex|claude|opencode) ;; *) echo 'LIVE TEST CONFIGURATION ERROR: set MANA_USER_LEARNING_T1_PROVIDER to codex, claude, or opencode.' >&2; exit 2;; esac
[ -n "$model" ] || { echo 'LIVE TEST CONFIGURATION ERROR: set MANA_USER_LEARNING_T1_MODEL to a configured lightweight T1 model.' >&2; exit 2; }

tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-live.XXXXXX")"
trap 'chmod -R u+w "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
# Kept separately from the harness work directory so a selected scenario keeps
# its bounded forensic record even when an assertion exits nonzero.
artifact_root="${MANA_USER_LEARNING_LIVE_ARTIFACT_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning-live-artifacts.XXXXXX")}" 
case "$artifact_root" in /*) ;; *) fail 'MANA_USER_LEARNING_LIVE_ARTIFACT_DIR must be absolute';; esac
mkdir -p "$artifact_root"
live_calls=0

make_project() {
  local root_dir="$1" name="$2" subject="$3" choice="$4" evidence="$5" project log
  project="$root_dir/$name"; log="$project/.mana/features/$name/decisions/developer-choice-log.md"
  mkdir -p "$(dirname "$log")"
  cat > "$log" <<EOF
# Developer Choice Log

## Choices

| Date | Story | Area | Question Or Choice | Developer Answer | Evidence | Confirmed By | Status | Follow-Up |
|---|---|---|---|---|---|---|---|---|
| 2026-08-08 | $name | reliability | $subject | $choice | $evidence | developer@example.test | confirmed | |
EOF
  git -C "$project" init -q
  git -C "$project" remote add origin "https://example.test/mana/live-$name.git"
}

run_case() {
  local name expectation state work result project first clusters_before diagnostics candidate
  name="$1"
  expectation="$2"
  state="$tmp/$name-state"
  work="$tmp/$name-work"
  shift 2
  mkdir -p "$work"
  # Arguments are groups of four: project name, subject, choice, evidence.
  while [ "$#" -gt 0 ]; do
    make_project "$work" "$1" "$2" "$3" "$4"
    MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$work/$1" capture --json | jq -e '.modelCalls==0 and .newlyStored==1' >/dev/null || fail "$name: deterministic capture failed"
    shift 4
  done
  first="$(find "$work" -mindepth 1 -maxdepth 1 -type d -print | LC_ALL=C sort | head -n 1)"
  MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$first" aggregate --json | jq -e '.modelCalls==0' >/dev/null || fail "$name: deterministic aggregation failed"
  clusters_before="$(find "$state/user-learning/clusters" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
  if [ "${MANA_USER_LEARNING_LIVE_HARNESS_SMOKE:-}" = 1 ]; then
    echo "User Learning live semantic harness smoke passed: scenario=$name reached pre-provider stage"
    exit 0
  fi
  diagnostics="$artifact_root/$name"
  result="$(MANA_USER_STATE_HOME="$state" MANA_USER_LEARNING_DIAGNOSTICS_DIR="$diagnostics" MANA_USER_LEARNING_DIAGNOSTIC_SCENARIO="$name" MANA_USER_LEARNING_T1_PROVIDER="$provider" MANA_USER_LEARNING_T1_MODEL="$model" MANA_USER_LEARNING_MAX_CLUSTERS_PER_UNIT=8 MANA_USER_LEARNING_MAX_SIGNALS_PER_CLUSTER=3 MANA_USER_LEARNING_MAX_INPUT_TOKENS=1000 MANA_USER_LEARNING_MAX_INPUT_BYTES=4000 MANA_USER_LEARNING_MAX_OUTPUT_TOKENS=500 MANA_USER_LEARNING_MAX_SYNTHESIS_UNITS=8 "$root/scripts/mana-user-learning.sh" --project-root "$first" synthesize --json)"
  printf '%s\n' "$result" > "$diagnostics/result.json"
  if printf '%s' "$result" | jq -e '.providerTransportFailures > 0' >/dev/null; then
    diagnostics="$(printf '%s' "$result" | jq -c '.providerFailureDiagnostics // []')"
    echo "LIVE TEST INFRASTRUCTURE/PROVIDER UNAVAILABLE ($name): provider=$provider model=$model diagnostics=$diagnostics" >&2
    exit 2
  fi
  if ! printf '%s' "$result" | jq -e '.invalidProviderResponses==0 and .modelCalls==1 and .modelCalls<=1 and .serializedInputBytes<=4000 and .estimatedInputTokens<=1000 and .estimatedOutputTokens<=500' >/dev/null; then semantic_fail "$name: provider result violated the bounded structured contract"; fi
  if [ "$clusters_before" != "$(find "$state/user-learning/clusters" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ]; then semantic_fail "$name: M3 altered derived M2 clusters"; fi
  live_calls=$((live_calls + 1))
  case "$expectation" in
    none)
      printf '%s' "$result" | jq -e '.noCandidateResults==1 and .candidateResults==0' >/dev/null || semantic_fail "$name: invented reusable guidance from external constraints"
      ;;
    candidate)
      printf '%s' "$result" | jq -e '.candidateResults==1 and .noCandidateResults==0' >/dev/null || semantic_fail "$name: did not synthesize the required bounded candidate"
      candidate="$(find "$state/user-learning/candidates" -type f -name '*.json' -print -quit)"
      if [ -z "$candidate" ] || ! jq -e '.guidance|type=="string" and length>0 and length<=600' "$candidate" >/dev/null; then semantic_fail "$name: candidate guidance is missing or unbounded"; fi
      if [ -z "$candidate" ] || ! jq -e '(.sourceClusterIds|length)>=1 and (.supportingSignalIds|length)>=2' "$candidate" >/dev/null; then semantic_fail "$name: candidate provenance is incomplete"; fi
      ;;
    contextual)
      printf '%s' "$result" | jq -e '(.candidateResults==1) or (.noCandidateResults==1)' >/dev/null || semantic_fail "$name: missing semantic result"
      if printf '%s' "$result" | jq -e '.candidateResults==1' >/dev/null; then
        candidate="$(find "$state/user-learning/candidates" -type f -name '*.json' -print -quit)"
        if [ -z "$candidate" ] || ! jq -e '(.guidance|test("always|unconditional";"i")|not) and (.counterEvidence|length>0)' "$candidate" >/dev/null; then semantic_fail "$name: produced an unconditional rule despite counter-evidence"; fi
      fi
      ;;
    exact)
      printf '%s' "$result" | jq -e '.synthesisUnits==1 and .candidateResults==1 and .noCandidateResults==0' >/dev/null || semantic_fail "$name: exact recurrence did not synthesize the required reusable candidate"
      ;;
  esac
  printf '%s\n' "$result" > "$tmp/$name-result.json"
}

run_case_if_enabled() {
  local name="$1"
  shift
  [ -z "$only_case" ] || [ "$only_case" = "$name" ] || return 0
  run_case "$name" "$@"
}

# A: repeated external constraints are not a preference.
run_case_if_enabled external_constraint none \
  A 'Database selection' 'PostgreSQL' 'Customer infrastructure requires PostgreSQL.' \
  B 'Database selection' 'PostgreSQL' 'PostGIS is required.' \
  C 'Database selection' 'PostgreSQL' 'Company platform mandates PostgreSQL.'

# B: distinct choices support a narrow reusable reliability principle.
run_case_if_enabled reusable_principle candidate \
  A 'Recovering correctness critical async work' 'durable outbox' 'Failures must remain recoverable.' \
  B 'Recovering correctness critical async work' 'persistent retry' 'Work loss must be observable.' \
  C 'Recovering correctness critical async work' 'avoid fire and forget' 'Correctness depends on eventual completion.'

# C: counter-evidence permits a narrow candidate or NO_CANDIDATE, never an absolute rule.
run_case_if_enabled contextual_counter_evidence contextual \
  A 'Asynchronous work delivery' 'durable outbox' 'Correctness-critical work must remain recoverable.' \
  B 'Asynchronous work delivery' 'durable outbox' 'Loss must be observable before acknowledgement.' \
  C 'Asynchronous work delivery' 'fire and forget telemetry' 'Disposable telemetry can be dropped.'

# D: M2 keeps these wordings separate; T1 must reconcile them into one candidate.
run_case_if_enabled semantic_reconciliation candidate \
  A 'Async correctness work recovery' 'durable outbox' 'Preserve work after process failure.' \
  B 'Async correctness work recovery' 'durable outbox' 'Make asynchronous loss recoverable.' \
  C 'Recovering asynchronous correctness work' 'persistent retry' 'Observe and recover eventual completion failures.'
if [ -z "$only_case" ] || [ "$only_case" = semantic_reconciliation ]; then
  reconcile_candidate=""
  reconcile_dir="$tmp/semantic_reconciliation-state/user-learning/candidates"
  if [ -d "$reconcile_dir" ]; then reconcile_candidate="$(find "$reconcile_dir" -type f -name '*.json' -print -quit)"; fi
  if [ -z "$reconcile_candidate" ] || ! jq -e '(.sourceClusterIds|length)>=2' "$reconcile_candidate" >/dev/null; then semantic_fail 'semantic_reconciliation: candidate did not retain multiple M2 cluster references'; fi
fi

# E: one exact recurring M2 cluster is eligible for a single bounded T1 call.
run_case_if_enabled exact_recurrence exact \
  A 'Async failure handling' 'durable retry' 'We chose durable retry over fire-and-forget because completion can outlive a process and replay preserves correctness.' \
  B 'Async failure handling' 'durable retry' 'We keep durable retry because acknowledgements are unsafe until work is observable and recoverable.' \
  C 'Async failure handling' 'durable retry' 'We selected durable retry over best effort to preserve outstanding work across outages.'

expected_calls=5
[ -z "$only_case" ] || expected_calls=1
[ "$live_calls" -eq "$expected_calls" ] || fail "live suite exceeded its fixed call budget: $live_calls (expected $expected_calls)"
if [ "$semantic_failures" -gt 0 ]; then
  echo "User Learning live semantic acceptance failed: provider=$provider model=$model calls=$live_calls semanticFailures=$semantic_failures" >&2
  exit 1
fi
echo "User Learning live semantic acceptance passed: provider=$provider model=$model calls=$live_calls (maximum 5)"
echo "Bounded live diagnostics retained: $artifact_root"
