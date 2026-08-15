#!/usr/bin/env bash
# Explicit, local-only pilot feedback. No runtime event, network, or model API.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
command=""; format="markdown"; output_dir=""; json=false
run_reference=""; finding_reference=""; profile=""; disposition=""; changed_before_pr=""; reviewer_find_anyway=""; reason_category=""; note=""
. "$root/scripts/lib/json.sh"
. "$root/scripts/lib/run-identity.sh"

usage() { cat <<'USAGE'
Usage:
  mana pilot-feedback record --run-ref <stable-ref> --finding-ref <stable-ref> --profile <workflow> --disposition <accepted|rejected|ignored|deferred> --changed-before-pr <yes|no|unknown> --would-reviewer-find-anyway <yes|maybe|no|unknown> --reason <bug|architecture|contract|test|style/noise|duplicate|false-positive|insufficient-evidence|other> [--note <bounded-note>] [--output <workspace-dir>] [--json]
  mana pilot-feedback report [--json|--csv|--markdown] [--output <workspace-dir>]

Records explicit human feedback only. Data stays under .mana/pilot-feedback by
default; it is never uploaded, sent to a model, or added to runtime telemetry.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }

safe_reference() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]; }
safe_profile() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ ]]; }
valid_enum() { case "|$3|" in *"|$2|"*) ;; *) fail "invalid $1: $2";; esac; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; shift 2;;
    --output) output_dir="${2:-}"; shift 2;;
    --run-ref) run_reference="${2:-}"; shift 2;;
    --finding-ref) finding_reference="${2:-}"; shift 2;;
    --profile) profile="${2:-}"; shift 2;;
    --disposition) disposition="${2:-}"; shift 2;;
    --changed-before-pr) changed_before_pr="${2:-}"; shift 2;;
    --would-reviewer-find-anyway) reviewer_find_anyway="${2:-}"; shift 2;;
    --reason) reason_category="${2:-}"; shift 2;;
    --note) note="${2:-}"; shift 2;;
    --json) json=true; format="json"; shift;;
    --csv) format="csv"; shift;;
    --markdown) format="markdown"; shift;;
    --help|-h) usage; exit 0;;
    record|report) [ -z "$command" ] || fail 'only one command is allowed'; command="$1"; shift;;
    *) fail "unknown argument: $1";;
  esac
done
[ -n "$command" ] || { usage >&2; exit 2; }
mana_json_require
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail "project root not found: $project_root"

resolve_output() {
  local requested="$1" candidate parent
  if [ -z "$requested" ]; then candidate="$project_root/.mana/pilot-feedback"; else
    case "$requested" in /*) candidate="$requested";; *) candidate="$project_root/$requested";; esac
  fi
  parent="$(dirname "$candidate")"
  mkdir -p "$parent" || fail 'could not create pilot-feedback parent directory'
  parent="$(cd "$parent" && pwd -P)"
  candidate="$parent/$(basename "$candidate")"
  case "$candidate" in "$project_root"/.mana/*) ;; *) fail 'pilot feedback output must remain under project .mana/' ;; esac
  [ ! -L "$candidate" ] || fail 'pilot feedback output must not be a symlink'
  printf '%s' "$candidate"
}

feedback_validate() {
  jq -e '
    def only($allowed): (keys - $allowed | length) == 0;
    type == "object" and only(["schemaVersion","feedbackId","recordedAt","runReference","findingReference","profile","disposition","changedBeforePr","wouldReviewerFindAnyway","reasonCategory","note","capture"]) and
    .schemaVersion == "mana.pilot-feedback/v1" and
    (.feedbackId|type == "string" and test("^pilot-feedback-[0-9a-f]{64}$")) and
    (.recordedAt|type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T")) and
    (.runReference|type == "string" and test("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")) and
    (.findingReference|type == "string" and test("^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")) and
    (.profile|type == "string" and test("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")) and
    (.disposition|IN("accepted","rejected","ignored","deferred")) and
    (.changedBeforePr|IN("yes","no","unknown")) and
    (.wouldReviewerFindAnyway|IN("yes","maybe","no","unknown")) and
    (.reasonCategory|IN("bug","architecture","contract","test","style/noise","duplicate","false-positive","insufficient-evidence","other")) and
    (.note|type == "string" and (length <= 280) and test("[\\r\\n]"; "n") | not) and
    (.capture == {processor:"mana-pilot-feedback-v1",modelCalls:0,networkCalls:0})
  ' "$1" >/dev/null
}

contains_sensitive_content() {
  local lower="${1,,}"
  [[ "$lower" == *http://* || "$lower" == *https://* || "$lower" == *www.* || "$lower" == *'@'* || "$lower" == *token* || "$lower" == *secret* || "$lower" == *password* || "$lower" == *credential* || "$lower" == *authorization* || "$lower" == *bearer* || "$lower" == *'```'* ]]
}

record() {
  local state records payload identity record_file tmp
  safe_reference "$run_reference" || fail '--run-ref must be a stable opaque reference (1-128 safe characters)'
  safe_reference "$finding_reference" || fail '--finding-ref must be a stable opaque reference (1-128 safe characters)'
  safe_profile "$profile" || fail '--profile must be a safe workflow identifier'
  valid_enum disposition "$disposition" 'accepted|rejected|ignored|deferred'
  valid_enum changed-before-pr "$changed_before_pr" 'yes|no|unknown'
  valid_enum would-reviewer-find-anyway "$reviewer_find_anyway" 'yes|maybe|no|unknown'
  valid_enum reason "$reason_category" 'bug|architecture|contract|test|style/noise|duplicate|false-positive|insufficient-evidence|other'
  [ "${#note}" -le 280 ] || fail '--note must not exceed 280 characters'
  [[ "$note" != *$'\n'* && "$note" != *$'\r'* ]] || fail '--note must be one line'
  contains_sensitive_content "$note" && fail '--note may not contain URLs, identities, source fences, or credential-like content'
  state="$(resolve_output "$output_dir")"; records="$state/records"; mkdir -p "$records"
  identity="$(printf '%s\037%s' "$run_reference" "$finding_reference" | shasum -a 256 | awk '{print $1}')"
  record_file="$records/pilot-feedback-$identity.json"
  [ ! -L "$records" ] || fail 'pilot feedback records directory must not be a symlink'
  [ ! -e "$record_file" ] || fail "duplicate feedback record for immutable run/finding/profile reference: ${record_file#$project_root/}"
  payload="$(jq -cn --arg id "pilot-feedback-$identity" --arg recorded "$(mana_generated_at)" --arg run "$run_reference" --arg finding "$finding_reference" --arg profile "$profile" --arg disposition "$disposition" --arg changed "$changed_before_pr" --arg reviewer "$reviewer_find_anyway" --arg reason "$reason_category" --arg note "$note" '{schemaVersion:"mana.pilot-feedback/v1",feedbackId:$id,recordedAt:$recorded,runReference:$run,findingReference:$finding,profile:$profile,disposition:$disposition,changedBeforePr:$changed,wouldReviewerFindAnyway:$reviewer,reasonCategory:$reason,note:$note,capture:{processor:"mana-pilot-feedback-v1",modelCalls:0,networkCalls:0}}')"
  tmp="$(mktemp "$records/.pilot-feedback.tmp.XXXXXX")" || fail 'could not create feedback staging file'
  umask 077; printf '%s\n' "$payload" > "$tmp"
  feedback_validate "$tmp" || { rm -f "$tmp"; fail 'internal feedback contract validation failed'; }
  mv "$tmp" "$record_file"
  if [ "$json" = true ]; then jq -cn --arg file "${record_file#$project_root/}" --arg id "pilot-feedback-$identity" '{schemaVersion:"mana.pilot-feedback-record-result/v1",status:"recorded",feedbackId:$id,record:$file,modelCalls:0,networkCalls:0,telemetryWritten:false}'; else echo "Recorded pilot feedback: ${record_file#$project_root/}"; fi
}

aggregate_json() {
  local state="$1" records valid file total
  records="$state/records"; valid="$state/.valid-records.jsonl"
  : > "$valid"
  if [ -d "$records" ]; then
    while IFS= read -r file; do
      feedback_validate "$file" || fail "malformed pilot feedback: ${file#$project_root/}"
      jq -c . "$file" >> "$valid"
    done < <(find "$records" -type f -name 'pilot-feedback-*.json' ! -type l -print | LC_ALL=C sort)
  fi
  total="$(wc -l < "$valid" | tr -d ' ')"
  jq -s --arg generated "$(mana_generated_at)" '
    def rate($n; $d): if $d == 0 then null else ($n / $d) end;
    . as $records | ($records|length) as $total |
    ([.[]|.runReference]|unique|length) as $runs |
    ([.[]|select(.disposition=="accepted")]|length) as $accepted |
    ([.[]|select(.disposition=="rejected" or .reasonCategory=="false-positive")]|length) as $rejected |
    ([.[]|select(.changedBeforePr=="yes")]|length) as $changed |
    ([.[]|select(.changedBeforePr=="unknown" or .wouldReviewerFindAnyway=="unknown")]|length) as $unknown |
    {schemaVersion:"mana.pilot-feedback-aggregate/v1",generatedAt:$generated,source:{recordsScanned:$total,invalidRecords:0,rawFeedbackExported:false},denominators:{runsReviewed:$runs,findingsDispositioned:$total,feedbackFields:($total*2)},metrics:{accepted:{count:$accepted,rate:rate($accepted;$total)},falsePositiveOrRejected:{count:$rejected,rate:rate($rejected;$total)},changesMadeBeforePr:{count:$changed,rate:rate($changed;$total)},unknownOrMissingFeedback:{count:$unknown,rate:rate($unknown;($total*2))}},dispositions:{accepted:([.[]|select(.disposition=="accepted")]|length),rejected:([.[]|select(.disposition=="rejected")]|length),ignored:([.[]|select(.disposition=="ignored")]|length),deferred:([.[]|select(.disposition=="deferred")]|length)},reasonCategories:(group_by(.reasonCategory)|map({key:.[0].reasonCategory,value:length})|from_entries),limitations:["Human-filled pilot feedback is optional; missing records cannot be inferred without an external reviewed-run inventory.","Rates describe dispositioned findings only and do not estimate time saved, ROI, correctness, or individual performance."]}
  ' "$valid"
  rm -f "$valid"
}

report() {
  local state aggregate out tmp
  state="$(resolve_output "$output_dir")"; mkdir -p "$state/records" "$state/reports"
  [ ! -L "$state/records" ] && [ ! -L "$state/reports" ] || fail 'pilot feedback directories must not be symlinks'
  find "$state/records" -type l -print -quit | grep -q . && fail 'pilot feedback records must not contain symlinks'
  aggregate="$(aggregate_json "$state")"
  umask 077; tmp="$(mktemp "$state/reports/.pilot-feedback-report.tmp.XXXXXX")" || fail 'could not create report staging file'
  case "$format" in
    json) out="$state/reports/pilot-feedback-aggregate.json"; printf '%s\n' "$aggregate" > "$tmp";;
    csv) out="$state/reports/pilot-feedback-aggregate.csv"; { echo 'metric,count,denominator,rate'; printf '%s' "$aggregate" | jq -r '["runs_reviewed",.denominators.runsReviewed,.denominators.runsReviewed,1], ["findings_dispositioned",.denominators.findingsDispositioned,.denominators.findingsDispositioned,1], ["accepted_rate",.metrics.accepted.count,.denominators.findingsDispositioned,(.metrics.accepted.rate // "")], ["false_positive_or_rejected_rate",.metrics.falsePositiveOrRejected.count,.denominators.findingsDispositioned,(.metrics.falsePositiveOrRejected.rate // "")], ["changes_made_before_pr",.metrics.changesMadeBeforePr.count,.denominators.findingsDispositioned,(.metrics.changesMadeBeforePr.rate // "")], ["unknown_or_missing_feedback",.metrics.unknownOrMissingFeedback.count,.denominators.feedbackFields,(.metrics.unknownOrMissingFeedback.rate // "")] | @csv'; } > "$tmp";;
    markdown) out="$state/reports/pilot-feedback-aggregate.md"; { echo '# Mana Pilot Feedback Aggregate'; echo; echo '| Metric | Count | Denominator | Rate |'; echo '|---|---:|---:|---:|'; printf '%s' "$aggregate" | jq -r 'def row($n;$c;$d;$r): "| " + $n + " | " + ($c|tostring) + " | " + ($d|tostring) + " | " + (if $r == null then "n/a" else ($r|tostring) end) + " |"; row("Runs reviewed";.denominators.runsReviewed;.denominators.runsReviewed;1), row("Findings dispositioned";.denominators.findingsDispositioned;.denominators.findingsDispositioned;1), row("Accepted";.metrics.accepted.count;.denominators.findingsDispositioned;.metrics.accepted.rate), row("False-positive or rejected";.metrics.falsePositiveOrRejected.count;.denominators.findingsDispositioned;.metrics.falsePositiveOrRejected.rate), row("Changes made before PR";.metrics.changesMadeBeforePr.count;.denominators.findingsDispositioned;.metrics.changesMadeBeforePr.rate), row("Unknown/missing feedback fields";.metrics.unknownOrMissingFeedback.count;.denominators.feedbackFields;.metrics.unknownOrMissingFeedback.rate)'; echo; echo '## Limits'; printf '%s' "$aggregate" | jq -r '.limitations[] | "- " + .'; } > "$tmp";;
    *) fail 'unsupported report format';;
  esac
  mv "$tmp" "$out"
  if [ "$json" = true ] && [ "$format" = json ]; then cat "$out"; else echo "Pilot feedback report: ${out#$project_root/}"; fi
}

case "$command" in record) record;; report) report;; esac
