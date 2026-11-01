#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-private-review.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
workspace="$project/.mana/features/REVIEW"
mkdir -p "$workspace/evidence" "$tmp/scratch" "$tmp/cache"
printf 'workspace_type: feature\nworkspace_id: REVIEW\nfeature_id: REVIEW\n' > "$workspace/manifest.yaml"
printf '# Real application evidence\n' > "$workspace/evidence/application-evidence.md"
# A similar file outside the reserved receipt pattern must stay visible.
printf '{"executionId":"legitimate"}\n' > "$workspace/evidence/story-start-discovery-failure-document.json"
cat > "$tmp/stub" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' 'PRIVATE_TEST_SENTINEL' >&2
exit 7
EOF
chmod 700 "$tmp/stub"
export TMPDIR="$tmp/scratch" MANA_CACHE_HOME="$tmp/cache" MANA_USER_LEARNING_ALLOW_STUB=true MANA_USER_LEARNING_STUB_COMMAND="$tmp/stub"
. "$root/scripts/lib/provider-dispatch.sh"
. "$root/scripts/lib/story-start-scope-v2.sh"
package="$root/tests/fixtures/story-start-scope-v2/discovery/compact-package.json"
for attempt in 1 2; do
  if mana_story_start_scope_v2_run_public stub deterministic "$package" "$workspace"; then echo 'unexpected success' >&2; exit 1; fi
  jq -e '.status=="needs_owner_review" and .failedPhase=="discovery" and .artifactRefs.implementationPlan==null' "$workspace/validation/story-start-scope-run-v2.json" >/dev/null
  [ ! -f "$workspace/planning/story-start-implementation-plan-v2.json" ]
done
[ "$(find "$workspace/.mana-story-start-discovery" -name 'story-start-discovery-failure-????????????????????????????????.json' | wc -l | tr -d ' ')" = 2 ]
[ -z "$(find "$tmp/scratch" -mindepth 1 -print -quit)" ]
session="$project/.mana/sessions/SESSION"
mkdir -p "$session/evidence"
printf 'workspace_type: session\nworkspace_id: SESSION\n' > "$session/manifest.yaml"
printf '7\t0\t0\t0\t1\t2\t3\n' > "$tmp/status.tsv"
python3 "$root/scripts/lib/story-start-discovery-receipt.py" publish "$tmp/status.tsv" "$session" bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb not_reached UNKNOWN_FAILURE
if "$root/scripts/mana-inspect.sh" --project-root "$project" artifact workspace:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb --json > /dev/null 2>&1; then exit 1; fi
for receipt in "$workspace"/.mana-story-start-discovery/story-start-discovery-failure-????????????????????????????????.json; do
  jq -e '.failureCategory=="PROVIDER_EXIT_NONZERO" and .supervisor.exitCode==7' "$receipt" >/dev/null
  python3 -c 'import os, stat, sys; sys.exit(stat.S_IMODE(os.stat(sys.argv[1]).st_mode) != 0o600)' "$receipt"
  ! grep -q PRIVATE_TEST_SENTINEL "$receipt"
  id="$(jq -r .executionId "$receipt")"
  if "$root/scripts/mana-inspect.sh" --project-root "$project" artifact "workspace:$id" --json > /dev/null 2>&1; then exit 1; fi
  rel="${receipt#"$project"/}"
  if "$root/scripts/mana-inspect.sh" --project-root "$project" artifact "$rel" --json > /dev/null 2>&1; then exit 1; fi
  if "$root/scripts/mana-inspect.sh" --project-root "$project" source "$rel" --json > /dev/null 2>&1; then exit 1; fi
done
inspect="$root/scripts/mana-inspect.sh"
"$inspect" --project-root "$project" artifacts --json > "$tmp/artifacts.json"
"$inspect" --project-root "$project" work-item feature:REVIEW --json > "$tmp/work-item.json"
"$inspect" --project-root "$project" work-items --json > "$tmp/work-items.json"
"$inspect" --project-root "$project" activity --json > "$tmp/activity.json"
"$inspect" --project-root "$project" semantic-snapshot --include-supporting --json > "$tmp/snapshot.json"
! grep -q 'story-start-discovery-failure-[0-9a-f]\{32\}\.json' "$tmp/artifacts.json" "$tmp/work-item.json" "$tmp/work-items.json" "$tmp/activity.json" "$tmp/snapshot.json"
jq -e 'any(.artifacts[]; .path|endswith("/evidence/application-evidence.md")) and any(.artifacts[]; .path|endswith("/evidence/story-start-discovery-failure-document.json"))' "$tmp/artifacts.json" >/dev/null
jq -e '.sections[] | select(.section_id=="evidence") | any(.artifacts[]; .path|endswith("/evidence/application-evidence.md"))' "$tmp/work-item.json" >/dev/null
python3 "$root/scripts/mana-catalog.py" --project-root "$project" build --json > "$tmp/catalog-build.json"
python3 - "$tmp/cache" <<'PY'
import pathlib, sqlite3, sys
files = list(pathlib.Path(sys.argv[1]).rglob('*.sqlite3'))
assert len(files) == 1
with sqlite3.connect(files[0]) as db:
    paths = [row[0] for row in db.execute('select path from entries')]
assert any(p.endswith('/evidence/application-evidence.md') for p in paths)
assert any(p.endswith('/evidence/story-start-discovery-failure-document.json') for p in paths)
assert not any('story-start-discovery-failure-' in p and len(p.rsplit('-',1)[-1]) == 37 for p in paths)
with sqlite3.connect(files[0]) as db:
    source = db.execute('select * from entries limit 1').fetchone()
    legacy = '.mana/features/REVIEW/evidence/story-start-discovery-failure-' + 'a'*32 + '.json'
    db.execute('insert into entries values (' + ','.join('?' * len(source)) + ')', (legacy, *source[1:]))
PY
python3 "$root/scripts/mana-catalog.py" --project-root "$project" status --json > "$tmp/stale.json"
jq -e '.freshness=="stale" and .reason=="path-set-changed"' "$tmp/stale.json" >/dev/null
python3 "$root/scripts/mana-catalog.py" --project-root "$project" build --json > /dev/null
python3 - "$tmp/cache" "$workspace" <<'PY'
import pathlib, sqlite3, sys
with sqlite3.connect(next(pathlib.Path(sys.argv[1]).rglob('*.sqlite3'))) as db:
    assert not db.execute("select 1 from entries where path like '%story-start-discovery-failure-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json'").fetchall()
workspace = pathlib.Path(sys.argv[2])
marker = workspace / 'validation/story-start-scope-run-v2.json'
assert all(marker.stat().st_mtime_ns >= p.stat().st_mtime_ns for p in (workspace / '.mana-story-start-discovery').glob('story-start-discovery-failure-' + '?'*32 + '.json'))
PY
echo 'Private Discovery receipts excluded from Inspect and derived catalog (offline)'
