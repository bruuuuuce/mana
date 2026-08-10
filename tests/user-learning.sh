#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-learning.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

project="$tmp/project"
state="$tmp/host-owned-state"
context_source="$tmp/external-user-context"
log="$project/.mana/features/PROJ-1/decisions/developer-choice-log.md"
mkdir -p "$(dirname "$log")" "$project/.mana/user-context" "$project/.mana/learning/candidates" "$context_source"
printf '%s\n' 'external User Context fixture' > "$context_source/preferences.md"
printf '%s\n' 'read-only User Context fixture' > "$project/.mana/user-context/preferences.md"
chmod 0444 "$project/.mana/user-context/preferences.md"
printf '%s\n' '{"schemaVersion":"2","candidateId":"learning-12345678","status":"candidate","evidenceReferences":[],"executions":[]}' > "$project/.mana/learning/candidates/learning-12345678.json"
cat > "$log" <<'EOF'
# Developer Choice Log

## Choices

| Date | Story | Area | Question Or Choice | Developer Answer | Evidence | Confirmed By | Status | Follow-Up |
|---|---|---|---|---|---|---|---|---|
| 2026-08-01 | PROJ-1 | persistence | Which database should the service use? | PostgreSQL | docs/adr/001.md | developer@example.test | confirmed | src/config/database.yml |
| 2026-08-01 | PROJ-1 | persistence | Which database should the service use? | PostgreSQL | docs/adr/001.md | developer@example.test | confirmed | src/config/database.yml |
| 2026-08-03 | PROJ-1 | cache | Which cache should the service use? | Redis | docs/adr/003.md | developer@example.test | asked | |
| 2026-08-04 | PROJ-1 | owner | Who approves the message format? | Architecture owner | docs/adr/004.md | | needs_owner_review | |
| malformed | row | that | lacks | required | choice | cells | confirmed |
EOF
git -C "$project" init -q
git -C "$project" remote add origin 'https://example.test/mana/identity-project.git'

project_before="$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
context_before="$(find "$context_source" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
first="$(MANA_USER_STATE_HOME="$state" MANA_USER_CONTEXT_ROOT="$context_source" "$root/scripts/mana-user-learning.sh" --project-root "$project" capture --json)"
printf '%s' "$first" | jq -e '.modelCalls == 0 and .discoveredSignals == 2 and .newlyStored == 2 and .alreadyKnown == 0 and .skipped == 3' >/dev/null || fail 'capture counts or zero-model contract wrong'
printf '%s' "$first" | jq -e '.skippedItems[] | select(.reason == "status_not_eligible")' >/dev/null || fail 'unresolved choice was not reported as skipped'
printf '%s' "$first" | jq -e '.skippedItems[] | select(.reason == "malformed_choice_row")' >/dev/null || fail 'malformed source was not rejected safely'

signals_dir="$state/user-learning/signals"
signal_count="$(find "$signals_dir" -type f -name 'user-choice-*.json' | wc -l | tr -d ' ')"
[ "$signal_count" = 2 ] || fail 'two distinct confirmed decisions did not create two signals'
first_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$signals_dir"/user-choice-*.json)"
[ -n "$first_id" ] || fail 'signal identity missing'
first_signal="$signals_dir/$first_id.json"
jq -e '.schemaVersion == "2" and .signalId == $id and .sourceDecision.status == "confirmed" and .sourceDecision.choiceOrdinal == 1 and .sourceDecision.subject != "" and .sourceDecision.confirmedChoice != "" and .provenance.sourceArtifact.path == ".mana/features/PROJ-1/decisions/developer-choice-log.md" and (.provenance.evidence | index("docs/adr/001.md")) and .capture.modelCalls == 0' --arg id "$first_id" "$first_signal" >/dev/null || fail 'signal provenance did not survive serialization'
second_decision_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 2) | .signalId' "$signals_dir"/user-choice-*.json)"
[ "$first_id" != "$second_decision_id" ] || fail 'separate_decisions_different_id: identical decision text collapsed into one signal'
jq -s 'map(.sourceDecision | del(.reference, .line, .choiceOrdinal)) | .[0] == .[1]' "$signals_dir"/user-choice-*.json | grep -qx true || fail 'payload_equality_does_not_imply_identity_equality regression fixture is not equivalent'

# The same repository decision in an equivalent checkout and a different host
# state root must retain its identity; neither absolute checkout path nor state
# location participates in the key when repository identity is available.
equivalent="$tmp/equivalent-checkout"
equivalent_log="$equivalent/.mana/features/PROJ-1/decisions/developer-choice-log.md"
mkdir -p "$(dirname "$equivalent_log")"
cp "$log" "$equivalent_log"
git -C "$equivalent" init -q
git -C "$equivalent" remote add origin 'https://example.test/mana/identity-project.git'
equivalent_result="$(MANA_USER_STATE_HOME="$tmp/equivalent-state" MANA_TEST_GENERATED_AT='2031-01-01T00:00:00Z' "$root/scripts/mana-user-learning.sh" --project-root "$equivalent" capture --json)"
equivalent_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$tmp/equivalent-state/user-learning/signals"/user-choice-*.json)"
[ "$first_id" = "$equivalent_id" ] || fail 'equivalent_environment_same_project_same_id: checkout path or state root altered identity'
printf '%s' "$equivalent_result" | jq -e '.modelCalls == 0 and .newlyStored == 2' >/dev/null || fail 'equivalent environment capture failed'

second="$(MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" capture --json)"
printf '%s' "$second" | jq -e '.discoveredSignals == 2 and .newlyStored == 0 and .alreadyKnown == 2' >/dev/null || fail 'repeated capture was not idempotent'
second_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$signals_dir"/user-choice-*.json)"
[ "$first_id" = "$second_id" ] || fail 'same_source_decision_same_id: signal identity was not stable'
[ "$project_before" = "$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'external-state capture mutated the project repository'

# The answer preserves a selected option while its explanation changes. The
# source row is the same governed decision, so preserve-first capture must not
# create a second signal.
awk '{gsub(/PostgreSQL \| docs\/adr\/001\.md/, "PostgreSQL (rationale clarified) | docs/adr/001.md"); print}' "$log" > "$tmp/choice-log-edited" && mv "$tmp/choice-log-edited" "$log"
project_before_metadata_capture="$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
rationale_edit="$(MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" capture --json)"
printf '%s' "$rationale_edit" | jq -e '.newlyStored == 0 and .alreadyKnown == 2' >/dev/null || fail 'rationale_edit_same_id: descriptive edit created new evidence'
rationale_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$signals_dir"/user-choice-*.json)"
[ "$first_id" = "$rationale_id" ] || fail 'rationale_edit_same_id: identity changed'
[ "$(find "$signals_dir" -type f -name 'user-choice-*.json' | wc -l | tr -d ' ')" = 2 ] || fail 'payload_mutation_did_not_create_duplicate_historical_evidence'

metadata_change="$(MANA_TEST_GENERATED_AT='2030-01-01T00:00:00Z' MANA_USER_STATE_HOME="$state" "$root/scripts/mana-user-learning.sh" --project-root "$project" capture --json)"
printf '%s' "$metadata_change" | jq -e '.newlyStored == 0 and .alreadyKnown == 2' >/dev/null || fail 'capture_metadata_change_same_id: metadata created new evidence'
metadata_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$signals_dir"/user-choice-*.json)"
[ "$first_id" = "$metadata_id" ] || fail 'capture_metadata_change_same_id: identity changed'

project_after="$(find "$project" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)"
[ "$project_before_metadata_capture" = "$project_after" ] || fail 'external-state capture mutated the project repository'
[ "$(cat "$project/.mana/user-context/preferences.md")" = 'read-only User Context fixture' ] || fail 'capture modified User Context'
[ "$context_before" = "$(find "$context_source" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort)" ] || fail 'capture modified the external User Context source'
[ -f "$project/.mana/learning/candidates/learning-12345678.json" ] || fail 'capture changed existing project learning lifecycle'
[ ! -e "$project/.mana/user-learning" ] || fail 'capture created a project-local User Learning store'

if MANA_USER_STATE_HOME="$project/.mana/state" "$root/scripts/mana-user-learning.sh" --project-root "$project" capture >/dev/null 2>&1; then
  fail 'project-local state location was accepted'
fi

# The linked-project wrapper exposes the additive command without changing the
# existing `mana learning` lifecycle.
linked="$tmp/linked-project"
mkdir -p "$linked/.mana/features/PROJ-2/decisions"
"$root/scripts/bootstrap-project.sh" --project-root "$linked" --mana-root "$root" --no-jira-env >/dev/null
cp "$log" "$linked/.mana/features/PROJ-2/decisions/developer-choice-log.md"
git -C "$linked" init -q
git -C "$linked" remote add origin 'https://example.test/mana/different-project.git'
wrapper_result="$(MANA_USER_STATE_HOME="$tmp/wrapper-state" "$linked/mana" user-learning capture --json)"
printf '%s' "$wrapper_result" | jq -e '.command == "capture" and .modelCalls == 0 and .newlyStored == 2' >/dev/null || fail 'linked mana wrapper did not dispatch User Learning capture'
wrapper_id="$(jq -r 'select(.sourceDecision.choiceOrdinal == 1) | .signalId' "$tmp/wrapper-state/user-learning/signals"/user-choice-*.json)"
[ "$first_id" != "$wrapper_id" ] || fail 'same_decision_text_different_projects_different_id: cross-project evidence was deduplicated'

echo 'User Learning tests passed'
