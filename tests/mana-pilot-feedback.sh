#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-pilot-feedback.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"; mkdir -p "$project"
feedback="$root/scripts/mana-pilot-feedback.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }
record() { MANA_TEST_GENERATED_AT='2026-08-12T10:00:00Z' "$feedback" --project-root "$project" record "$@"; }

[ -f "$root/docs/roadmap/m06-pilot-utility-evidence-audit.md" ] || fail 'M06 mechanism audit missing'
if record --finding-ref finding-0 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway no --reason bug >/dev/null 2>&1; then fail 'missing run reference was accepted'; fi
if record --run-ref run-0 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway no --reason bug >/dev/null 2>&1; then fail 'missing finding reference was accepted'; fi

base=(--run-ref run-42 --finding-ref finding-7 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway maybe --reason bug --note 'Added regression test')
record "${base[@]}" --json > "$tmp/record.json"
jq -e '.status=="recorded" and .modelCalls==0 and .networkCalls==0 and .telemetryWritten==false and (.feedbackId|test("^pilot-feedback-[0-9a-f]{64}$"))' "$tmp/record.json" >/dev/null || fail 'record result contract failed'
raw="$project/.mana/pilot-feedback/records/$(jq -r .feedbackId "$tmp/record.json").json"
[ -f "$raw" ] || fail 'raw feedback was not stored locally'
jq -e '.schemaVersion=="mana.pilot-feedback/v1" and .runReference=="run-42" and .findingReference=="finding-7" and .note=="Added regression test" and .capture.modelCalls==0 and .capture.networkCalls==0' "$raw" >/dev/null || fail 'raw schema content failed'
! grep -Eqi 'https?://|credential|authorization|source snippet' "$raw" || fail 'raw record contains prohibited content'

if record "${base[@]}" >/dev/null 2>&1; then fail 'duplicate record was accepted'; fi
before="$(shasum -a 256 "$raw")"
if record --run-ref run-42 --finding-ref finding-7 --profile requested-pr-review --disposition rejected --changed-before-pr no --would-reviewer-find-anyway yes --reason false-positive >/dev/null 2>&1; then fail 'immutable reference was overwritten'; fi
[ "$before" = "$(shasum -a 256 "$raw")" ] || fail 'duplicate attempt mutated record'

if record --run-ref missing --finding-ref finding-8 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway no --reason bug --note 'see https://private.invalid' >/dev/null 2>&1; then fail 'URL note was accepted'; fi
if record --run-ref missing --finding-ref finding-9 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway no --reason bug --note $'line one\nline two' >/dev/null 2>&1; then fail 'multiline note was accepted'; fi
mkdir -p "$project/.mana/external"; ln -s "$tmp" "$project/.mana/external/records"
if record --run-ref missing --finding-ref finding-10 --profile requested-pr-review --disposition accepted --changed-before-pr yes --would-reviewer-find-anyway no --reason bug --output .mana/external >/dev/null 2>&1; then fail 'symlinked records directory was accepted'; fi
rm "$project/.mana/external/records"

record --run-ref run-42 --finding-ref finding-8 --profile requested-pr-review --disposition rejected --changed-before-pr no --would-reviewer-find-anyway unknown --reason false-positive
record --run-ref run-43 --finding-ref finding-1 --profile jessica-fletcher --disposition deferred --changed-before-pr unknown --would-reviewer-find-anyway no --reason insufficient-evidence
MANA_TEST_GENERATED_AT='2026-08-12T10:01:00Z' "$feedback" --project-root "$project" report --json > "$tmp/aggregate.json"
jq -e '.schemaVersion=="mana.pilot-feedback-aggregate/v1" and .source.recordsScanned==3 and .source.rawFeedbackExported==false and .denominators.runsReviewed==2 and .denominators.findingsDispositioned==3 and .metrics.accepted.count==1 and .metrics.falsePositiveOrRejected.count==1 and .metrics.changesMadeBeforePr.count==1 and .metrics.unknownOrMissingFeedback.count==2 and .metrics.accepted.rate==(1/3)' "$tmp/aggregate.json" >/dev/null || fail 'partial aggregation contract failed'
! grep -Fq 'Added regression test' "$tmp/aggregate.json" || fail 'aggregate leaked raw note'
! grep -Fq 'run-42' "$tmp/aggregate.json" || fail 'aggregate leaked raw reference'
MANA_TEST_GENERATED_AT='2026-08-12T10:01:00Z' "$feedback" --project-root "$project" report --json > "$tmp/aggregate-two.json"
cmp -s "$tmp/aggregate.json" "$tmp/aggregate-two.json" || fail 'aggregation is not deterministic'
"$feedback" --project-root "$project" report --csv >/dev/null
"$feedback" --project-root "$project" report --markdown >/dev/null
[ -f "$project/.mana/pilot-feedback/reports/pilot-feedback-aggregate.csv" ] || fail 'CSV export missing'
[ -f "$project/.mana/pilot-feedback/reports/pilot-feedback-aggregate.md" ] || fail 'Markdown export missing'
for export_file in "$project/.mana/pilot-feedback/reports/pilot-feedback-aggregate.csv" "$project/.mana/pilot-feedback/reports/pilot-feedback-aggregate.md"; do
  ! grep -Fq 'Added regression test' "$export_file" || fail 'aggregate export leaked raw note'
  ! grep -Fq 'run-42' "$export_file" || fail 'aggregate export leaked raw reference'
done

"$root/scripts/bootstrap-project.sh" --project-root "$project" --mana-root "$root" --no-jira-env >/dev/null
"$project/mana" pilot-feedback report --json > "$tmp/wrapper-aggregate.json"
jq -e '.schemaVersion=="mana.pilot-feedback-aggregate/v1" and .source.recordsScanned==3' "$tmp/wrapper-aggregate.json" >/dev/null || fail 'wrapper dispatch failed'

zero="$tmp/zero"; mkdir -p "$zero"
MANA_TEST_GENERATED_AT='2026-08-12T10:02:00Z' "$feedback" --project-root "$zero" report --json > "$tmp/zero.json"
jq -e '.denominators.runsReviewed==0 and .denominators.findingsDispositioned==0 and .metrics.accepted.rate==null and .source.recordsScanned==0' "$tmp/zero.json" >/dev/null || fail 'zero-record aggregate failed'

printf '%s\n' '{bad json' > "$project/.mana/pilot-feedback/records/pilot-feedback-malformed.json"
if "$feedback" --project-root "$project" report --json >/dev/null 2>&1; then fail 'malformed feedback was silently aggregated'; fi
rm "$project/.mana/pilot-feedback/records/pilot-feedback-malformed.json"

for schema in "$root/docs/standards/mana-pilot-feedback-v1.schema.json" "$root/docs/standards/mana-pilot-feedback-aggregate-v1.schema.json"; do jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and .type=="object"' "$schema" >/dev/null || fail "invalid schema: $schema"; done
echo 'Mana pilot feedback tests passed'
