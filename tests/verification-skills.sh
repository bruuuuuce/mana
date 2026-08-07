#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/verification.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-verification-tests.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
init_repo() {
  local project="$1"; mkdir -p "$project"; git -C "$project" init -q; git -C "$project" config user.email mana@example.invalid; git -C "$project" config user.name Mana; git -C "$project" config commit.gpgsign false; printf '.mana/\ntarget/\nbuild/\n' > "$project/.gitignore"
}
commit_all() { git -C "$1" add .; git -C "$1" commit -qm fixture; }
verify() { "$root/scripts/mana-verify.sh" --project-root "$1" "${@:2}"; }

# Existing skills remain valid and all three verification contracts are indexed.
"$root/scripts/validate-skills.sh" "$root" >/dev/null || fail 'skills validation failed'
for id in shell-syntax-verification mana-governance-regression-verification java-targeted-build-verification; do grep -A8 "id: $id" "$root/skills/index.yaml" | grep -Fq 'capability: verification' || fail "$id not indexed"; done

# Strict schema rejects malformed identity and all unknown executable vocabulary.
valid="$root/skills/shell-syntax-verification/verification.yaml"
verification_spec_validate "$valid" shell-syntax-verification || fail 'valid spec rejected'
for mutation in unknown_field wrong_id unknown_predicate unknown_adapter unknown_effect unknown_result duplicate_key oversized; do
  bad="$tmp/$mutation.yaml"
  case "$mutation" in
    unknown_field) jq '.unexpected=true' "$valid" > "$bad";;
    wrong_id) jq '.skill_id="other"' "$valid" > "$bad";;
    unknown_predicate) jq '.applicability.all[0].type="command_predicate"' "$valid" > "$bad";;
    unknown_adapter) jq '.checks[0].adapter="shell"' "$valid" > "$bad";;
    unknown_effect) jq '.checks[0].effects.source_tree="anywhere"' "$valid" > "$bad";;
    unknown_result) jq '.success.accepted_results=["ready"]' "$valid" > "$bad";;
    duplicate_key) sed 's/"schema_version": 1,/"schema_version": 999, "schema_version": 1,/' "$valid" > "$bad";;
    oversized) cp "$valid" "$bad"; printf '%070000d' 0 >> "$bad";;
  esac
  verification_spec_validate "$bad" shell-syntax-verification && fail "$mutation spec accepted"
done

# Dry-run is stable in shape and writes neither workspace nor runtime state.
shell_project="$tmp/shell pass"; init_repo "$shell_project"; mkdir -p "$shell_project/scripts"; printf '#!/usr/bin/env bash\necho before\n' > "$shell_project/scripts/check me.sh"; printf '#!/usr/bin/env bash\necho safe\n' > "$shell_project/scripts/special;name.sh"; commit_all "$shell_project"; printf '#!/usr/bin/env bash\necho after\n' > "$shell_project/scripts/check me.sh"; printf '#!/usr/bin/env bash\necho still-safe\n' > "$shell_project/scripts/special;name.sh"
plan="$(verify "$shell_project" --skill shell-syntax-verification --dry-run --explain --json)" || fail 'shell dry-run failed'
jq -e '.status=="planned" and .modelCalls==0 and (.actions|length)==2 and (.actions|any(.effectiveArgv==["bash","-n","--","scripts/check me.sh"])) and (.actions|any(.effectiveArgv==["bash","-n","--","scripts/special;name.sh"])) and (.actions|all(.targetFingerprint|length>10)) and (.selections[0].reasons|any(.detail|contains("scripts/check me.sh")))' <<<"$plan" >/dev/null || fail 'shell plan evidence incorrect'
[ ! -e "$shell_project/.mana" ] || fail 'dry-run wrote Mana state'

# Passing shell execution writes canonical evidence, bounded artifacts and zero model cost.
pass_json="$(verify "$shell_project" --skill shell-syntax-verification --json)" || fail 'valid shell verification failed'
jq -e '.schemaVersion=="1" and .kind=="verification-result" and .overallResult=="passed" and .checks[0].adapter=="bash_syntax" and .checks[0].trustOrigin=="framework_declared" and (.checks[0].targetFingerprint|length>10) and (.checks[0].actionFingerprint|length>10) and (.checks[0].executionFingerprint|length>10) and (.checks[0].inputDigest|length>10) and (.checks[0].executable.digest|length>10) and .checks[0].timedOut==false and .cost.modelCalls==0 and .cost.inputTokens==0 and .cost.outputTokens==0 and .judgment==null' <<<"$pass_json" >/dev/null || fail 'pass result envelope incorrect'
result_path="$(find "$shell_project/.mana" -path '*/evidence/verification/*/result.json' -type f | tail -n1)"; [ -f "$result_path" ] || fail 'result evidence missing'; [ -f "$(dirname "$result_path")/summary.md" ] || fail 'summary missing'
verification_result_validate "$result_path" || fail 'canonical result validation failed'; jq 'del(.checks[0].targetFingerprint)' "$result_path" > "$tmp/malformed-result.json"; verification_result_validate "$tmp/malformed-result.json" && fail 'malformed result envelope was accepted'
jq '.checks[0].deduplicated=true' "$result_path" > "$tmp/malformed-dedup-result.json"; verification_result_validate "$tmp/malformed-dedup-result.json" && fail 'ambiguous deduplication provenance was accepted'
jq '.checks += [.checks[0]]' "$result_path" > "$tmp/duplicate-check-result.json"; verification_result_validate "$tmp/duplicate-check-result.json" && fail 'duplicate check identity was accepted'
[ "$(stat -f '%Lp' "$result_path" 2>/dev/null || stat -c '%a' "$result_path")" = 600 ] || fail 'result permissions are not private'
runtime_file="$(find "$shell_project/.mana/runtime/events" -name '*.jsonl' -type f | tail -n1)"; grep -Fq '"eventType":"verification.started"' "$runtime_file" || fail 'verification runtime start missing'; grep -Fq '"eventType":"evidence.created"' "$runtime_file" || fail 'verification evidence link missing'; ! grep -Eqi 'secret-value|prompt|model response' "$runtime_file" || fail 'runtime event leaked output'

# Syntax failure remains evidence and preserves the parser excerpt.
printf '#!/usr/bin/env bash\nif then\n' > "$shell_project/scripts/check me.sh"
if verify "$shell_project" --skill shell-syntax-verification --json > "$tmp/fail.json"; then fail 'invalid shell passed'; fi
jq -e '.overallResult=="failed" and .checks[0].result=="failed" and .checks[0].exitCode!=0 and (.checks[0].output.excerpt|length>0)' "$tmp/fail.json" >/dev/null || fail 'failure evidence incorrect'

# Explicit but irrelevant selection is not applicable and executes nothing.
irrelevant="$tmp/irrelevant"; init_repo "$irrelevant"; printf 'text\n' > "$irrelevant/README.txt"; commit_all "$irrelevant"
irrelevant_plan="$(verify "$irrelevant" --skill java-targeted-build-verification --dry-run --json)" || fail 'irrelevant dry-run failed'
jq -e '.selections[0].applicability=="not_applicable" and (.actions|length)==0' <<<"$irrelevant_plan" >/dev/null || fail 'explicit irrelevant skill was not not_applicable'

# Multiple plausible local bases are reported rather than silently invented.
ambiguous="$tmp/ambiguous"; init_repo "$ambiguous"; printf '#!/usr/bin/env bash\ntrue\n' > "$ambiguous/check.sh"; commit_all "$ambiguous"; git -C "$ambiguous" branch main; git -C "$ambiguous" branch develop; git -C "$ambiguous" checkout -qb feature; printf '#!/usr/bin/env bash\necho changed\n' > "$ambiguous/check.sh"
if verify "$ambiguous" --skill shell-syntax-verification --dry-run --json > "$tmp/ambiguous.json"; then fail 'ambiguous base was accepted'; fi
jq -e '.status=="blocked" and (.blockers|any(contains("diff base is ambiguous")))' "$tmp/ambiguous.json" >/dev/null || fail 'ambiguous base evidence missing'

# Java changes are applicable, but a derived/unapproved action is blocked.
java_project="$tmp/java"; init_repo "$java_project"; mkdir -p "$java_project/src/main/java"; printf '<project/>\n' > "$java_project/pom.xml"; printf 'class Main {}\n' > "$java_project/src/main/java/Main.java"; commit_all "$java_project"; printf 'class Main { int value; }\n' > "$java_project/src/main/java/Main.java"
if verify "$java_project" --skill java-targeted-build-verification --json > "$tmp/java-blocked.json"; then fail 'unapproved Java action executed'; fi
jq -e '.overallResult=="blocked" and .checks[0].trustOrigin=="derived" and .checks[0].result=="blocked" and (.checks[0].effectiveArgv[0]=="proposed")' "$tmp/java-blocked.json" >/dev/null || fail 'Java trust block incorrect'

# Approved Java entries use fixed argv, never the legacy command string.
mkdir -p "$java_project/.mana/global" "$tmp/java-bin"
cat > "$java_project/.mana/global/testbook.yaml" <<'EOF'
schema_version: 1
tests:
  - id: "maven-unit-test"
    kind: "unit"
    command: "mvn test"
    command_origin: "pom_or_test_layout"
    source: "pom.xml"
    prerequisites: "java_and_maven"
    environment: "local"
    execution_status: "runnable"
    safety: "normal"
    timeout_seconds: 30
    approved: true
EOF
printf '%s\n' '#!/usr/bin/env bash' 'printf approved-java' > "$tmp/java-bin/mvn"; chmod +x "$tmp/java-bin/mvn"
approved_plan="$(PATH="$tmp/java-bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --dry-run --json)" || fail 'approved Java plan failed'
jq -e '.actions[0].trustOrigin=="project_approved" and .actions[0].effectiveArgv==["mvn","test"]' <<<"$approved_plan" >/dev/null || fail 'approved Java argv not fixed'; [ ! -e "$tmp/must-not-execute" ] || fail 'legacy catalog command executed'

# The same catalog never authorizes automatic repository build execution.
auto_java_plan="$(PATH="$tmp/java-bin:$PATH" verify "$java_project" --dry-run --json)" || fail 'automatic Java plan failed'
jq -e '.actions[0].trustOrigin=="derived" and (.actions[0].target|contains("explicit-skill-invocation-required"))' <<<"$auto_java_plan" >/dev/null || fail 'automatic Java action bypassed explicit trust gate'

# Malicious or incomplete catalog command data cannot alter or authorize argv.
sed 's/command: "mvn test"/command: "mvn test; touch escaped"/' "$java_project/.mana/global/testbook.yaml" > "$tmp/malicious-testbook.yaml"; cp "$tmp/malicious-testbook.yaml" "$java_project/.mana/global/testbook.yaml"
malicious_plan="$(PATH="$tmp/java-bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --dry-run --json)" || fail 'malicious Java dry-run failed'
jq -e '.actions[0].trustOrigin=="derived" and .actions[0].effectiveArgv[0]=="proposed"' <<<"$malicious_plan" >/dev/null || fail 'malicious Java catalog authorized execution'; [ ! -e "$java_project/escaped" ] || fail 'malicious catalog command executed'
sed 's/command: "mvn test; touch escaped"/command: "mvn test"/' "$java_project/.mana/global/testbook.yaml" > "$tmp/restored-testbook.yaml"; cp "$tmp/restored-testbook.yaml" "$java_project/.mana/global/testbook.yaml"

# Repository wrappers and Gradle are allowed only when the catalog action
# exactly matches the executable selected by the adapter.
wrapper_project="$tmp/maven-wrapper"; init_repo "$wrapper_project"; mkdir -p "$wrapper_project/src/main/java" "$wrapper_project/.mana/global"; printf '<project/>\n' > "$wrapper_project/pom.xml"; printf 'class W {}\n' > "$wrapper_project/src/main/java/W.java"; printf '%s\n' '#!/usr/bin/env bash' 'printf wrapper-ran' > "$wrapper_project/mvnw"; chmod +x "$wrapper_project/mvnw"; commit_all "$wrapper_project"; printf 'class W { int x; }\n' > "$wrapper_project/src/main/java/W.java"
sed 's/command: "mvn test"/command: ".\/mvnw test"/' "$java_project/.mana/global/testbook.yaml" > "$wrapper_project/.mana/global/testbook.yaml"
verify "$wrapper_project" --skill java-targeted-build-verification --json > "$tmp/wrapper.json" || fail 'approved Maven wrapper failed'; jq -e '.checks[0].commandOrigin=="repository_script" and .checks[0].effectiveArgv==["./mvnw","test"] and .checks[0].output.stdoutBytes==11 and (.checks[0].limitations|any(contains("without an OS sandbox")))' "$tmp/wrapper.json" >/dev/null || fail 'Maven wrapper provenance incorrect'

gradle_project="$tmp/gradle"; gradle_bin="$tmp/gradle-bin"; init_repo "$gradle_project"; mkdir -p "$gradle_project/src/main/java" "$gradle_project/.mana/global" "$gradle_bin"; printf 'plugins {}\n' > "$gradle_project/build.gradle"; printf 'class G {}\n' > "$gradle_project/src/main/java/G.java"; commit_all "$gradle_project"; printf 'class G { int x; }\n' > "$gradle_project/src/main/java/G.java"
cat > "$gradle_project/.mana/global/testbook.yaml" <<'EOF'
tests:
  - id: "gradle-unit-test"
    kind: "unit"
    command: "gradle test"
    command_origin: "build_file"
    source: "build.gradle"
    prerequisites: "java_or_gradle"
    environment: "local"
    execution_status: "runnable"
    safety: "normal"
    timeout_seconds: 30
    approved: true
EOF
printf '%s\n' '#!/usr/bin/env bash' true > "$gradle_bin/gradle"; chmod +x "$gradle_bin/gradle"; gradle_plan="$(PATH="$gradle_bin:$PATH" verify "$gradle_project" --skill java-targeted-build-verification --dry-run --json)" || fail 'system Gradle plan failed'; jq -e '.actions[0].effectiveArgv==["gradle","test"] and .actions[0].trustOrigin=="project_approved"' <<<"$gradle_plan" >/dev/null || fail 'system Gradle action incorrect'
printf '%s\n' '#!/usr/bin/env bash' true > "$gradle_project/gradlew"; chmod +x "$gradle_project/gradlew"; sed 's/command: "gradle test"/command: ".\/gradlew test"/' "$gradle_project/.mana/global/testbook.yaml" > "$tmp/gradle-wrapper-catalog"; cp "$tmp/gradle-wrapper-catalog" "$gradle_project/.mana/global/testbook.yaml"; gradle_wrapper_plan="$(verify "$gradle_project" --skill java-targeted-build-verification --dry-run --json)" || fail 'Gradle wrapper plan failed'; jq -e '.actions[0].effectiveArgv==["./gradlew","test"] and .actions[0].trustOrigin=="project_approved"' <<<"$gradle_wrapper_plan" >/dev/null || fail 'Gradle wrapper action incorrect'

# An active-workspace pointer cannot import approval from outside the project.
escape_project="$tmp/catalog-escape"; outside_workspace="$tmp/outside-workspace"; init_repo "$escape_project"; mkdir -p "$escape_project/src/main/java" "$escape_project/.mana" "$outside_workspace/tests"; printf '<project/>\n' > "$escape_project/pom.xml"; printf 'class E {}\n' > "$escape_project/src/main/java/E.java"; commit_all "$escape_project"; printf 'class E { int x; }\n' > "$escape_project/src/main/java/E.java"; printf '../../outside-workspace\n' > "$escape_project/.mana/active-workspace"; cp "$java_project/.mana/global/testbook.yaml" "$outside_workspace/tests/testbook.yaml"
escape_plan="$(verify "$escape_project" --skill java-targeted-build-verification --dry-run --json)" || fail 'catalog escape dry-run failed'; jq -e '.actions[0].trustOrigin=="derived"' <<<"$escape_plan" >/dev/null || fail 'out-of-project catalog authorized Java execution'

# A check's own exit 124 is a failure, not supervisor timeout evidence.
printf '%s\n' '#!/usr/bin/env bash' 'exit 124' > "$tmp/java-bin/mvn"; chmod +x "$tmp/java-bin/mvn"
if PATH="$tmp/java-bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --json > "$tmp/java-timeout.json"; then fail 'timeout passed'; fi
jq -e '.overallResult=="failed" and .checks[0].result=="failed" and .checks[0].exitCode==124 and .checks[0].timedOut==false and .cost.checksExecuted==1' "$tmp/java-timeout.json" >/dev/null || fail 'exit 124 was confused with timeout'

# The framework wall-clock bound also shortens a check's effective timeout.
actual_timeout_bin="$tmp/actual-timeout-bin"; mkdir -p "$actual_timeout_bin"; printf '%s\n' '#!/usr/bin/env bash' 'sleep 10' > "$actual_timeout_bin/mvn"; chmod +x "$actual_timeout_bin/mvn"
if MANA_VERIFY_MAX_SECONDS=3 PATH="$actual_timeout_bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --json > "$tmp/java-real-timeout.json"; then fail 'wall-clock timeout passed'; fi
jq -e '.overallResult=="inconclusive" and .checks[0].result=="inconclusive" and (.checks[0].timeoutSeconds>=1 and .checks[0].timeoutSeconds<=3) and .checks[0].timedOut==true and .cost.checksExecuted==1' "$tmp/java-real-timeout.json" >/dev/null || fail 'effective timeout evidence incorrect'

# Timeout terminates descendants, including children that ignore TERM.
child_supervisor="$tmp/child-supervisor"; mkdir -p "$child_supervisor"; printf '%s\n' '#!/usr/bin/env bash' 'trap "" TERM' "sleep 60 & echo \$! > '$child_supervisor/child.pid'" 'wait' > "$child_supervisor/spawn"; chmod +x "$child_supervisor/spawn"
perl "$root/scripts/lib/verification-exec.pl" --timeout 1 --output-cap 512 --stdout "$child_supervisor/stdout" --stderr "$child_supervisor/stderr" --status "$child_supervisor/status" -- "$child_supervisor/spawn"
IFS=$'\t' read -r _ child_signal child_timed_out _ _ _ _ < "$child_supervisor/status"; child_pid="$(sed -n '1p' "$child_supervisor/child.pid")"; sleep 1; ! kill -0 "$child_pid" 2>/dev/null || fail 'timeout left a child process alive'
[ "$child_timed_out" = 1 ] && [ "$child_signal" -gt 0 ] || fail 'child timeout metadata missing'

# Descendants that close both output streams are still terminated after the
# command leader exits, rather than surviving outside output-based detection.
closed_child="$tmp/closed-stream-child"; mkdir -p "$closed_child"; printf '%s\n' '#!/usr/bin/env bash' "sleep 60 >/dev/null 2>&1 & echo \$! > '$closed_child/child.pid'" > "$closed_child/spawn"; chmod +x "$closed_child/spawn"
perl "$root/scripts/lib/verification-exec.pl" --timeout 10 --output-cap 512 --stdout "$closed_child/stdout" --stderr "$closed_child/stderr" --status "$closed_child/status" -- "$closed_child/spawn"
IFS=$'\t' read -r _ _ closed_timed_out closed_descendants _ _ _ < "$closed_child/status"; closed_pid="$(sed -n '1p' "$closed_child/child.pid")"; sleep 0.2; ! kill -0 "$closed_pid" 2>/dev/null || fail 'closed-stream descendant survived leader exit'; [ "$closed_timed_out" = 0 ] && [ "$closed_descendants" = 1 ] || fail 'closed-stream descendant metadata missing'

# Interrupting the supervisor also tears down the command process group; it
# must not leave a child running or publish a successful status record.
interrupt_dir="$tmp/interrupt-supervisor"; mkdir -p "$interrupt_dir"; printf '%s\n' '#!/usr/bin/env bash' "echo \$\$ > '$interrupt_dir/child.pid'" 'sleep 60' > "$interrupt_dir/sleep"; chmod +x "$interrupt_dir/sleep"
perl "$root/scripts/lib/verification-exec.pl" --timeout 30 --output-cap 512 --stdout "$interrupt_dir/stdout" --stderr "$interrupt_dir/stderr" --status "$interrupt_dir/status" -- "$interrupt_dir/sleep" & interrupt_supervisor=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do [ -s "$interrupt_dir/child.pid" ] && break; sleep 0.1; done; [ -s "$interrupt_dir/child.pid" ] || fail 'interrupt fixture did not start'; interrupt_child="$(sed -n '1p' "$interrupt_dir/child.pid")"; kill -TERM "$interrupt_supervisor"; wait "$interrupt_supervisor" 2>/dev/null || true; sleep 0.2
! kill -0 "$interrupt_child" 2>/dev/null || fail 'interrupted supervisor left child alive'; [ ! -e "$interrupt_dir/status" ] || fail 'interrupted supervisor published completion status'

# Persisted and transient output are streaming-capped while total byte counts
# and truncation are recorded.
printf '%s\n' '#!/usr/bin/env bash' 'perl -e '\''print "x" x (10*1024*1024); print STDERR "y" x (10*1024*1024)'\''' > "$tmp/java-bin/mvn"; chmod +x "$tmp/java-bin/mvn"
MANA_VERIFY_MAX_OUTPUT_BYTES=512 PATH="$tmp/java-bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --json > "$tmp/java-output.json" || fail 'bounded output run failed'
jq -e '.checks[0].output.stdoutBytes==10485760 and .checks[0].output.stderrBytes==10485760 and .checks[0].output.stdoutTruncated==true and .checks[0].output.stderrTruncated==true' "$tmp/java-output.json" >/dev/null || fail 'output truncation metadata missing'
bounded_artifact="$(jq -r '.checks[0].output.stdoutArtifact' "$tmp/java-output.json")"; [ "$(wc -c < "$java_project/$bounded_artifact" | tr -d ' ')" = 512 ] || fail 'persisted output exceeded cap'
! find "$java_project/.mana" -name '*.full' -print | grep -q . || fail 'unbounded transient output artifact exists'

# A direct 100 MiB no-newline stream retains only the configured prefix.
supervisor_dir="$tmp/supervisor"; mkdir -p "$supervisor_dir"
perl "$root/scripts/lib/verification-exec.pl" --timeout 10 --output-cap 1024 --stdout "$supervisor_dir/stdout" --stderr "$supervisor_dir/stderr" --status "$supervisor_dir/status" -- perl -e 'print "z" x (100*1024*1024)'
IFS=$'\t' read -r supervisor_code _ _ _ supervisor_bytes _ _ < "$supervisor_dir/status"
[ "$supervisor_code" = 0 ] && [ "$supervisor_bytes" = 104857600 ] && [ "$(wc -c < "$supervisor_dir/stdout" | tr -d ' ')" = 1024 ] || fail '100 MiB streaming bound failed'

# An executing approved action that changes tracked source is detected, stops
# reliable verification, and is never reverted.
printf '%s\n' '#!/usr/bin/env bash' 'printf "// verifier mutation\\n" >> src/main/java/Main.java' > "$tmp/java-bin/mvn"; chmod +x "$tmp/java-bin/mvn"; before_mutation="$(git -C "$java_project" hash-object src/main/java/Main.java)"
if PATH="$tmp/java-bin:$PATH" verify "$java_project" --skill java-targeted-build-verification --json > "$tmp/java-mutation.json"; then fail 'source-mutating verification passed'; fi
after_mutation="$(git -C "$java_project" hash-object src/main/java/Main.java)"; [ "$before_mutation" != "$after_mutation" ] || fail 'mutation fixture did not modify source'
jq -e '.overallResult=="inconclusive" and .observedEffects.unexpectedSourceMutation==true and .checks[0].observedEffects.unexpectedSourceMutation==true and (.checks[0].observedEffects.mutationPaths|index("src/main/java/Main.java"))' "$tmp/java-mutation.json" >/dev/null || fail 'source mutation evidence missing'; grep -Fq 'verifier mutation' "$java_project/src/main/java/Main.java" || fail 'verifier reverted source mutation'

# Generated/derived/repository-script origins are never directly executable.
verification_trust_executable generated && fail 'generated action became executable'; verification_trust_executable derived && fail 'derived action became executable'; verification_trust_executable repository_script && fail 'repository script became directly executable'; verification_trust_executable project_approved || fail 'project-approved action rejected'
! rg -n '^[[:space:]]*eval[[:space:]]' "$root/scripts/mana-verify.sh" >/dev/null || fail 'verifier uses eval'; ! rg -n 'bash[[:space:]]+-lc' "$root/scripts/mana-verify.sh" >/dev/null || fail 'verifier uses bash -lc'

# Action identity is stable and duplicate claims succeed exactly once.
fp1="$(verification_execution_fingerprint target input executable framework_declared effects environment bounds)"; fp2="$(verification_execution_fingerprint target input executable framework_declared effects environment bounds)"; [ "$fp1" = "$fp2" ] || fail 'fingerprint unstable'; mkdir -p "$tmp/dedup"; verification_dedup_claim "$tmp/dedup" "$fp1" || fail 'first action claim failed'; verification_dedup_claim "$tmp/dedup" "$fp2" && fail 'duplicate action claim succeeded'

# Dirty state is supported; source mutation detection reports and never reverts.
mutation_project="$tmp/mutation"; init_repo "$mutation_project"; printf 'one\n' > "$mutation_project/source.java"; commit_all "$mutation_project"; printf 'dirty\n' > "$mutation_project/source.java"; mkdir -p "$tmp/snapshot" "$tmp/after"; verification_snapshot_source_state "$mutation_project" "$tmp/snapshot/state" "$tmp/snapshot/paths" "$tmp/snapshot/untracked"; printf 'changed again\n' > "$mutation_project/source.java"; mutations="$(verification_detect_source_mutations "$mutation_project" "$tmp/snapshot/state" "$tmp/snapshot/paths" "$tmp/snapshot/untracked" "$tmp/after")"; printf '%s\n' "$mutations" | grep -Fq source.java || fail 'tracked mutation not detected'; grep -Fq 'changed again' "$mutation_project/source.java" || fail 'mutation was reverted'
mkdir -p "$mutation_project/build"; printf 'generated\n' > "$mutation_project/build/output.java"; mutations="$(verification_detect_source_mutations "$mutation_project" "$tmp/snapshot/state" "$tmp/snapshot/paths" "$tmp/snapshot/untracked" "$tmp/after")"; printf '%s\n' "$mutations" | grep -Fq 'build/output.java' && fail 'ignored build output treated as source mutation'

# A tracked path remains attribution-sensitive even under a conventional build
# directory; only untracked build/cache output receives the path exemption.
printf 'tracked output\n' > "$mutation_project/build/tracked.txt"; git -C "$mutation_project" add -f build/tracked.txt; git -C "$mutation_project" commit -qm 'tracked build fixture'; mkdir -p "$tmp/tracked-build-before" "$tmp/tracked-build-after"; verification_snapshot_source_state "$mutation_project" "$tmp/tracked-build-before/state" "$tmp/tracked-build-before/paths" "$tmp/tracked-build-before/untracked"; printf 'changed by verifier\n' >> "$mutation_project/build/tracked.txt"
mutations="$(verification_detect_source_mutations "$mutation_project" "$tmp/tracked-build-before/state" "$tmp/tracked-build-before/paths" "$tmp/tracked-build-before/untracked" "$tmp/tracked-build-after")"; printf '%s\n' "$mutations" | grep -Fq build/tracked.txt || fail 'tracked build path mutation was ignored'

# A pre-existing untracked source path is fingerprinted by content/type/mode.
printf 'before\n' > "$mutation_project/untracked.sh"; mkdir -p "$tmp/untracked-before" "$tmp/untracked-after"; verification_snapshot_source_state "$mutation_project" "$tmp/untracked-before/state" "$tmp/untracked-before/paths" "$tmp/untracked-before/untracked"; printf 'after\n' >> "$mutation_project/untracked.sh"
mutations="$(verification_detect_source_mutations "$mutation_project" "$tmp/untracked-before/state" "$tmp/untracked-before/paths" "$tmp/untracked-before/untracked" "$tmp/untracked-after")"; printf '%s\n' "$mutations" | grep -Fq untracked.sh || fail 'pre-existing untracked mutation not detected'

# Staged content, mode changes, symlink targets, and tracked fixture data are
# represented in the tracked binary-diff fingerprint.
matrix_project="$tmp/mutation-matrix"; init_repo "$matrix_project"; mkdir -p "$matrix_project/src/test/resources"; printf original > "$matrix_project/staged.sh"; printf fixture > "$matrix_project/src/test/resources/data.txt"; ln -s staged.sh "$matrix_project/link.sh"; commit_all "$matrix_project"; printf staged > "$matrix_project/staged.sh"; git -C "$matrix_project" add staged.sh; mkdir -p "$tmp/matrix-before" "$tmp/matrix-after"; verification_snapshot_source_state "$matrix_project" "$tmp/matrix-before/state" "$tmp/matrix-before/paths" "$tmp/matrix-before/untracked"; printf further > "$matrix_project/staged.sh"; chmod +x "$matrix_project/src/test/resources/data.txt"; ln -snf src/test/resources/data.txt "$matrix_project/link.sh"
matrix_mutations="$(verification_detect_source_mutations "$matrix_project" "$tmp/matrix-before/state" "$tmp/matrix-before/paths" "$tmp/matrix-before/untracked" "$tmp/matrix-after")"; for expected_path in staged.sh src/test/resources/data.txt link.sh; do printf '%s\n' "$matrix_mutations" | grep -Fq "$expected_path" || fail "mutation not detected: $expected_path"; done

# Target identity is stable across repairs; concrete action identity is not.
target_one="$(verification_target_fingerprint bash_syntax '["bash","-n","--","x.sh"]' /repo changed_files)"; target_two="$(verification_target_fingerprint bash_syntax '["bash","-n","--","x.sh"]' /repo changed_files)"; target_other_cwd="$(verification_target_fingerprint bash_syntax '["bash","-n","--","x.sh"]' /other changed_files)"
[ "$target_one" = "$target_two" ] && [ "$target_one" != "$target_other_cwd" ] || fail 'target fingerprint stability incorrect'
action_one="$(verification_action_fingerprint "$target_one" contract input-one executable framework_declared effects environment)"; action_same="$(verification_action_fingerprint "$target_one" contract input-one executable framework_declared effects environment)"; action_repaired="$(verification_action_fingerprint "$target_one" contract input-two executable framework_declared effects environment)"; action_new_spec="$(verification_action_fingerprint "$target_one" contract-two input-one executable framework_declared effects environment)"
[ "$action_one" = "$action_same" ] && [ "$action_one" != "$action_repaired" ] && [ "$action_one" != "$action_new_spec" ] || fail 'action fingerprint sensitivity incorrect'

# Mechanical aggregation never hides missing required evidence.
[ "$(verification_overall_result '[{"required":true,"result":"passed"},{"required":false,"result":"failed"}]' false)" = partial ] || fail 'optional failure aggregation incorrect'
[ "$(verification_overall_result '[{"required":true,"result":"failed"},{"required":true,"result":"blocked"}]' false)" = blocked ] || fail 'required blocker was hidden by failure'
[ "$(verification_overall_result '[{"required":true,"result":"passed"}]' true)" = inconclusive ] || fail 'source mutation did not dominate aggregation'

# Leading dashes remain argv data; tabs/newlines are explicitly blocked rather
# than silently omitted by Git's quoted path display.
path_project="$tmp/path-project"; init_repo "$path_project"; printf base > "$path_project/base"; commit_all "$path_project"; printf '#!/usr/bin/env bash\ntrue\n' > "$path_project/-leading.sh"
verify "$path_project" --skill shell-syntax-verification --json > "$tmp/leading.json" || fail 'leading-dash shell filename failed'; jq -e '.checks[0].effectiveArgv==["bash","-n","--","-leading.sh"] and .overallResult=="passed"' "$tmp/leading.json" >/dev/null || fail 'leading-dash filename was interpreted as options'
printf '#!/usr/bin/env bash\ntrue\n' > "$path_project/tab	name.sh"; if verify "$path_project" --skill shell-syntax-verification --dry-run --json > "$tmp/control-path.json"; then fail 'control-character path was silently accepted'; fi
jq -e '.status=="blocked" and (.blockers|any(contains("tabs or newlines")))' "$tmp/control-path.json" >/dev/null || fail 'control-character path blocker missing'

# Concise JSON evidence is redacted; raw logs remain local, private artifacts.
secret_project="$tmp/secret"; init_repo "$secret_project"; printf '#!/usr/bin/env bash\ntrue\n' > "$secret_project/secret.sh"; commit_all "$secret_project"; printf '#!/usr/bin/env bash\nif then # TOKEN=super-secret\n' > "$secret_project/secret.sh"
if verify "$secret_project" --skill shell-syntax-verification --json > "$tmp/secret-result.json"; then fail 'secret syntax fixture passed'; fi
! grep -Fq 'super-secret' "$tmp/secret-result.json" || fail 'secret propagated into concise JSON evidence'; grep -Fq '[REDACTED]' "$tmp/secret-result.json" || fail 'secret redaction marker missing'

# Framework bounds can be tightened but not loosened through the environment.
bounded="$(MANA_VERIFY_MAX_CHECKS=999 bash -c '. "$1/scripts/lib/verification.sh"; printf "%s" "$MANA_VERIFY_MAX_CHECKS"' _ "$root")"; [ "$bounded" = 20 ] || fail 'framework maximum was loosened'
cap_project="$tmp/check-cap"; init_repo "$cap_project"; mkdir -p "$cap_project/scripts"; printf '#!/usr/bin/env bash\ntrue\n' > "$cap_project/scripts/seed.sh"; commit_all "$cap_project"
for number in $(seq 1 21); do printf '#!/usr/bin/env bash\ntrue\n' > "$cap_project/scripts/check-$number.sh"; done
if verify "$cap_project" --skill shell-syntax-verification --dry-run --json > "$tmp/check-cap.json"; then fail 'check cap was not enforced'; fi
jq -e '.status=="blocked" and (.blockers|any(contains("exceed framework maximum")))' "$tmp/check-cap.json" >/dev/null || fail 'check cap blocker missing'

# Dedup executes one shared action while preserving both owning skill records.
framework="$tmp/framework"; mkdir -p "$framework"; cp -R "$root/scripts" "$root/skills" "$root/templates" "$framework/"; cp -R "$framework/skills/shell-syntax-verification" "$framework/skills/shell-syntax-verification-copy"
sed 's/name: shell-syntax-verification/name: shell-syntax-verification-copy/' "$framework/skills/shell-syntax-verification-copy/SKILL.md" > "$tmp/copy-skill"; cp "$tmp/copy-skill" "$framework/skills/shell-syntax-verification-copy/SKILL.md"
jq '.skill_id="shell-syntax-verification-copy"' "$framework/skills/shell-syntax-verification-copy/verification.yaml" > "$tmp/copy-spec"; cp "$tmp/copy-spec" "$framework/skills/shell-syntax-verification-copy/verification.yaml"
"$framework/scripts/build-skill-index.sh" "$framework" > "$framework/skills/index.yaml"
dedup_project="$tmp/dedup-project"; init_repo "$dedup_project"; printf '#!/usr/bin/env bash\ntrue\n' > "$dedup_project/check.sh"; commit_all "$dedup_project"; printf '#!/usr/bin/env bash\necho changed\n' > "$dedup_project/check.sh"
dedup_json="$("$framework/scripts/mana-verify.sh" --project-root "$dedup_project" --skill shell-syntax-verification --skill shell-syntax-verification-copy --json)" || fail 'deduplicated verification failed'
jq -e '(.checks|length)==2 and .cost.checksExecuted==1 and .cost.duplicateActionsSuppressed==1 and ([.checks[].skillId]|unique|length)==2 and ([.checks[].specDigest]|unique|length)==2 and ([.checks[].output.stdoutArtifact]|unique|length)==1 and ([.checks[]|select(.deduplicated)]|length)==1' <<<"$dedup_json" >/dev/null || fail 'deduplicated provenance incorrect'

# Deleting a governance-relevant file remains applicable and uses the bounded
# manifest-backed conservative scenario set.
governance_project="$tmp/governance-targeting"; init_repo "$governance_project"; mkdir -p "$governance_project/scripts" "$governance_project/evals/scenarios" "$governance_project/profiles"; printf '#!/usr/bin/env bash\n' > "$governance_project/scripts/mana-eval.sh"; printf profile > "$governance_project/profiles/example.yaml"; printf keep > "$governance_project/evals/scenarios/.keep"; commit_all "$governance_project"; git -C "$governance_project" rm -q profiles/example.yaml
governance_plan="$(verify "$governance_project" --dry-run --json)" || fail 'governance deletion plan failed'
jq -e '(.selections|any(.skillId=="mana-governance-regression-verification" and .selected)) and ([.actions[]|select(.adapter=="mana_eval")]|length)==2' <<<"$governance_plan" >/dev/null || fail 'governance deletion targeting incorrect'

# The canonical result is atomically published and leaves no temporary files.
! find "$(dirname "$result_path")" -name '.*.tmp.*' -print | grep -q . || fail 'partial evidence publication file remained'
rg -F 'mv "$result_tmp" "$result_file"' "$root/scripts/mana-verify.sh" >/dev/null || fail 'result publication is not atomic'

# Provider names on PATH cannot be reached by any Mana-owned verification
# adapter path. The marker remains absent after a real shell run.
provider_bin="$tmp/providers"; provider_marker="$tmp/provider-called"; mkdir -p "$provider_bin"
for provider in codex claude opencode junie; do printf '%s\n' '#!/usr/bin/env bash' "printf called >> '$provider_marker'" > "$provider_bin/$provider"; chmod +x "$provider_bin/$provider"; done
PATH="$provider_bin:$PATH" verify "$shell_project" --skill shell-syntax-verification --json >/dev/null || true
[ ! -e "$provider_marker" ] || fail 'verification reached a model/provider executable'
! rg -n '(^|[[:space:]/])(codex|claude|opencode|junie)([[:space:]]|$)' "$root/scripts/mana-verify.sh" "$root/scripts/lib/verification.sh" "$root/scripts/lib/verification-exec.pl" >/dev/null || fail 'provider invocation is reachable from verifier code'

# Compare the seven historical failures semantically, not by count/status.
baseline_root="$tmp/baseline-root"; baseline_project="$tmp/baseline-project"; current_project="$tmp/current-project"; mkdir -p "$baseline_root" "$baseline_project" "$current_project"; git -C "$root" archive HEAD | tar -x -C "$baseline_root"
init_repo "$baseline_project"; printf fixture > "$baseline_project/README"; commit_all "$baseline_project"; init_repo "$current_project"; printf fixture > "$current_project/README"; commit_all "$current_project"
"$baseline_root/scripts/mana-eval.sh" --project-root "$baseline_project" run --json > "$tmp/baseline-eval.json" || true; "$root/scripts/mana-eval.sh" --project-root "$current_project" run --json > "$tmp/current-eval.json" || true
jq -r '.results[]' "$tmp/baseline-eval.json" | while IFS= read -r artifact; do jq -c '{scenarioId,status,pass,assertions,selectedSkills,humanGates,expectedEvidence,modelRouting,runtimeWarnings}' "$artifact"; done | LC_ALL=C sort > "$tmp/baseline-semantic.jsonl"
jq -r '.results[]' "$tmp/current-eval.json" | while IFS= read -r artifact; do jq -c '{scenarioId,status,pass,assertions,selectedSkills,humanGates,expectedEvidence,modelRouting,runtimeWarnings}' "$artifact"; done | LC_ALL=C sort > "$tmp/current-semantic.jsonl"
cmp -s "$tmp/baseline-semantic.jsonl" "$tmp/current-semantic.jsonl" || fail 'historical eval semantics changed'
[ "$(jq -s 'map(select(.pass==false))|length' $(jq -r '.results[]' "$tmp/current-eval.json"))" = 7 ] || fail 'historical failing eval set changed'
jq -s -e '
  [ .[] | select(.pass==false) |
    {scenarioId, failures: [.assertions[] | select(.pass==false) |
      {type, value, reasonCode, reason}]} ] == [
    {"scenarioId":"ambiguous-story","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool test_runner_execute_local"}]},
    {"scenarioId":"conditional-contract-pr","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool shell_command"}]},
    {"scenarioId":"conditional-database-pr","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool shell_command"}]},
    {"scenarioId":"conditional-security-pr","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool shell_command"}]},
    {"scenarioId":"plan-drift-branch","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool shell_command"}]},
    {"scenarioId":"risky-liquibase-change","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool test_runner_execute_local"}]},
    {"scenarioId":"weak-acceptance-criteria","failures":[{"type":"must_not_modify","value":"true","reasonCode":"MUTATING_TOOL_ALLOWED","reason":"Effective tool allowlist includes mutating tool test_runner_execute_local"}]}
  ]
' $(jq -r '.results[]' "$tmp/current-eval.json") >/dev/null || fail 'historical eval failure assertions changed'

echo 'Verification Skills tests passed'
