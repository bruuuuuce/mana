#!/usr/bin/env bash
# Local, explicit human comments for Mana artifacts. Generated reports remain
# immutable; this command stores separate, versioned contribution records.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
project_root="$(pwd)"
command=""; artifact_id=""; artifact_revision=""; section_id=""; thread_id=""; thread_revision=""; decision_id=""; decision_revision=""; option_id=""; decision_source=""; decision_source_revision=""; body=""; author=""; idempotency_key=""; operation_id=""; thread_cursor=""; page_limit="100"; request_stdin=false; json=false
. "$root/scripts/lib/json.sh"

usage() { cat <<'USAGE'
Usage:
  mana human-feedback list --artifact-id <id> --artifact-revision <revision> [--section-id <id>] [--cursor <thread-id>] [--limit 1..200] --json
  mana human-feedback list-history --artifact-id <id> --artifact-revision <current-revision> [--section-id <id>] [--cursor <thread-id>] [--limit 1..200] --json
  mana human-feedback targets --artifact-id <id> --artifact-revision <current-revision> --json
  mana human-feedback create --artifact-id <id> --artifact-revision <revision> [--section-id <id>] --author <declared-author> --body <markdown> --idempotency-key <key> --json
  mana human-feedback reply --thread-id <id> --thread-revision <revision> --author <declared-author> --body <markdown> --idempotency-key <key> --json
  mana human-feedback resolve|reopen --thread-id <id> --thread-revision <revision> --idempotency-key <key> --json
  mana human-feedback decision-targets --decision-source <project-relative-plan.json> --json
  mana human-feedback decision-state --decision-id <id> --json
  mana human-feedback decide --decision-source <project-relative-plan.json> --decision-source-revision <sha256:...> --decision-id <id> --decision-revision <revision> --option-id <id> --author <declared-author> --body <rationale> --idempotency-key <key> --json
  mana human-feedback operation --operation-id <idempotency-key> --json

All records remain local under .mana/human-feedback/.  The command makes no
network or model call and never rewrites the artifact named by --artifact-id.

Clients may replace the named request fields with --request-stdin. Its JSON
object accepts only artifactId, artifactRevision, sectionId, threadId,
threadRevision, decisionId, decisionRevision, optionId, author, body, and
idempotencyKey.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }
busy() {
  jq -cn '{schemaVersion:"mana.human-feedback.busy/v1",status:"busy",retryable:true}'
  exit 75
}
safe_id() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$ ]] || return 1
  case "/$1/" in *'/../'*|*'//'*|*/./*) return 1;; esac
}
safe_key() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; shift 2;;
    --artifact-id) artifact_id="${2:-}"; shift 2;;
    --artifact-revision) artifact_revision="${2:-}"; shift 2;;
    --section-id) section_id="${2:-}"; shift 2;;
    --thread-id) thread_id="${2:-}"; shift 2;;
    --thread-revision) thread_revision="${2:-}"; shift 2;;
    --decision-id) decision_id="${2:-}"; shift 2;;
    --decision-revision) decision_revision="${2:-}"; shift 2;;
    --option-id) option_id="${2:-}"; shift 2;;
    --decision-source) decision_source="${2:-}"; shift 2;;
    --decision-source-revision) decision_source_revision="${2:-}"; shift 2;;
    --author) author="${2:-}"; shift 2;;
    --body) body="${2:-}"; shift 2;;
    --idempotency-key) idempotency_key="${2:-}"; shift 2;;
    --operation-id) operation_id="${2:-}"; shift 2;;
    --cursor) thread_cursor="${2:-}"; shift 2;;
    --limit) page_limit="${2:-}"; shift 2;;
    --request-stdin) request_stdin=true; shift;;
    --json) json=true; shift;;
    create|list|list-history|targets|reply|resolve|reopen|decide|decision-targets|decision-state|operation|capabilities) [ -z "$command" ] || fail 'only one command is allowed'; command="$1"; shift;;
    --help|-h) usage; exit 0;;
    *) fail "unknown argument: $1";;
  esac
done
[ -n "$command" ] || { usage >&2; exit 2; }
[ "$json" = true ] || fail '--json is required'
mana_json_require
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail 'project root is unreadable'
if [ "$request_stdin" = true ]; then
  request="$(cat)"
  printf '%s' "$request" | jq -e '
    type == "object" and
    (keys - ["artifactId","artifactRevision","sectionId","threadId","threadRevision","decisionId","decisionRevision","optionId","decisionSource","decisionSourceRevision","author","body","idempotencyKey","cursor","limit"] | length) == 0 and
    all(.[]; type == "string")
  ' >/dev/null || fail '--request-stdin must be a JSON object with only string request fields'
  artifact_id="$(printf '%s' "$request" | jq -r '.artifactId // empty')"
  artifact_revision="$(printf '%s' "$request" | jq -r '.artifactRevision // empty')"
  section_id="$(printf '%s' "$request" | jq -r '.sectionId // empty')"
  thread_id="$(printf '%s' "$request" | jq -r '.threadId // empty')"
  thread_revision="$(printf '%s' "$request" | jq -r '.threadRevision // empty')"
  decision_id="$(printf '%s' "$request" | jq -r '.decisionId // empty')"
  decision_revision="$(printf '%s' "$request" | jq -r '.decisionRevision // empty')"
  option_id="$(printf '%s' "$request" | jq -r '.optionId // empty')"
  decision_source="$(printf '%s' "$request" | jq -r '.decisionSource // empty')"
  decision_source_revision="$(printf '%s' "$request" | jq -r '.decisionSourceRevision // empty')"
  author="$(printf '%s' "$request" | jq -r '.author // empty')"
  # Command substitution strips trailing newlines. Append a sentinel while
  # decoding then remove it so Markdown bodies round-trip byte-for-byte.
  body="$(printf '%s' "$request" | jq -r '.body // empty | . + "\u0001"')"
  body="${body%$'\001'}"
  idempotency_key="$(printf '%s' "$request" | jq -r '.idempotencyKey // empty')"
  thread_cursor="$(printf '%s' "$request" | jq -r '.cursor // empty')"
  page_limit="$(printf '%s' "$request" | jq -r '.limit // "100"')"
fi
state="$project_root/.mana/human-feedback"

# Read operations deliberately do not create .mana or any feedback directory.
# Writers take one project-scoped lock.  The state is a small local journal and
# correctness matters more than parallel throughput; distinct projects remain
# independent.  mkdir is available on macOS, Linux and Windows shells.
ensure_state() {
  [ ! -L "$project_root/.mana" ] || fail '.mana must not be a symlink'
  [ ! -e "$project_root/.mana" ] || [ -d "$project_root/.mana" ] || fail '.mana must be a directory'
  [ ! -e "$state" ] || { [ -d "$state" ] && [ ! -L "$state" ]; } || fail 'human-feedback storage must be a directory, not a symlink'
  mkdir -p "$state/threads" "$state/decisions" "$state/operations" "$state/indexes" "$state/locks"
  [ ! -L "$project_root/.mana" ] && [ ! -L "$state" ] && [ ! -L "$state/threads" ] && [ ! -L "$state/decisions" ] && [ ! -L "$state/operations" ] && [ ! -L "$state/indexes" ] && [ ! -L "$state/locks" ] || fail 'human-feedback storage must not be a symlink'
}
assert_existing_state_safe() {
  [ ! -e "$state" ] && return 0
  [ -d "$state" ] && [ ! -L "$state" ] || fail 'human-feedback storage must be a directory, not a symlink'
  for directory in threads decisions operations indexes locks; do
    [ ! -e "$state/$directory" ] || { [ -d "$state/$directory" ] && [ ! -L "$state/$directory" ]; } || fail "human-feedback $directory storage is unsafe"
  done
}
lock_dir=""
release_lock() { [ -z "$lock_dir" ] || rmdir "$lock_dir" 2>/dev/null || true; lock_dir=""; }
acquire_lock() {
  local attempts=0 limit="${MANA_HUMAN_FEEDBACK_LOCK_ATTEMPTS:-3000}"
  [[ "$limit" =~ ^[1-9][0-9]*$ ]] || fail 'MANA_HUMAN_FEEDBACK_LOCK_ATTEMPTS must be a positive integer'
  ensure_state
  lock_dir="$state/locks/write.lock"
  while ! mkdir "$lock_dir" 2>/dev/null; do
    attempts=$((attempts + 1))
    # A write can include several atomic journal/record publications. Wait long
    # enough for a competing writer to reach its revision check and receive a
    # structured conflict instead of failing spuriously at the lock boundary.
    [ "$attempts" -lt "$limit" ] || busy
    sleep 0.01
  done
  trap release_lock EXIT INT TERM
}

validate_body() {
  [ -n "$body" ] || fail '--body is required'
  [ "$(printf %s "$body" | wc -c | tr -d ' ')" -le 65536 ] || fail '--body exceeds 65536 UTF-8 bytes'
}
validate_author() {
  [ -n "$author" ] || fail '--author is required'
  [ "$(printf %s "$author" | wc -c | tr -d ' ')" -le 128 ] || fail '--author exceeds 128 UTF-8 bytes'
  case "$author" in *$'\n'*|*$'\r'*|*$'\t'*) fail '--author must not contain line or tab controls';; esac
}
validate_key() { safe_key "$idempotency_key" || fail '--idempotency-key must be a safe 1-128 character key'; }
validate_key_for() { safe_key "$1" || fail '--operation-id must be a safe 1-128 character key'; }
thread_file() { printf '%s/threads/%s.json' "$state" "$1"; }
target_index_file() {
  local target_key
  target_key="$(hash "$1\037$2\037$3")"
  printf '%s/indexes/target_%s.json' "$state" "$target_key"
}
# Decision IDs are logical producer identifiers, never filesystem components.
decision_file() { printf '%s/decisions/decision_%s.json' "$state" "$(hash "$1")"; }
operation_file() { printf '%s/operations/%s.json' "$state" "$1"; }
hash() { if command -v sha256sum >/dev/null 2>&1; then printf '%s' "$1" | sha256sum | awk '{print $1}'; else printf '%s' "$1" | shasum -a 256 | awk '{print $1}'; fi; }
hash_file() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi; }
recorded_at() { date -u +%Y-%m-%dT%H:%M:%SZ; }
test_abort_after_record() {
  # Test-only crash boundary: production never sets this variable. SIGKILL
  # deliberately skips the EXIT trap to model process termination after the
  # canonical rename and before the operation receipt is finalized.
  [ "${MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_RECORD:-}" = 1 ] || return 0
  kill -KILL "$$"
}
test_abort_after_canonical_before_index() {
  [ "${MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_CANONICAL_BEFORE_INDEX:-}" = 1 ] || return 0
  kill -KILL "$$"
}
test_abort_after_prepare() {
  [ "${MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_PREPARE:-}" = 1 ] || return 0
  kill -KILL "$$"
}

decision_source_file() {
  case "$decision_source" in ''|/*|.mana|*'//'|../*|*/../*|*/..|..) fail '--decision-source must be a safe project-relative path';; esac
  case "/$decision_source/" in *'/../'*|*'/./'*) fail '--decision-source must be a safe project-relative path';; esac
  local source="$project_root/$decision_source" resolved
  [ -f "$source" ] && [ ! -L "$source" ] || fail 'decision source is unavailable or unsafe'
  resolved="$(cd "$(dirname "$source")" && pwd -P)/$(basename "$source")"
  case "$resolved" in "$project_root"/*) printf '%s' "$resolved";; *) fail 'decision source escapes the project root';; esac
}

decision_targets() {
  local source actual
  source="$(decision_source_file)"
  actual="sha256:$(hash_file "$source")"
  jq -e '.schemaVersion=="mana.story-start.implementation-plan/v2" and (.decisionRegister|type=="array")' "$source" >/dev/null || fail 'decision source is not a valid Story Start v2 implementation plan'
  jq -c --arg path "$decision_source" --arg revision "$actual" '{schemaVersion:"mana.human-feedback.decision-targets/v1",sourcePath:$path,sourceRevision:$revision,decisions:[.decisionRegister[]|{decisionId:.id,question:.question,status:.status,options:[.options[]|{optionId:.id,label:.label,summary:.summary}]}]}' "$source"
}

decision_state() {
  safe_id "$decision_id" || fail '--decision-id must be safe'
  assert_existing_state_safe
  local file
  file="$(decision_file "$decision_id")"
  if [ ! -e "$file" ]; then
    jq -cn --arg id "$decision_id" '{schemaVersion:"mana.human-feedback.decision-state/v1",decisionId:$id,revision:"0",selectedOptionId:null,history:[]}'
    return
  fi
  [ -f "$file" ] && [ ! -L "$file" ] || fail 'decision record is unsafe'
  jq -e --arg id "$decision_id" '.schemaVersion=="mana.human-feedback.decision/v1" and .decisionId==$id and (.revision|type=="string") and (.history|type=="array")' "$file" >/dev/null || fail 'decision record is malformed'
  jq -c '{schemaVersion:"mana.human-feedback.decision-state/v1",decisionId:.decisionId,revision:.revision,selectedOptionId:.selectedOptionId,history:.history}' "$file"
}

validate_thread_file() {
  jq -e '
    type == "object" and .schemaVersion == "mana.human-feedback.thread/v1" and
    (.threadId|type == "string" and test("^thread_[0-9a-f]{64}$")) and
    (.revision|type == "string" and test("^[0-9]+$")) and
    (.target.artifactId|type == "string") and (.target.artifactRevision|type == "string") and
    (.state|IN("open","resolved")) and (.entries|type == "array") and
    all(.entries[]; (.entryId|type == "string") and (.author|type == "string") and (.body|type == "string") and (.kind|IN("comment","reply")))
  ' "$1" >/dev/null
}

validate_target_index() {
  local file="$1" artifact="$2" revision="$3" section="$4"
  jq -e --arg artifact "$artifact" --arg revision "$revision" --arg section "$section" '
    type == "object" and .schemaVersion == "mana.human-feedback.target-index/v1" and
    .target.artifactId == $artifact and .target.artifactRevision == $revision and
    ((.target.sectionId // "") == $section) and
    (.threadIds|type == "array") and
    all(.threadIds[]; type == "string" and test("^thread_[0-9a-f]{64}$")) and
    (.threadIds == (.threadIds | unique | sort))
  ' "$file" >/dev/null
}

index_ready_file() { printf '%s/indexes/.target-index-v1-ready.json' "$state"; }

target_indexes_ready() {
  local ready
  ready="$(index_ready_file)"
  [ -e "$ready" ] || return 1
  [ -f "$ready" ] && [ ! -L "$ready" ] || fail 'target index readiness record is unsafe'
  jq -e '.schemaVersion=="mana.human-feedback.target-index-set/v1" and .status=="ready"' "$ready" >/dev/null || fail 'target index readiness record is malformed'
}

mark_target_indexes_dirty() {
  # Remove readiness before the canonical rename. If the process dies at any
  # later point, readers fall back to canonical files until a writer rebuilds.
  rm -f "$(index_ready_file)"
}

mark_target_indexes_ready() {
  local ready temp
  ready="$(index_ready_file)"
  temp="$(mktemp "$state/indexes/.human-feedback.tmp.XXXXXX")"
  jq -cn '{schemaVersion:"mana.human-feedback.target-index-set/v1",status:"ready"}' > "$temp"
  mv "$temp" "$ready"
}

write_target_index_record() {
  local artifact="$1" revision="$2" section="$3" id="$4" file temp ids
  file="$(target_index_file "$artifact" "$revision" "$section")"
  if [ -e "$file" ]; then
    [ -f "$file" ] && [ ! -L "$file" ] || fail 'target index is unsafe'
    validate_target_index "$file" "$artifact" "$revision" "$section" || fail 'target index is malformed'
    ids="$(jq -c --arg id "$id" '.threadIds + [$id] | unique | sort' "$file")"
  else
    ids="$(jq -cn --arg id "$id" '[$id]')"
  fi
  temp="$(mktemp "$state/indexes/.human-feedback.tmp.XXXXXX")"
  jq -cn --arg artifact "$artifact" --arg revision "$revision" --arg section "$section" --argjson ids "$ids" '
    {schemaVersion:"mana.human-feedback.target-index/v1",
     target:{artifactId:$artifact,artifactRevision:$revision,sectionId:(if $section=="" then null else $section end)},
     threadIds:$ids}' > "$temp"
  mv "$temp" "$file"
}

rebuild_target_indexes() {
  # Migration/recovery path for legacy or interrupted cache state. It runs
  # under the existing writer lock and only becomes visible once readiness is
  # atomically published; readers therefore never trust a partial rebuild.
  local candidate artifact revision section id
  find "$state/threads" -type l -print -quit | grep -q . && fail 'thread storage must not contain symlinks'
  while IFS= read -r candidate; do
    validate_thread_file "$candidate" || fail "malformed thread record: ${candidate#$project_root/}"
    IFS=$'\t' read -r artifact revision section id < <(jq -r '[.target.artifactId,.target.artifactRevision,(.target.sectionId // ""),.threadId]|@tsv' "$candidate")
    write_target_index_record "$artifact" "$revision" "$section" "$id"
  done < <(find "$state/threads" -type f -name 'thread_*.json' ! -type l -print | LC_ALL=C sort)
  mark_target_indexes_ready
}

ensure_target_indexes() {
  target_indexes_ready && return
  rebuild_target_indexes
}

write_operation() {
  local key="$1" request_digest="$2" result="$3" phase="${4:-committed}" temp
  temp="$(mktemp "$state/operations/.human-feedback.tmp.XXXXXX")"
  jq -cn --arg key "$key" --arg digest "$request_digest" --arg phase "$phase" --argjson result "$result" '{schemaVersion:"mana.human-feedback.operation/v1",operationId:$key,requestDigest:$digest,phase:$phase,result:$result}' > "$temp"
  mv "$temp" "$(operation_file "$key")"
}

idempotent_result() {
  local digest="$1" file actual
  file="$(operation_file "$idempotency_key")"
  [ -e "$file" ] || return 1
  [ ! -L "$file" ] || fail 'operation record must not be a symlink'
  actual="$(jq -r '.requestDigest // empty' "$file")"
  [ "$actual" = "$digest" ] || return 2
  jq -e '.schemaVersion=="mana.human-feedback.operation/v1" and (.phase|IN("prepared","committed")) and (.result|type=="object")' "$file" >/dev/null || fail 'operation record is malformed'
  jq -c . "$file"
}
prepared_result_is_published() {
  local result="$1" id revision option file
  id="$(jq -r '.threadId // empty' <<<"$result")"
  if [ -n "$id" ]; then
    revision="$(jq -r '.threadRevision // empty' <<<"$result")"
    file="$(thread_file "$id")"
    [ -f "$file" ] && [ ! -L "$file" ] && validate_thread_file "$file" &&
      [ "$(jq -r .revision "$file")" = "$revision" ]
    return
  fi
  id="$(jq -r '.decisionId // empty' <<<"$result")"
  [ -n "$id" ] || return 1
  revision="$(jq -r '.decisionRevision // empty' <<<"$result")"
  option="$(jq -r '.selectedOptionId // empty' <<<"$result")"
  file="$(decision_file "$id")"
  [ -f "$file" ] && [ ! -L "$file" ] &&
    jq -e --arg id "$id" --arg revision "$revision" --arg option "$option" \
      '.schemaVersion=="mana.human-feedback.decision/v1" and .decisionId==$id and .revision==$revision and .selectedOptionId==$option' \
      "$file" >/dev/null
}

operation() {
  validate_key_for "$operation_id"
  assert_existing_state_safe
  file="$(operation_file "$operation_id")"
  if [ ! -e "$file" ]; then
    jq -cn --arg id "$operation_id" '{schemaVersion:"mana.human-feedback.operation-status/v1",operationId:$id,status:"unknown"}'
    return
  fi
  [ -f "$file" ] && [ ! -L "$file" ] || fail 'operation record is unsafe'
  jq -c '{schemaVersion:"mana.human-feedback.operation-status/v1",operationId:.operationId,status:(if .phase=="committed" then "persisted" else "outcome_to_verify" end),result:.result}' "$file"
}

capabilities() {
  assert_existing_state_safe
  jq -cn '{schemaVersion:"mana.human-feedback.capabilities/v1",operations:["list","list-history","targets","create","reply","resolve","reopen","decision-targets","decision-state","decide","operation"],threadPagination:true,historyAcrossRevisions:true,stableArtifactTargets:true,decisionTargets:true,artifactTargets:"producer-validated-by-caller",storage:"local-project"}'
}

# Story Start publishes this manifest beside its report. Its stable section IDs
# come from the producer schema; heading positions are only locators within
# this exact report revision. Other/legacy Markdown deliberately has no
# section-target capability rather than guessing from a rendered heading.
feedback_targets_manifest() {
  local relative document manifest actual
  case "$artifact_id" in file:*) relative="${artifact_id#file:}";; *) return 1;; esac
  case "$relative" in ''|/*|.|..|../*|*/../*|*'//'*) return 1;; esac
  document="$project_root/$relative"
  [ "$(basename "$document")" = story-start-scope-v2.md ] || return 1
  [ -f "$document" ] && [ ! -L "$document" ] || return 1
  manifest="${document%.md}.feedback-targets-v1.json"
  [ -e "$manifest" ] || return 1
  [ -f "$manifest" ] && [ ! -L "$manifest" ] || fail 'Story Start feedback target manifest is unsafe'
  actual="sha256:$(hash_file "$document")"
  [ "$actual" = "$artifact_revision" ] || return 1
  jq -e --arg revision "$artifact_revision" '
    .schemaVersion=="mana.story-start.feedback-targets/v1" and
    .artifactRevision==$revision and (.sections|type=="array") and
    all(.sections[]; (.sectionId|type=="string" and test("^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")) and (.headingIndex|type=="number" and floor==. and .>=1))
  ' "$manifest" >/dev/null || fail 'Story Start feedback target manifest is malformed'
  printf '%s' "$manifest"
}

targets() {
  safe_id "$artifact_id" || fail '--artifact-id must be safe'
  [ -n "$artifact_revision" ] || fail '--artifact-revision is required'
  local manifest
  if manifest="$(feedback_targets_manifest)"; then
    jq -c --arg artifact "$artifact_id" --arg revision "$artifact_revision" '
      {schemaVersion:"mana.human-feedback.targets/v1",artifactId:$artifact,
       artifactRevision:$revision,stableSections:true,sections:.sections}
    ' "$manifest"
  else
    jq -cn --arg artifact "$artifact_id" --arg revision "$artifact_revision" '
      {schemaVersion:"mana.human-feedback.targets/v1",artifactId:$artifact,
       artifactRevision:$revision,stableSections:false,sections:[]}'
  fi
}

history_link_state() {
  local section="$1" source_revision="$2" manifest count
  if [ -z "$section" ]; then
    [ "$source_revision" = "$artifact_revision" ] && printf valid || printf changed
    return
  fi
  if manifest="$(feedback_targets_manifest)"; then
    count="$(jq --arg section "$section" '[.sections[] | select(.sectionId==$section)] | length' "$manifest")"
    case "$count" in
      0) printf missing;;
      1) [ "$source_revision" = "$artifact_revision" ] && printf valid || printf changed;;
      *) printf ambiguous;;
    esac
    return
  fi
  [ "$source_revision" = "$artifact_revision" ] && printf valid || printf changed
}

list() {
  local entries view_revision index_file ids
  safe_id "$artifact_id" || fail '--artifact-id must be safe'
  [ -n "$artifact_revision" ] || fail '--artifact-revision is required'
  [[ "$page_limit" =~ ^([1-9][0-9]?|1[0-9]{2}|200)$ ]] || fail '--limit must be an integer from 1 to 200'
  [ -z "$thread_cursor" ] || [[ "$thread_cursor" =~ ^thread_[0-9a-f]{64}$ ]] || fail '--cursor must be a thread ID'
  assert_existing_state_safe
  [ -d "$state/threads" ] || { jq -cn '{schemaVersion:"mana.human-feedback.threads/v1",threads:[],nextCursor:null,viewRevision:"sha256:empty"}'; return; }
  find "$state/threads" -type l -print -quit | grep -q . && fail 'thread storage must not contain symlinks'
  index_file="$(target_index_file "$artifact_id" "$artifact_revision" "$section_id")"
  if target_indexes_ready && [ -e "$index_file" ]; then
    [ -f "$index_file" ] && [ ! -L "$index_file" ] || fail 'target index is unsafe'
    validate_target_index "$index_file" "$artifact_id" "$artifact_revision" "$section_id" || fail 'target index is malformed'
    ids="$(jq -r '.threadIds[]' "$index_file")"
    entries="$(while IFS= read -r thread; do
      [ -n "$thread" ] || continue
      file="$(thread_file "$thread")"
      [ -f "$file" ] && [ ! -L "$file" ] || fail 'target index references an unavailable thread'
      validate_thread_file "$file" || fail "malformed thread record: ${file#$project_root/}"
      jq -c --arg artifact "$artifact_id" --arg revision "$artifact_revision" --arg section "$section_id" '
        select(.target.artifactId == $artifact and .target.artifactRevision == $revision and (.target.sectionId // "") == $section)
      ' "$file"
    done <<<"$ids" | jq -s .)"
  else
    # Index publication can be interrupted after the canonical thread rename.
    # A missing index must degrade to a complete read, never hide that record.
    entries="$(find "$state/threads" -type f -name 'thread_*.json' ! -type l -print | LC_ALL=C sort | while IFS= read -r file; do
      validate_thread_file "$file" || fail "malformed thread record: ${file#$project_root/}"
      jq -c --arg artifact "$artifact_id" --arg revision "$artifact_revision" --arg section "$section_id" 'select(.target.artifactId == $artifact and .target.artifactRevision == $revision and (.target.sectionId // "") == $section)' "$file"
    done | jq -s .)"
  fi
  view_revision="sha256:$(hash "$entries")"
  jq -cn --argjson entries "$entries" --arg cursor "$thread_cursor" --argjson limit "$page_limit" --arg view "$view_revision" '
    [$entries[] | select(.threadId > $cursor)] as $remaining |
    ($remaining[:$limit]) as $page |
    {schemaVersion:"mana.human-feedback.threads/v1",threads:$page,
     nextCursor:(if ($remaining|length) > $limit then $page[-1].threadId else null end),
     viewRevision:$view}
  '
}

# A thread always preserves its original producer target. A history read may
# compare only stable IDs and revisions; it must never infer a missing or
# ambiguous section from rendered Markdown text.
list_history() {
  local entries view_revision
  safe_id "$artifact_id" || fail '--artifact-id must be safe'
  [ -n "$artifact_revision" ] || fail '--artifact-revision is required'
  [[ "$page_limit" =~ ^([1-9][0-9]?|1[0-9]{2}|200)$ ]] || fail '--limit must be an integer from 1 to 200'
  [ -z "$thread_cursor" ] || [[ "$thread_cursor" =~ ^thread_[0-9a-f]{64}$ ]] || fail '--cursor must be a thread ID'
  assert_existing_state_safe
  [ -d "$state/threads" ] || { jq -cn '{schemaVersion:"mana.human-feedback.thread-history/v1",threads:[],nextCursor:null,viewRevision:"sha256:empty"}'; return; }
  find "$state/threads" -type l -print -quit | grep -q . && fail 'thread storage must not contain symlinks'
  entries="$(find "$state/threads" -type f -name 'thread_*.json' ! -type l -print | LC_ALL=C sort | while IFS= read -r file; do
    validate_thread_file "$file" || fail "malformed thread record: ${file#$project_root/}"
    target_section="$(jq -r '.target.sectionId // ""' "$file")"
    source_revision="$(jq -r '.target.artifactRevision' "$file")"
    link_state="$(history_link_state "$target_section" "$source_revision")"
    jq -c --arg artifact "$artifact_id" --arg section "$section_id" --arg link "$link_state" '
      select(.target.artifactId == $artifact and ((.target.sectionId // "") == $section)) |
      . + {linkState:$link}
    ' "$file"
  done | jq -s .)"
  view_revision="sha256:$(hash "$entries")"
  jq -cn --argjson entries "$entries" --arg cursor "$thread_cursor" --argjson limit "$page_limit" --arg view "$view_revision" '
    [$entries[] | select(.threadId > $cursor)] as $remaining |
    ($remaining[:$limit]) as $page |
    {schemaVersion:"mana.human-feedback.thread-history/v1",threads:$page,
     nextCursor:(if ($remaining|length) > $limit then $page[-1].threadId else null end),
     viewRevision:$view}
  '
}

create() {
  local request digest id file entry result tmp
  safe_id "$artifact_id" || fail '--artifact-id must be safe'
  [ -n "$artifact_revision" ] || fail '--artifact-revision is required'
  validate_author; validate_body; validate_key
  request="$(jq -cn --arg command create --arg artifact "$artifact_id" --arg revision "$artifact_revision" --arg section "$section_id" --arg author "$author" --arg body "$body" --arg key "$idempotency_key" '{command:$command,artifact:$artifact,revision:$revision,section:$section,author:$author,body:$body,key:$key}')"
  digest="$(hash "$request")"
  acquire_lock
  ensure_target_indexes
  if operation_record="$(idempotent_result "$digest")"; then
    result="$(jq -c .result <<<"$operation_record")"
    if [ "$(jq -r .phase <<<"$operation_record")" = committed ]; then
      printf '%s\n' "$result"; return
    fi
    if prepared_result_is_published "$result"; then
      write_operation "$idempotency_key" "$digest" "$result" committed
      printf '%s\n' "$result"; return
    fi
  elif [ "$?" -eq 2 ]; then
    fail 'idempotency key was reused with different content'
  fi
  id="thread_$(hash "$artifact_id\037$artifact_revision\037$section_id\037$idempotency_key")"
  file="$(thread_file "$id")"
  entry="entry_$(hash "$id\037$body\037$author")"
  result="$(jq -cn --arg id "$id" --arg revision 1 '{schemaVersion:"mana.human-feedback.result/v1",status:"persisted",threadId:$id,threadRevision:$revision,planUpdate:"not_requested"}')"
  if [ -e "$file" ]; then
    validate_thread_file "$file" && [ "$(jq -r .threadId "$file")" = "$id" ] || fail 'thread identity collision'
    write_operation "$idempotency_key" "$digest" "$result" committed
    printf '%s\n' "$result"; return
  fi
  write_operation "$idempotency_key" "$digest" "$result" prepared
  test_abort_after_prepare
  mark_target_indexes_dirty
  tmp="$(mktemp "$state/threads/.human-feedback.tmp.XXXXXX")"
  jq -cn --arg id "$id" --arg artifact "$artifact_id" --arg revision "$artifact_revision" --arg section "$section_id" --arg entry "$entry" --arg author "$author" --arg body "$body" --arg at "$(recorded_at)" '{schemaVersion:"mana.human-feedback.thread/v1",threadId:$id,revision:"1",target:{artifactId:$artifact,artifactRevision:$revision,sectionId:(if $section=="" then null else $section end)},state:"open",entries:[{entryId:$entry,kind:"comment",author:$author,body:$body,recordedAt:$at}]}' > "$tmp"
  validate_thread_file "$tmp" || { rm -f "$tmp"; fail 'internal thread validation failed'; }
  mv "$tmp" "$file"
  test_abort_after_canonical_before_index
  write_target_index_record "$artifact_id" "$artifact_revision" "$section_id" "$id"
  mark_target_indexes_ready
  test_abort_after_record
  write_operation "$idempotency_key" "$digest" "$result" committed
  printf '%s\n' "$result"
}

mutate() {
  local action="$1" request digest file current expected next entry result tmp
  safe_id "$thread_id" || fail '--thread-id must be safe'
  [[ "$thread_id" =~ ^thread_[0-9a-f]{64}$ ]] || fail '--thread-id is invalid'
  [[ "$thread_revision" =~ ^[0-9]+$ ]] || fail '--thread-revision is required'
  validate_key
  if [ "$action" = reply ]; then validate_author; validate_body; fi
  request="$(jq -cn --arg action "$action" --arg id "$thread_id" --arg revision "$thread_revision" --arg author "$author" --arg body "$body" --arg key "$idempotency_key" '{action:$action,id:$id,revision:$revision,author:$author,body:$body,key:$key}')"
  digest="$(hash "$request")"
  acquire_lock
  if operation_record="$(idempotent_result "$digest")"; then
    result="$(jq -c .result <<<"$operation_record")"
    if [ "$(jq -r .phase <<<"$operation_record")" = committed ]; then
      printf '%s\n' "$result"; return
    fi
    if prepared_result_is_published "$result"; then
      write_operation "$idempotency_key" "$digest" "$result" committed
      printf '%s\n' "$result"; return
    fi
  elif [ "$?" -eq 2 ]; then
    fail 'idempotency key was reused with different content'
  fi
  file="$(thread_file "$thread_id")"; [ -f "$file" ] && [ ! -L "$file" ] || fail 'thread does not exist'
  validate_thread_file "$file" || fail 'thread record is malformed'
  current="$(jq -r .revision "$file")"; [ "$current" = "$thread_revision" ] || { jq -cn --arg expected "$thread_revision" --arg current "$current" '{schemaVersion:"mana.human-feedback.conflict/v1",status:"conflict",expectedRevision:$expected,currentRevision:$current}'; exit 3; }
  next="$((current + 1))"
  result="$(jq -cn --arg id "$thread_id" --arg revision "$next" --arg action "$action" '{schemaVersion:"mana.human-feedback.result/v1",status:"persisted",threadId:$id,threadRevision:$revision,action:$action,planUpdate:"not_requested"}')"
  write_operation "$idempotency_key" "$digest" "$result" prepared
  test_abort_after_prepare
  tmp="$(mktemp "$state/threads/.human-feedback.tmp.XXXXXX")"
  case "$action" in
    reply)
      entry="entry_$(hash "$thread_id\037$next\037$body\037$author")"
      jq --arg revision "$next" --arg entry "$entry" --arg author "$author" --arg body "$body" --arg at "$(recorded_at)" '.revision=$revision | .entries += [{entryId:$entry,kind:"reply",author:$author,body:$body,recordedAt:$at}]' "$file" > "$tmp";;
    resolve) jq --arg revision "$next" '.revision=$revision | .state="resolved"' "$file" > "$tmp";;
    reopen) jq --arg revision "$next" '.revision=$revision | .state="open"' "$file" > "$tmp";;
  esac
  validate_thread_file "$tmp" || { rm -f "$tmp"; fail 'internal thread validation failed'; }; mv "$tmp" "$file"
  test_abort_after_record
  write_operation "$idempotency_key" "$digest" "$result" committed
  printf '%s\n' "$result"
}

decide() {
  local request digest file current next result tmp source actual_source_revision decision_descriptor decision_story supersedes
  safe_id "$decision_id" || fail '--decision-id must be safe'
  safe_id "$option_id" || fail '--option-id must be safe'
  [[ "$decision_revision" =~ ^[0-9]+$ ]] || fail '--decision-revision is required'
  validate_author; validate_body; validate_key
  source="$(decision_source_file)"
  actual_source_revision="sha256:$(hash_file "$source")"
  [ "$decision_source_revision" = "$actual_source_revision" ] || fail 'decision source revision is stale or missing'
  jq -e --arg decision "$decision_id" --arg option "$option_id" '
    .schemaVersion=="mana.story-start.implementation-plan/v2" and
    any(.decisionRegister[]; .id==$decision and (.status=="open" or .status=="resolved") and any(.options[]; .id==$option))
  ' "$source" >/dev/null || fail 'decision or option is not available in the declared Story Start plan'
  decision_descriptor="$(jq -c --arg id "$decision_id" '.decisionRegister[] | select(.id==$id)' "$source")"
  decision_story="$(jq -r '.storyId // empty' "$source")"
  request="$(jq -cn --arg decision "$decision_id" --arg revision "$decision_revision" --arg option "$option_id" --arg source "$decision_source" --arg source_revision "$actual_source_revision" --arg author "$author" --arg body "$body" --arg key "$idempotency_key" '{decision:$decision,revision:$revision,option:$option,source:$source,sourceRevision:$source_revision,author:$author,body:$body,key:$key}')"
  digest="$(hash "$request")"
  acquire_lock
  if operation_record="$(idempotent_result "$digest")"; then
    result="$(jq -c .result <<<"$operation_record")"
    if [ "$(jq -r .phase <<<"$operation_record")" = committed ]; then
      printf '%s\n' "$result"; return
    fi
    if prepared_result_is_published "$result"; then
      write_operation "$idempotency_key" "$digest" "$result" committed
      printf '%s\n' "$result"; return
    fi
  elif [ "$?" -eq 2 ]; then
    fail 'idempotency key was reused with different content'
  fi
  file="$(decision_file "$decision_id")"
  if [ -e "$file" ]; then
    [ ! -L "$file" ] || fail 'decision record must not be a symlink'
    jq -e --arg id "$decision_id" '.schemaVersion=="mana.human-feedback.decision/v1" and .decisionId==$id and (.revision|type=="string") and (.history|type=="array")' "$file" >/dev/null || fail 'decision record is malformed'
    current="$(jq -r .revision "$file")"
    [ "$current" = "$decision_revision" ] || { jq -cn --arg expected "$decision_revision" --arg current "$current" '{schemaVersion:"mana.human-feedback.conflict/v1",status:"conflict",expectedRevision:$expected,currentRevision:$current}'; exit 3; }
    next="$((current + 1))"
    :
  else
    [ "$decision_revision" = 0 ] || fail 'new decisions require revision 0'
    next=1
    :
  fi
  supersedes="$(python3 "$root/scripts/lib/story-start-human-decisions.py" supersedes "$state/decisions" "$source" "$decision_id" "$decision_source")" || fail 'canonical decision reconciliation failed'
  result="$(jq -cn --arg id "$decision_id" --arg option "$option_id" --arg revision "$next" '{schemaVersion:"mana.human-feedback.decision-result/v1",status:"recorded",decisionId:$id,selectedOptionId:$option,decisionRevision:$revision,planUpdate:"replanning_required"}')"
  write_operation "$idempotency_key" "$digest" "$result" prepared
  test_abort_after_prepare
  tmp="$(mktemp "$state/decisions/.human-feedback.tmp.XXXXXX")"
  if [ -e "$file" ]; then
    jq --argjson supersedes "$supersedes" --argjson descriptor "$decision_descriptor" --arg story "$decision_story" --arg revision "$next" --arg option "$option_id" --arg source "$decision_source" --arg source_revision "$actual_source_revision" --arg author "$author" --arg body "$body" --arg at "$(recorded_at)" '.supersedes=$supersedes | .decision=$descriptor | .storyId=$story | .revision=$revision | .selectedOptionId=$option | .source={path:$source,revision:$source_revision} | .history += [{optionId:$option,author:$author,rationale:$body,recordedAt:$at,sourceRevision:$source_revision}]' "$file" > "$tmp"
  else
    jq -cn --argjson supersedes "$supersedes" --argjson descriptor "$decision_descriptor" --arg story "$decision_story" --arg id "$decision_id" --arg option "$option_id" --arg source "$decision_source" --arg source_revision "$actual_source_revision" --arg author "$author" --arg body "$body" --arg at "$(recorded_at)" '{schemaVersion:"mana.human-feedback.decision/v1",decisionId:$id,decision:$descriptor,storyId:$story,supersedes:$supersedes,revision:"1",source:{path:$source,revision:$source_revision},selectedOptionId:$option,history:[{optionId:$option,author:$author,rationale:$body,recordedAt:$at,sourceRevision:$source_revision}]}' > "$tmp"
  fi
  jq -e '.schemaVersion=="mana.human-feedback.decision/v1" and (.decisionId|type=="string") and (.revision|type=="string") and (.selectedOptionId|type=="string") and (.history|type=="array" and length>0)' "$tmp" >/dev/null || { rm -f "$tmp"; fail 'internal decision validation failed'; }
  mv "$tmp" "$file"
  test_abort_after_record
  write_operation "$idempotency_key" "$digest" "$result" committed
  printf '%s\n' "$result"
}

case "$command" in
  list) list;;
  list-history) list_history;;
  targets) targets;;
  operation) operation;;
  capabilities) capabilities;;
  decision-targets) decision_targets;;
  decision-state) decision_state;;
  create) create;;
  reply|resolve|reopen) mutate "$command";;
  decide) decide;;
esac
