#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-human-feedback.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project"
command="$root/scripts/mana-human-feedback.sh"
fail() { echo "FAIL: $*" >&2; exit 1; }

# A read on a project with no feedback state is pure: it must not create .mana.
empty="$tmp/empty"
mkdir -p "$empty"
"$command" --project-root "$empty" list --artifact-id file:report.md --artifact-revision sha256:empty --json > "$tmp/empty-list.json"
jq -e '.threads == []' "$tmp/empty-list.json" >/dev/null || fail 'empty read did not return an empty collection'
[ ! -e "$empty/.mana" ] || fail 'list created feedback storage'

linked="$tmp/linked"
mkdir -p "$linked"
ln -s "$tmp" "$linked/.mana"
if "$command" --project-root "$linked" create --artifact-id file:hostile.md --artifact-revision sha256:hostile --author Ada --body hostile --idempotency-key hostile-symlink --json >/dev/null 2>&1; then
  fail 'writer accepted a symlinked .mana directory'
fi

create=(create --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --author Ada --body 'Choose option B.' --idempotency-key operation-create --json)
"$command" --project-root "$project" "${create[@]}" > "$tmp/created.json"
jq -e '.schemaVersion=="mana.human-feedback.result/v1" and .status=="persisted" and .threadRevision=="1" and .planUpdate=="not_requested"' "$tmp/created.json" >/dev/null || fail 'create result contract failed'
thread="$(jq -r .threadId "$tmp/created.json")"
file="$project/.mana/human-feedback/threads/$thread.json"
[ -f "$file" ] || fail 'thread record missing'
jq -e '.schemaVersion=="mana.human-feedback.thread/v1" and .target.artifactId=="file:.mana/features/PAY-42/planning/story-start-scope-v2.md" and .target.sectionId=="decisions-required" and .state=="open" and (.entries|length)==1' "$file" >/dev/null || fail 'thread record contract failed'

"$command" --project-root "$project" create --artifact-id file:unicode.md --artifact-revision sha256:unicode --author 'Ada Rossi 👩🏽‍💻' --body $'Prima riga\nUltima riga\n' --idempotency-key unicode-author --json > "$tmp/unicode.json"
unicode_thread="$(jq -r .threadId "$tmp/unicode.json")"
jq -e --arg id "$unicode_thread" '.threadId==$id' "$project/.mana/human-feedback/threads/$unicode_thread.json" >/dev/null || fail 'unicode author thread missing'
jq -e '.entries[0].author=="Ada Rossi 👩🏽‍💻" and .entries[0].body=="Prima riga\nUltima riga\n"' "$project/.mana/human-feedback/threads/$unicode_thread.json" >/dev/null || fail 'unicode author or body roundtrip failed'

# Crash after canonical record publication but before the receipt is committed:
# the same idempotency request must recover one result, not add a second entry.
crash_create=(create --artifact-id file:crash.md --artifact-revision sha256:crash --author Ada --body 'recover after ACK loss' --idempotency-key crash-after-record --json)
if MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_RECORD=1 "$command" --project-root "$project" "${crash_create[@]}" > "$tmp/crash-first.json" 2> "$tmp/crash-first.err"; then
  fail 'fault injection did not terminate after record publication'
fi
"$command" --project-root "$project" operation --operation-id crash-after-record --json > "$tmp/crash-operation.json"
jq -e '.status=="outcome_to_verify"' "$tmp/crash-operation.json" >/dev/null || fail 'prepared crash receipt was not observable'
# SIGKILL intentionally leaves the mkdir lock behind. Its explicit removal is
# the documented administrative recovery action before an idempotent retry.
rmdir "$project/.mana/human-feedback/locks/write.lock"
"$command" --project-root "$project" "${crash_create[@]}" > "$tmp/crash-retry.json"
jq -e '.schemaVersion=="mana.human-feedback.result/v1" and .threadRevision=="1"' "$tmp/crash-retry.json" >/dev/null || fail 'crash retry did not recover result'
"$command" --project-root "$project" operation --operation-id crash-after-record --json > "$tmp/crash-committed.json"
jq -e '.status=="persisted"' "$tmp/crash-committed.json" >/dev/null || fail 'crash retry did not finalize receipt'
crash_thread="$(jq -r .threadId "$tmp/crash-retry.json")"
jq -e '(.entries|length)==1' "$project/.mana/human-feedback/threads/$crash_thread.json" >/dev/null || fail 'crash retry duplicated the comment'

# Crash after journal preparation but before the record: the retry must not
# claim success from the prepared receipt; it completes the missing commit.
prepare_create=(create --artifact-id file:prepare.md --artifact-revision sha256:prepare --author Ada --body 'recover before commit' --idempotency-key crash-after-prepare --json)
if MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_PREPARE=1 "$command" --project-root "$project" "${prepare_create[@]}" > "$tmp/prepare-first.json" 2> "$tmp/prepare-first.err"; then
  fail 'prepare fault injection did not terminate'
fi
"$command" --project-root "$project" operation --operation-id crash-after-prepare --json > "$tmp/prepare-operation.json"
jq -e '.status=="outcome_to_verify"' "$tmp/prepare-operation.json" >/dev/null || fail 'prepared pre-commit receipt was not observable'
rmdir "$project/.mana/human-feedback/locks/write.lock"
"$command" --project-root "$project" "${prepare_create[@]}" > "$tmp/prepare-retry.json"
prepare_thread="$(jq -r .threadId "$tmp/prepare-retry.json")"
jq -e '.threadRevision=="1"' "$tmp/prepare-retry.json" >/dev/null || fail 'prepared retry did not commit the record'
jq -e '(.entries|length)==1 and .entries[0].body=="recover before commit"' "$project/.mana/human-feedback/threads/$prepare_thread.json" >/dev/null || fail 'prepared retry did not publish exactly one comment'

# The target cache is deliberately marked dirty before the canonical rename.
# A crash before its refresh must expose the new thread through the canonical
# fallback, and a retry must rebuild/commit without duplicating it.
index_crash_create=(create --artifact-id file:index-crash.md --artifact-revision sha256:index-crash --author Ada --body 'recover missing index' --idempotency-key crash-before-index --json)
if MANA_HUMAN_FEEDBACK_TEST_ABORT_AFTER_CANONICAL_BEFORE_INDEX=1 "$command" --project-root "$project" "${index_crash_create[@]}" > "$tmp/index-crash-first.json" 2> "$tmp/index-crash-first.err"; then
  fail 'fault injection did not terminate before target index publication'
fi
rmdir "$project/.mana/human-feedback/locks/write.lock"
"$command" --project-root "$project" list --artifact-id file:index-crash.md --artifact-revision sha256:index-crash --json > "$tmp/index-crash-list.json"
jq -e '(.threads|length)==1 and .threads[0].entries[0].body=="recover missing index"' "$tmp/index-crash-list.json" >/dev/null || fail 'dirty target index hid canonical crash record'
"$command" --project-root "$project" "${index_crash_create[@]}" > "$tmp/index-crash-retry.json"
jq -e '.threadRevision=="1"' "$tmp/index-crash-retry.json" >/dev/null || fail 'dirty target index retry did not recover record'

"$command" --project-root "$project" "${create[@]}" > "$tmp/repeated.json"
cmp -s "$tmp/created.json" "$tmp/repeated.json" || fail 'same idempotency request did not return same result'
if "$command" --project-root "$project" create --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --author Ada --body changed --idempotency-key operation-create --json >/dev/null 2>&1; then
  fail 'idempotency key was accepted for different content'
fi

"$command" --project-root "$project" list --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json > "$tmp/list.json"
jq -e '.schemaVersion=="mana.human-feedback.threads/v1" and (.threads|length)==1 and .threads[0].threadId != null' "$tmp/list.json" >/dev/null || fail 'list did not return the thread'

# A later Story Start revision retains the canonical original target. This
# read changes no state and does not guess a section identity from Markdown.
"$command" --project-root "$project" list-history --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-two --section-id decisions-required --json > "$tmp/history.json"
jq -e --arg id "$thread" '.schemaVersion=="mana.human-feedback.thread-history/v1" and (.threads|length)==1 and .threads[0].threadId==$id and .threads[0].target.artifactRevision=="sha256:report-one" and .threads[0].linkState=="changed"' "$tmp/history.json" >/dev/null || fail 'history did not retain the changed source target'
"$command" --project-root "$project" list-history --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json > "$tmp/history-current.json"
jq -e '.threads[0].linkState=="valid"' "$tmp/history-current.json" >/dev/null || fail 'history did not mark the current source target valid'

# Stable Story Start identities are producer-owned. A missing/duplicate ID in
# the current manifest remains explicit instead of being guessed from a
# coincidentally similar rendered heading.
target_report="$project/.mana/features/PAY-42/planning/story-start-scope-v2.md"
mkdir -p "$(dirname "$target_report")"
printf '%s\n' '# Story Start Scope v2 report' '## 1. Story readiness' '## 2. Base implementation plan' > "$target_report"
target_revision="sha256:$(shasum -a 256 "$target_report" | awk '{print $1}')"
jq -cn --arg revision "$target_revision" '
  {schemaVersion:"mana.story-start.feedback-targets/v1",artifactRevision:$revision,
   sections:[
     {sectionId:"base-implementation-plan",headingIndex:3},
     {sectionId:"ambiguous",headingIndex:2},
     {sectionId:"ambiguous",headingIndex:3}
   ]}
' > "${target_report%.md}.feedback-targets-v1.json"
target_artifact='file:.mana/features/PAY-42/planning/story-start-scope-v2.md'
for section in base-implementation-plan removed ambiguous; do
  "$command" --project-root "$project" create --artifact-id "$target_artifact" --artifact-revision sha256:older-report --section-id "$section" --author Ada --body "history $section" --idempotency-key "history-$section" --json >/dev/null
done
"$command" --project-root "$project" targets --artifact-id "$target_artifact" --artifact-revision "$target_revision" --json > "$tmp/stable-targets.json"
jq -e '.schemaVersion=="mana.human-feedback.targets/v1" and .stableSections==true and (.sections|length)==3' "$tmp/stable-targets.json" >/dev/null || fail 'stable target manifest was not exposed'
"$command" --project-root "$project" list-history --artifact-id "$target_artifact" --artifact-revision "$target_revision" --section-id base-implementation-plan --json > "$tmp/stable-history.json"
jq -e '(.threads|length)==1 and .threads[0].linkState=="changed"' "$tmp/stable-history.json" >/dev/null || fail 'stable target did not preserve changed history'
"$command" --project-root "$project" list-history --artifact-id "$target_artifact" --artifact-revision "$target_revision" --section-id removed --json > "$tmp/missing-history.json"
jq -e '(.threads|length)==1 and .threads[0].linkState=="missing"' "$tmp/missing-history.json" >/dev/null || fail 'removed stable target was not marked missing'
"$command" --project-root "$project" list-history --artifact-id "$target_artifact" --artifact-revision "$target_revision" --section-id ambiguous --json > "$tmp/ambiguous-history.json"
jq -e '(.threads|length)==1 and .threads[0].linkState=="ambiguous"' "$tmp/ambiguous-history.json" >/dev/null || fail 'duplicated stable target was not marked ambiguous'

# Target indexes are an optional performance cache. A crash can leave the
# canonical record without its index, in which case reads must fall back
# without silently recreating state; a symlinked cache remains unsafe.
index_file="$(find "$project/.mana/human-feedback/indexes" -type f -name 'target_*.json' ! -type l -print | while IFS= read -r candidate; do
  if jq -e --arg id "$thread" '(.threadIds|index($id)) != null' "$candidate" >/dev/null; then
    printf '%s\n' "$candidate"
    break
  fi
done)"
[ -n "$index_file" ] || fail 'target index was not published'
rm "$index_file"
"$command" --project-root "$project" list --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json > "$tmp/list-without-index.json"
jq -e --arg id "$thread" '(.threads|length)==1 and .threads[0].threadId==$id' "$tmp/list-without-index.json" >/dev/null || fail 'missing target index hid the canonical thread'
[ ! -e "$index_file" ] || fail 'read recreated a missing target index'
ln -s "$tmp" "$index_file"
if "$command" --project-root "$project" list --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json >/dev/null 2>&1; then
  fail 'list accepted a symlinked target index'
fi
rm "$index_file"

for number in 1 2 3; do
  "$command" --project-root "$project" create --artifact-id file:pagination.md --artifact-revision sha256:page --author Ada --body "page $number" --idempotency-key "page-$number" --json >/dev/null
done
"$command" --project-root "$project" list --artifact-id file:pagination.md --artifact-revision sha256:page --limit 2 --json > "$tmp/page-one.json"
cursor="$(jq -r .nextCursor "$tmp/page-one.json")"
jq -e '.threads|length==2' "$tmp/page-one.json" >/dev/null || fail 'first thread page has wrong size'
[ "$cursor" != null ] || fail 'first thread page did not return a cursor'
"$command" --project-root "$project" list --artifact-id file:pagination.md --artifact-revision sha256:page --limit 2 --cursor "$cursor" --json > "$tmp/page-two.json"
jq -e --slurpfile first "$tmp/page-one.json" '(.threads|length)==1 and .nextCursor==null and ([.threads[].threadId] | inside($first[0].threads | map(.threadId)) | not)' "$tmp/page-two.json" >/dev/null || fail 'thread pagination duplicated or lost a page'

"$command" --project-root "$project" reply --thread-id "$thread" --thread-revision 1 --author Ada --body 'Confirmed with the team.' --idempotency-key operation-reply --json > "$tmp/replied.json"
jq -e '.threadRevision=="2" and .action=="reply"' "$tmp/replied.json" >/dev/null || fail 'reply result failed'
"$command" --project-root "$project" resolve --thread-id "$thread" --thread-revision 2 --idempotency-key operation-resolve --json > "$tmp/resolved.json"
jq -e '.threadRevision=="3" and .action=="resolve"' "$tmp/resolved.json" >/dev/null || fail 'resolve result failed'
jq -e '.state=="resolved" and (.entries|length)==2' "$file" >/dev/null || fail 'resolve did not preserve thread history'
if "$command" --project-root "$project" reopen --thread-id "$thread" --thread-revision 2 --idempotency-key stale-reopen --json > "$tmp/conflict.json" 2>/dev/null; then
  fail 'stale revision was accepted'
fi
jq -e '.schemaVersion=="mana.human-feedback.conflict/v1" and .currentRevision=="3"' "$tmp/conflict.json" >/dev/null || fail 'stale revision did not return conflict'

decision_source='.mana/features/PAY-42/planning/story-start-implementation-plan-v2.json'
mkdir -p "$project/.mana/features/PAY-42/planning"
cp "$root/contracts/story-start/scope-v2/fixtures/valid/implementation-plan-separated-scope.json" "$project/$decision_source"
"$command" --project-root "$project" decision-targets --decision-source "$decision_source" --json > "$tmp/decision-targets.json"
decision_id="$(jq -r '.decisions[0].decisionId' "$tmp/decision-targets.json")"
option_id="$(jq -r '.decisions[0].options[0].optionId' "$tmp/decision-targets.json")"
decision_source_revision="$(jq -r .sourceRevision "$tmp/decision-targets.json")"
jq -e --arg id "$decision_id" --arg option "$option_id" '.schemaVersion=="mana.human-feedback.decision-targets/v1" and any(.decisions[]; .decisionId==$id and any(.options[]; .optionId==$option))' "$tmp/decision-targets.json" >/dev/null || fail 'decision target contract failed'

"$command" --project-root "$project" decide --decision-source "$decision_source" --decision-source-revision "$decision_source_revision" --decision-id "$decision_id" --decision-revision 0 --option-id "$option_id" --author Ada --body 'Chosen after the retention review.' --idempotency-key operation-decision --json > "$tmp/decision.json"
jq -e --arg option "$option_id" '.schemaVersion=="mana.human-feedback.decision-result/v1" and .status=="recorded" and .selectedOptionId==$option and .planUpdate=="replanning_required"' "$tmp/decision.json" >/dev/null || fail 'decision result failed'
decision_file="$(find "$project/.mana/human-feedback/decisions" -type f -name 'decision_*.json' -print -quit)"
[ -n "$decision_file" ] || fail 'hashed decision record missing'
jq -e --arg id "$decision_id" --arg option "$option_id" --arg source "$decision_source" '.decisionId==$id and .source.path==$source and .revision=="1" and .selectedOptionId==$option and (.history|length)==1' "$decision_file" >/dev/null || fail 'decision history failed'
"$command" --project-root "$project" decision-state --decision-id "$decision_id" --json > "$tmp/decision-state.json"
jq -e --arg id "$decision_id" --arg option "$option_id" '.schemaVersion=="mana.human-feedback.decision-state/v1" and .decisionId==$id and .revision=="1" and .selectedOptionId==$option' "$tmp/decision-state.json" >/dev/null || fail 'decision state failed'
"$command" --project-root "$project" decision-state --decision-id decision_unknown --json > "$tmp/decision-state-unknown.json"
jq -e '.revision=="0" and .selectedOptionId==null and .history==[]' "$tmp/decision-state-unknown.json" >/dev/null || fail 'unknown decision state failed'
if "$command" --project-root "$project" decide --decision-source "$decision_source" --decision-source-revision "$decision_source_revision" --decision-id "$decision_id" --decision-revision 0 --option-id "$option_id" --author Ada --body stale --idempotency-key stale-decision --json > "$tmp/decision-conflict.json" 2>/dev/null; then
  fail 'stale decision revision was accepted'
fi
jq -e '.schemaVersion=="mana.human-feedback.conflict/v1" and .currentRevision=="1"' "$tmp/decision-conflict.json" >/dev/null || fail 'decision conflict was not reported'

if "$command" --project-root "$project" decide --decision-source "$decision_source" --decision-source-revision "$decision_source_revision" --decision-id '../outside' --decision-revision 0 --option-id "$option_id" --author Ada --body hostile --idempotency-key hostile-path --json >/dev/null 2>&1; then
  fail 'unsafe decision identifier was accepted'
fi
if "$command" --project-root "$project" decide --decision-source "$decision_source" --decision-source-revision "$decision_source_revision" --decision-id "$decision_id" --decision-revision 1 --option-id option_missing --author Ada --body hostile --idempotency-key foreign-option --json >/dev/null 2>&1; then
  fail 'foreign decision option was accepted'
fi
if "$command" --project-root "$project" decide --decision-source "$decision_source" --decision-source-revision sha256:stale --decision-id "$decision_id" --decision-revision 1 --option-id "$option_id" --author Ada --body stale --idempotency-key stale-source --json >/dev/null 2>&1; then
  fail 'stale decision source was accepted'
fi
if find "$project/.mana/human-feedback/decisions" -type f -name '*outside*' -print -quit | grep -q .; then
  fail 'logical decision identifier leaked into a path'
fi

"$command" --project-root "$project" operation --operation-id operation-create --json > "$tmp/operation.json"
jq -e '.schemaVersion=="mana.human-feedback.operation-status/v1" and .status=="persisted" and .result.threadId==$id' --arg id "$thread" "$tmp/operation.json" >/dev/null || fail 'operation lookup failed'
"$command" --project-root "$project" operation --operation-id never-created --json > "$tmp/operation-unknown.json"
jq -e '.schemaVersion=="mana.human-feedback.operation-status/v1" and .status=="unknown"' "$tmp/operation-unknown.json" >/dev/null || fail 'unknown operation lookup failed'
"$command" --project-root "$project" capabilities --json > "$tmp/capabilities.json"
jq -e '.schemaVersion=="mana.human-feedback.capabilities/v1" and (.operations|index("operation"))' "$tmp/capabilities.json" >/dev/null || fail 'capabilities contract failed'

# Two writers based on revision 3 must produce exactly one update and one conflict.
"$command" --project-root "$project" reply --thread-id "$thread" --thread-revision 3 --author Ada --body 'race first' --idempotency-key race-one --json > "$tmp/race-one.json" &
first=$!
"$command" --project-root "$project" reply --thread-id "$thread" --thread-revision 3 --author Ada --body 'race second' --idempotency-key race-two --json > "$tmp/race-two.json" 2> "$tmp/race-two.err" &
second=$!
wait "$first" || true
wait "$second" || true
accepted=0
for output in "$tmp/race-one.json" "$tmp/race-two.json"; do
  [ -s "$output" ] && jq -e '.threadRevision=="4"' "$output" >/dev/null && accepted=$((accepted + 1))
done
[ "$accepted" -eq 1 ] || fail 'concurrent writers did not produce exactly one accepted update'
jq -e '.revision=="4" and (.entries|length)==3' "$file" >/dev/null || fail 'concurrent writers lost or duplicated an entry'

# An abandoned lock must produce a typed retryable outcome, never an empty or
# free-form response. The reduced limit is test-only; production waits 30 s.
mkdir -p "$project/.mana/human-feedback/locks/write.lock"
if MANA_HUMAN_FEEDBACK_LOCK_ATTEMPTS=1 "$command" --project-root "$project" create --artifact-id file:busy.md --artifact-revision sha256:busy --author Ada --body busy --idempotency-key busy-operation --json > "$tmp/busy.json" 2> "$tmp/busy.err"; then
  fail 'abandoned lock was accepted'
fi
jq -e '.schemaVersion=="mana.human-feedback.busy/v1" and .status=="busy" and .retryable==true' "$tmp/busy.json" >/dev/null || fail 'abandoned lock did not return typed busy result'
rmdir "$project/.mana/human-feedback/locks/write.lock"

mkdir -p "$project/.mana/human-feedback/threads/external"
ln -s "$tmp" "$project/.mana/human-feedback/threads/external/link"
if "$command" --project-root "$project" list --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json >/dev/null 2>&1; then
  fail 'symlink in thread store was silently accepted'
fi
rm "$project/.mana/human-feedback/threads/external/link"
"$root/scripts/bootstrap-project.sh" --project-root "$project" --mana-root "$root" --no-jira-env >/dev/null
"$project/mana" human-feedback list --artifact-id file:.mana/features/PAY-42/planning/story-start-scope-v2.md --artifact-revision sha256:report-one --section-id decisions-required --json > "$tmp/wrapper-list.json"
jq -e '.schemaVersion=="mana.human-feedback.threads/v1" and (.threads|length)==1' "$tmp/wrapper-list.json" >/dev/null || fail 'project wrapper dispatch failed'
echo 'Mana human feedback tests passed'
