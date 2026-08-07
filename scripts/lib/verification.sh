#!/usr/bin/env bash
# Strict helpers shared by verification validation and execution. Verification
# contracts use JSON syntax, which is valid YAML 1.2, so jq can reject unknown
# structure instead of relying on permissive prose or shell parsing.

MANA_VERIFY_MAX_AUTO_SKILLS="${MANA_VERIFY_MAX_AUTO_SKILLS:-5}"
MANA_VERIFY_MAX_CHECKS="${MANA_VERIFY_MAX_CHECKS:-20}"
MANA_VERIFY_MAX_SECONDS="${MANA_VERIFY_MAX_SECONDS:-900}"
MANA_VERIFY_MAX_OUTPUT_BYTES="${MANA_VERIFY_MAX_OUTPUT_BYTES:-16384}"
MANA_VERIFY_MAX_SPEC_BYTES=65536
[ "$MANA_VERIFY_MAX_AUTO_SKILLS" -le 5 ] 2>/dev/null || MANA_VERIFY_MAX_AUTO_SKILLS=5
[ "$MANA_VERIFY_MAX_CHECKS" -le 20 ] 2>/dev/null || MANA_VERIFY_MAX_CHECKS=20
[ "$MANA_VERIFY_MAX_SECONDS" -le 900 ] 2>/dev/null || MANA_VERIFY_MAX_SECONDS=900
[ "$MANA_VERIFY_MAX_OUTPUT_BYTES" -le 16384 ] 2>/dev/null || MANA_VERIFY_MAX_OUTPUT_BYTES=16384

verification_frontmatter_field() {
  awk -v key="$2" '$0 == "---" { n++; next } n == 2 { exit } n == 1 && index($0,key ":") == 1 { v=substr($0,length(key)+2); sub(/^[[:space:]]+/,"",v); gsub(/^"|"$/, "", v); print v; exit }' "$1"
}

verification_index_field() {
  awk -v id="$2" -v field="$3" '
    $1 == "-" && $2 == "id:" { active=($3 == id); next }
    active && $1 == field ":" { print $2; exit }
  ' "$1"
}

verification_spec_validate() {
  local spec="$1" expected_id="$2"
  [ -f "$spec" ] || return 1
  [ "$(wc -c < "$spec" | tr -d ' ')" -le "$MANA_VERIFY_MAX_SPEC_BYTES" ] || return 1
  # jq normally applies last-key-wins semantics. Streaming paths preserve each
  # occurrence, allowing strict contracts to reject duplicate object keys.
  [ -z "$(jq --stream -r 'select(length==2) | .[0] | @json' "$spec" 2>/dev/null | LC_ALL=C sort | uniq -d)" ] || return 1
  jq --stream -e 'all(select(length==2); (.[0] | length) <= 32)' "$spec" >/dev/null 2>&1 || return 1
  jq -e --arg expected "$expected_id" '
    def keys_exact($allowed): ((keys - $allowed) | length) == 0;
    def strings: type == "array" and length > 0 and all(.[]; type == "string" and length > 0);
    def predicate:
      type == "object" and
      if .type == "repository_available" or .type == "explicit_invocation" then
        keys_exact(["type"])
      elif .type == "changed_extension" then
        keys_exact(["type","extensions"]) and (.extensions | strings)
      elif .type == "changed_path" then
        keys_exact(["type","patterns"]) and (.patterns | strings)
      elif .type == "manifest_exists" then
        keys_exact(["type","paths"]) and (.paths | strings)
      else false end;
    def effects:
      type == "object" and
      keys_exact(["source_tree","mana_workspace","build_outputs","external_state","network"]) and
      (.source_tree | IN("none","declared_paths")) and
      (.mana_workspace | IN("none","write")) and
      (.build_outputs | IN("none","write")) and
      (.external_state | IN("none","isolated_test_read","isolated_test_write")) and
      (.network | IN("none","declared"));
    def check:
      type == "object" and
      keys_exact(["id","adapter","scope","required","timeout_seconds","cost","trust_origin","effects"]) and
      (.id | type == "string" and test("^[a-z0-9][a-z0-9-]*$")) and
      (.adapter | IN("bash_syntax","mana_eval","java_approved_test")) and
      (.scope | IN("changed_files","relevant_scenarios","changed_modules")) and
      (.required | type == "boolean") and
      (.timeout_seconds | type == "number" and . >= 1 and . <= 900 and floor == .) and
      (.cost | IN("cheap","normal","expensive")) and
      (.trust_origin | IN("framework_declared","project_approved","derived","repository_script","generated")) and
      (.effects | effects);
    . as $spec |
    type == "object" and
    keys_exact(["schema_version","skill_id","applicability","checks","success","limits"]) and
    .schema_version == 1 and .skill_id == $expected and
    (.applicability | type == "object" and keys_exact(["all","any"]) and
      (.all | type == "array" and all(.[]; predicate)) and
      (.any | type == "array" and all(.[]; predicate))) and
    (.checks | type == "array" and length > 0 and all(.[]; check) and
      ([.[].id] | length == (unique | length))) and
    (.success | type == "object" and keys_exact(["requires","accepted_results"]) and
      (.requires | strings) and
      (.accepted_results | strings) and
      .accepted_results == ["passed"] and
      all(.requires[]; . as $id | any($spec.checks[]; .id == $id)) and
      ((.requires | sort) == ([$spec.checks[] | select(.required) | .id] | sort))) and
    (.limits | type == "object" and keys_exact(["max_checks","max_seconds","max_output_bytes"]) and
      (.max_checks | type == "number" and . >= 1 and . <= 20 and floor == .) and
      (.max_seconds | type == "number" and . >= 1 and . <= 900 and floor == .) and
      (.max_output_bytes | type == "number" and . >= 256 and . <= 16384 and floor == .))
  ' "$spec" >/dev/null
}

verification_digest_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print "sha256:" $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print "sha256:" $1}'
  else return 1; fi
}

verification_digest_text() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print "sha256:" $1}'
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 | awk '{print "sha256:" $1}'
  else return 1; fi
}

verification_json_array_lines() {
  jq -Rsc 'split("\n") | map(select(length > 0))'
}

verification_target_fingerprint() {
  # Stable verification target: adapter, normalized action, cwd, and scope.
  printf 'adapter=%s\nargv=%s\ncwd=%s\nscope=%s\n' "$1" "$2" "$3" "$4" | verification_digest_text
}

verification_action_fingerprint() {
  # Concrete execution identity: target, contract, inputs, executable, trust,
  # effects, and environment. Run IDs and artifact paths are excluded.
  printf 'target=%s\nspec=%s\ninput=%s\nexecutable=%s\ntrust=%s\neffects=%s\nenvironment=%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" | verification_digest_text
}

verification_execution_fingerprint() {
  printf 'target=%s\ninput=%s\nexecutable=%s\ntrust=%s\neffects=%s\nenvironment=%s\nbounds=%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" | verification_digest_text
}

verification_environment_digest() {
  printf 'PATH=%s\nJAVA_HOME=%s\nMAVEN_OPTS=%s\nGRADLE_OPTS=%s\n' "${PATH:-}" "${JAVA_HOME:-}" "${MAVEN_OPTS:-}" "${GRADLE_OPTS:-}" | verification_digest_text
}

verification_redact_stream() {
  awk '/-----BEGIN .*PRIVATE KEY-----/ { print "[REDACTED PRIVATE KEY]"; private_key=1; next } /-----END .*PRIVATE KEY-----/ { private_key=0; next } !private_key { print }' | sed -E \
    -e 's/((PASSWORD|TOKEN|SECRET|AWS_SECRET_ACCESS_KEY)[[:space:]]*=[[:space:]]*)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/(Authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's#(://[^:/[:space:]]+:)[^@/[:space:]]+@#\1[REDACTED]@#g'
}

verification_dedup_claim() {
  local directory="$1" fingerprint="$2" key
  key="$(printf '%s' "$fingerprint" | tr ':/' '__')"
  [ ! -e "$directory/$key.claim" ] || return 1
  : > "$directory/$key.claim"
}

verification_trust_executable() {
  case "$1" in framework_declared|project_approved) return 0;; derived|repository_script|generated) return 1;; *) return 1;; esac
}

verification_snapshot_source_state() {
  # project root, tracked-state digest file, tracked path JSONL file, and
  # untracked path/type/mode/content JSONL file.
  local project="$1" base path identity kind mode digest
  if git -C "$project" rev-parse --verify HEAD >/dev/null 2>&1; then base=HEAD
  else base="$(git -C "$project" hash-object -t tree /dev/null)"; fi
  # Every tracked path is attribution-sensitive, even when its name resembles
  # a conventional build directory. Only Mana's own workspace is excluded.
  # Known build/cache directories are ignored below only for untracked paths.
  git -C "$project" diff --no-ext-diff --binary "$base" -- . ':(exclude).mana/**' | verification_digest_text > "$2"
  : > "$3"; : > "$4"
  while IFS= read -r -d '' path; do jq -cn --arg path "$path" '$path' >> "$3"; done < <(git -C "$project" diff --no-ext-diff --name-only -z "$base" -- . ':(exclude).mana/**')
  while IFS= read -r -d '' path; do
    case "$path" in .mana/*|target/*|build/*|out/*|.gradle/*|node_modules/*|*/target/*|*/build/*|*/out/*|*/.gradle/*|*/node_modules/*) continue;; esac
    if [ -L "$project/$path" ]; then kind=symlink; identity="$(readlink "$project/$path" | verification_digest_text)"
    elif [ -f "$project/$path" ]; then kind=file; identity="$(verification_digest_file "$project/$path")"
    else kind=other; identity=unreadable; fi
    mode="$(git -C "$project" ls-files -s -- "$path" | awk 'NR==1{print $1}')"; [ -n "$mode" ] || mode="$(test -x "$project/$path" && echo executable || echo regular)"
    jq -cn --arg path "$path" --arg kind "$kind" --arg mode "$mode" --arg identity "$identity" '{path:$path,kind:$kind,mode:$mode,identity:$identity}' >> "$4"
  done < <(git -C "$project" ls-files --others --exclude-standard -z)
}

verification_detect_source_mutations() {
  # Project root and the three preflight files. Prints safe mutation paths.
  local project="$1" before_state="$2" before_paths="$3" before_untracked="$4" scratch="$5" paths
  verification_snapshot_source_state "$project" "$scratch/state" "$scratch/paths" "$scratch/untracked"
  paths="$scratch/mutation-paths.jsonl"; : > "$paths"
  if ! cmp -s "$before_state" "$scratch/state"; then cat "$before_paths" "$scratch/paths" >> "$paths"; fi
  jq -s 'group_by(.path)[] | select(length == 1 or (map(.kind + "|" + .mode + "|" + .identity) | unique | length) > 1) | .[0].path' "$before_untracked" "$scratch/untracked" >> "$paths"
  jq -sr 'unique[] | if test("[\\t\\n]") then "[unsupported-control-character-path]" else . end' "$paths"
}

verification_repository_input_digest() {
  { printf '%s\n' "$1"; cat "$2" "$3"; } | verification_digest_text
}

verification_overall_result() {
  jq -r --argjson sourceMutation "$2" '
    if $sourceMutation then "inconclusive"
    elif any(.[]; .required and .result=="blocked") then "blocked"
    elif any(.[]; .required and .result=="inconclusive") then "inconclusive"
    elif any(.[]; .required and .result=="failed") then "failed"
    elif length == 0 then "inconclusive"
    elif any(.[]; .result!="passed") then "partial"
    else "passed" end
  ' <<<"$1"
}

verification_result_validate() {
  jq -e '
    def keys_exact($allowed): ((keys - $allowed) | length) == 0;
    def keys_equal($expected): (keys|sort) == ($expected|sort);
    def has_all($required): . as $object | all($required[]; . as $key | $object | has($key));
    def digest: type=="string" and (test("^sha256:[0-9a-f]{64}$") or .=="unavailable");
    def effects: type=="object" and keys_equal(["build_outputs","external_state","mana_workspace","network","source_tree"]) and
      (.source_tree|IN("none","declared_paths")) and (.mana_workspace|IN("none","write")) and (.build_outputs|IN("none","write")) and
      (.external_state|IN("none","isolated_test_read","isolated_test_write")) and (.network|IN("none","declared"));
    type=="object" and keys_equal(["checks","cost","generatedAt","judgment","kind","observedEffects","overallResult","projectRevision","runId","runtimeExecutionId","schemaVersion","scope","selections","startedAt","workingTreeDirtyBefore"]) and
    .schemaVersion=="1" and .kind=="verification-result" and (.overallResult|IN("passed","failed","blocked","partial","inconclusive")) and .judgment==null and
    (.scope|type=="object" and keys_equal(["base","changedPaths","changedPathsDigest","head","inputDigest","mode"]) and (.changedPathsDigest|digest) and (.inputDigest|digest) and (.changedPaths|type=="array")) and
    (.selections|type=="array" and ([.[].skillId]|length==(unique|length)) and all(.[]; type=="object" and keys_equal(["applicability","mode","reasons","selected","skillId"]) and (.applicability|IN("applicable","not_applicable","blocked")) and (.mode|IN("automatic","explicit")) and (.selected|type=="boolean"))) and
    (.checks|type=="array" and all(.[];
      type=="object" and keys_exact(["actionFingerprint","adapter","baseCheckId","checkId","commandOrigin","costClass","declaredEffects","deduplicated","deduplicatedFrom","deduplicatedFromCheckId","descendantsTerminated","durationMs","effectiveArgv","environmentClassification","environmentDigest","executable","executionFingerprint","exitCode","failureFingerprint","inputDigest","limitations","nativeArtifacts","observations","observedEffects","output","outputLimitBytes","relevantFiles","required","result","scope","signal","skillId","skillVersion","specDigest","targetFingerprint","timedOut","timeoutSeconds","trustOrigin","workingDirectory"]) and has_all(["actionFingerprint","adapter","baseCheckId","checkId","commandOrigin","costClass","declaredEffects","deduplicated","descendantsTerminated","durationMs","effectiveArgv","environmentClassification","environmentDigest","executable","executionFingerprint","exitCode","failureFingerprint","inputDigest","limitations","nativeArtifacts","observations","observedEffects","output","outputLimitBytes","relevantFiles","required","result","scope","signal","skillId","skillVersion","specDigest","targetFingerprint","timedOut","timeoutSeconds","trustOrigin","workingDirectory"]) and
      (.specDigest|digest) and (.targetFingerprint|digest) and (.actionFingerprint|digest) and (.executionFingerprint|digest) and (.inputDigest|digest) and (.environmentDigest|digest) and
      (.failureFingerprint==null or (.failureFingerprint|digest)) and (.required|type=="boolean") and (.deduplicated|type=="boolean") and
      (if .deduplicated then has("deduplicatedFrom") and has("deduplicatedFromCheckId") and (.deduplicatedFrom|digest) else (has("deduplicatedFrom") or has("deduplicatedFromCheckId") | not) end) and
      (.timedOut|type=="boolean") and (.descendantsTerminated|type=="boolean") and
      (.result|IN("passed","failed","blocked","partial","inconclusive")) and (.adapter|IN("bash_syntax","mana_eval","java_approved_test")) and (.declaredEffects|effects) and
      (.executable|type=="object" and keys_equal(["digest","path"]) and (.digest|digest)) and
      (.output|type=="object" and keys_equal(["excerpt","stderrArtifact","stderrBytes","stderrDigest","stderrTruncated","stdoutArtifact","stdoutBytes","stdoutDigest","stdoutTruncated"]) and (.stdoutDigest|digest) and (.stderrDigest|digest)) and
      (.observedEffects|type=="object" and keys_equal(["mutationPaths","unexpectedSourceMutation"]))) and ([.[].checkId]|length==(unique|length))) and
    (.observedEffects|type=="object" and keys_equal(["unexpectedSourceMutation"])) and
    (.cost|type=="object" and keys_equal(["checksExecuted","duplicateActionsSuppressed","inputTokens","modelCalls","outputTokens","wallTimeMs"]) and .modelCalls==0 and .inputTokens==0 and .outputTokens==0)
  ' "$1" >/dev/null
}
