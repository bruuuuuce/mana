#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"
mkdir -p "$tmp/workspace" "$tmp/scratch"
export TMPDIR="$tmp/scratch" MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$tmp/stub"
export RECEIPT_TEST_COUNT="$tmp/count"
export RECEIPT_TEST_SECRET='sensitive-token-unique-example'
cat > "$tmp/stub" <<'EOF'
#!/usr/bin/env bash
printf 'call\n' >> "$RECEIPT_TEST_COUNT"
printf '%s\n' "$RECEIPT_TEST_SECRET" >&2
if [ "${RECEIPT_TEST_MODE}" = exit ]; then exit 7; fi
if [ "${RECEIPT_TEST_MODE}" = success ]; then
  last=""; for arg in "$@"; do last="$arg"; done
  case "$last" in
    *COMPACT_DISCOVERY_PACKAGE*) cat "$RECEIPT_FIXTURE_ROOT/discovery/provider-output.json" ;;
    *COMPACT_DISCOVERY_V2*) cat "$RECEIPT_FIXTURE_ROOT/triage/provider-output.json" ;;
    *SCOPE_TRIAGE_V2*) cat "$RECEIPT_FIXTURE_ROOT/planner/provider-output.json" ;;
    *) exit 1 ;;
  esac
  exit
fi
printf '%s\n' '{"secret":"sensitive-token-unique-example"}'
EOF
chmod 700 "$tmp/stub"

assert_final_marker() {
  python3 - "$1" <<'PYMARKER'
import pathlib, sys
workspace = pathlib.Path(sys.argv[1])
marker = workspace / 'validation/story-start-scope-run-v2.json'
assert all(marker.stat().st_mtime_ns >= p.stat().st_mtime_ns for p in workspace.rglob('*') if p.is_file() and not p.is_symlink())
PYMARKER
}

package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
export RECEIPT_TEST_MODE=exit
if mana_story_start_scope_v2_run_public stub deterministic "$package" "$tmp/workspace"; then exit 1; fi
assert_final_marker "$tmp/workspace"
mapfile_check="$(find "$tmp/workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-*.json' -type f | wc -l | tr -d ' ')"
[ "$mapfile_check" = 1 ]
first="$(find "$tmp/workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-*.json' -type f)"
jq -e '.failureCategory=="PROVIDER_EXIT_NONZERO" and .supervisor.exitCode==7 and .schemaValidation=="not_reached"' "$first" >/dev/null
! grep -q "$RECEIPT_TEST_SECRET" "$first"
jq -e '.status=="needs_owner_review" and .failedPhase=="discovery" and .artifactRefs.implementationPlan==null' "$tmp/workspace/validation/story-start-scope-run-v2.json" >/dev/null
[ ! -e "$tmp/workspace/planning/story-start-implementation-plan-v2.json" ]
export RECEIPT_TEST_MODE=schema
if mana_story_start_scope_v2_run_public stub deterministic "$package" "$tmp/workspace"; then exit 1; fi
assert_final_marker "$tmp/workspace"
[ "$(find "$tmp/workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-*.json' -type f | wc -l | tr -d ' ')" = 2 ]
second="$(find "$tmp/workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-*.json' -type f ! -path "$first")"
jq -e '.failureCategory=="PROVIDER_OUTPUT_SCHEMA_INVALID" and .schemaValidation=="failed"' "$second" >/dev/null
! grep -q "$RECEIPT_TEST_SECRET" "$second"
[ "$(jq -r .executionId "$first")" != "$(jq -r .executionId "$second")" ]
[ -z "$(find "$tmp/scratch" -mindepth 1 -print -quit)" ]
[ ! -e "$tmp/workspace/planning/story-start-implementation-plan-v2.json" ]
export RECEIPT_TEST_MODE=success RECEIPT_FIXTURE_ROOT="$root/tests/fixtures/story-start-scope-v2"
mana_story_start_scope_v2_run_public stub deterministic "$package" "$tmp/workspace"
assert_final_marker "$tmp/workspace"
jq -e '.status=="passed" and .failedPhase=="none"' "$tmp/workspace/validation/story-start-scope-run-v2.json" >/dev/null
[ "$(find "$tmp/workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-*.json' -type f | wc -l | tr -d ' ')" = 2 ]
[ -z "$(find "$tmp/scratch" -mindepth 1 -print -quit)" ]
[ "$(wc -l < "$RECEIPT_TEST_COUNT" | tr -d ' ')" = 5 ]
# A previous receipt cannot stand in for a failed publication on a later run.
mkdir -p "$tmp/failed-publication"
cp -R "$tmp/workspace/.mana-story-start-discovery" "$tmp/archived-diagnostics"
ln -s "$tmp/archived-diagnostics" "$tmp/failed-publication/.mana-story-start-discovery"
cp "$first" "$tmp/first-receipt-copy"
export RECEIPT_TEST_MODE=exit
if mana_story_start_scope_v2_run_public stub deterministic "$package" "$tmp/failed-publication"; then exit 1; fi
assert_final_marker "$tmp/failed-publication"
[ "$(wc -l < "$RECEIPT_TEST_COUNT" | tr -d ' ')" = 6 ]
[ "$(find "$tmp/archived-diagnostics" -type f | wc -l | tr -d ' ')" = 2 ]
cmp "$tmp/first-receipt-copy" "$tmp/archived-diagnostics/$(basename "$first")"
jq -e '.status=="needs_owner_review" and .artifactRefs.implementationPlan==null' "$tmp/failed-publication/validation/story-start-scope-run-v2.json" >/dev/null
[ ! -e "$tmp/failed-publication/planning/story-start-implementation-plan-v2.json" ]
[ -z "$(find "$tmp/scratch" -mindepth 1 -print -quit)" ]
echo 'Discovery receipt integration tests passed (offline stubs, real Perl supervisor)'
