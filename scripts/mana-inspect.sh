#!/usr/bin/env bash
# Deterministic, local, read-only Mana inspect v1.
set -u
invalid=2 unsupported=3 malformed=4 internal=5
root="$(pwd)"; command=""; target=""; json=false
usage() { cat <<'USAGE'
Usage: mana inspect <project|artifacts> --json
       mana inspect artifact <artifact-id-or-.mana/path> --json
       mana inspect source <project-relative-source-path> --json
       mana inspect work-items --json
       mana inspect work-item <feature:<workspace-id>|session:<workspace-id>> --json
Exit codes: 0 success; 2 invalid input; 3 unsupported contract; 4 malformed workspace; 5 internal failure.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit "$invalid"; }
fatal() { echo "ERROR: $*" >&2; exit "$internal"; }
command -v jq >/dev/null 2>&1 || fatal "jq is required"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) root="${2:-}"; [ -n "$root" ] || fail "--project-root requires a path"; shift 2 ;;
    --json) json=true; shift ;;
    --help|-h|help) usage; exit 0 ;;
    project|artifacts|work-items|project-context|activity) [ -z "$command" ] || fail "only one operation is allowed"; command="$1"; shift ;;
    artifact|source|work-item) [ -z "$command" ] || fail "only one operation is allowed"; command="$1"; target="${2:-}"; [ -n "$target" ] || fail "$command requires a target"; shift 2 ;;
    *) fail "unknown inspect argument: $1" ;;
  esac
done
[ -n "$command" ] || fail "an inspect operation is required"
[ "$json" = true ] || fail "--json is required for inspect v1"
root="$(cd "$root" 2>/dev/null && pwd -P)" || fail "unreadable project root"
mana="$root/.mana"
[ ! -L "$mana" ] || { echo "ERROR: .mana must not be a symlink" >&2; exit "$malformed"; }
hash_text() { if command -v sha256sum >/dev/null; then printf '%s' "$1" | sha256sum | awk '{print $1}'; else printf '%s' "$1" | shasum -a 256 | awk '{print $1}'; fi; }
hash_file() {
  if [ -n "${MANA_INSPECT_DIGEST_MAP:-}" ]; then
    grep -F "  $1" "$MANA_INSPECT_DIGEST_MAP" | tail -n 1 | awk '{print $1}'
  elif command -v sha256sum >/dev/null; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi
}
rel() { case "$1" in "$root"/*) printf '%s' "${1#"$root"/}" ;; *) return 1 ;; esac; }
mtime() {
  if [ -n "${MANA_INSPECT_MTIME_MAP:-}" ]; then grep -F "  $1" "$MANA_INSPECT_MTIME_MAP" | tail -n 1 | awk '{print $1}'
  elif stat -f '%m' "$1" >/dev/null 2>&1; then stat -f '%m' "$1"; else stat -c '%Y' "$1" 2>/dev/null || printf unavailable; fi
}
ctype() { case "$1" in *.json|*.jsonl) echo application/json;; *.md) echo text/markdown;; *.yaml|*.yml) echo application/yaml;; *.log|*.txt|*.puml) echo text/plain;; *) echo application/octet-stream;; esac; }
workspace() { case "$1" in .mana/features/*) printf '%s' "$1" | awk -F/ '{print "feature:"$3}';; .mana/sessions/*) printf '%s' "$1" | awk -F/ '{print "session:"$3}';; *) echo null;; esac; }
family() {
  case "$1" in
    .mana/global/*) echo service_context;; .mana/features/*|.mana/sessions/*) echo workspace;;
    .mana/runtime/*) echo runtime;; .mana/learning/journeys/*|.mana/learning/*requests/*|.mana/learning/unresolved-concepts/*) echo knowledge;;
    .mana/learning/candidates/*) echo learning;; .mana/evaluations/*|.mana/reports/governance/*) echo governance;;
    .mana/env|.mana/links/*|.mana/jira-mcp.env) echo bootstrap;; .mana/user-context/*|.mana/user-context-state) echo user_context;; *) echo unknown;;
  esac
}
class() { case "$1" in */derived/*|*.puml|*/latest.json|*/latest.md) echo derived;; .mana/env|.mana/links/*|.mana/.?*) echo ephemeral;; *) echo canonical;; esac; }
kind() {
  case "$1" in */manifest.yaml) echo workspace_manifest;; */journey.yaml) echo journey;; */records/*-*.yaml) echo journey_record;; */events/*.jsonl) echo runtime_events;; */sessions/*.json) echo runtime_session;; */evidence/index.md) echo evidence_index;; .mana/jira-mcp.env) echo restricted_configuration;; *.md) echo markdown;; *.json) echo json;; *.jsonl) echo json_lines;; *.yaml|*.yml) echo yaml;; *) echo file;; esac
}
schema() {
  if [[ "$2" == *.json || "$2" == *.yaml || "$2" == *.yml ]] && jq -e . "$1" >/dev/null 2>&1; then
    value="$(jq -r '.schema // (if .kind? and .schemaVersion? then .kind+"/v"+(.schemaVersion|tostring) else empty end)' "$1" 2>/dev/null)"
    [ -n "$value" ] && { echo "$value"; return; }
  fi
  case "$2" in *.md) echo markdown;; *.json) echo json;; *.jsonl) echo jsonl;; *.yaml|*.yml) echo yaml;; *) echo unknown;; esac
}
intrinsic() {
  local value
  case "$2" in
    */journey.yaml) value="$(jq -r '.id // empty' "$1" 2>/dev/null)"; [[ "$value" =~ ^jrn_[a-f0-9]{24}$ ]] && { echo "journey:$value"; return; };;
    */records/*-*.yaml) value="$(jq -r '.id // empty' "$1" 2>/dev/null)"; [[ "$value" =~ ^[A-Za-z][A-Za-z0-9_]*_[a-f0-9]{24}$ ]] && { echo "journey-record:$value"; return; };;
    *.json) value="$(jq -r 'if .kind=="verification-result" then "verification:"+.runId elif .kind=="repair-attempt-result" then "repair-attempt:"+.attemptId elif .kind=="repair-loop-result" then "repair-loop:"+.loopId elif .executionId? then "runtime:"+.executionId elif .candidateId? then "learning:"+.candidateId else empty end' "$1" 2>/dev/null)"; [ -n "$value" ] && { echo "$value"; return; };;
  esac
  echo "file:$2"
}
status() {
  [[ "$2" == *.json ]] && jq -e . "$1" >/dev/null 2>&1 && { value="$(jq -r '.overallResult // .attemptStatus // .status // "available"' "$1")"; case "$value" in passed|failed|blocked|partial|inconclusive|candidate|reviewed|rejected|archived|completed|running|available) echo "$value"; return;; esac; }
  echo available
}
entry() {
  local file="$1" path fam cls typ art rev ws stat sch updated size diagnostic=null meta json_kind json_schema json_version json_id json_status
  path="$(rel "$file")" || return
  fam="$(family "$path")"; cls="$(class "$path")"; typ="$(kind "$path")"; rev="sha256:$(hash_file "$file")"; ws="$(workspace "$path")"; updated="$(mtime "$file")"; size="$(wc -c < "$file" | tr -d ' ')"
  if [[ "$path" == *.json ]] && jq -e . "$file" >/dev/null 2>&1; then
    art="file:$path"; stat=available; sch=json
    IFS='|' read -r json_kind json_schema json_version json_id json_status <<<"$(jq -r '[(.kind // ""),(.schema // ""),(.schemaVersion // ""),(if .kind=="verification-result" then .runId elif .kind=="repair-attempt-result" then .attemptId elif .kind=="repair-loop-result" then .loopId elif .executionId? then .executionId elif .candidateId? then .candidateId else "" end),(.overallResult // .attemptStatus // .status // "available")]|join("|")' "$file")"
    case "$json_kind" in verification-result|repair-attempt-result|repair-loop-result|user-context-candidate) typ="$json_kind" ;; esac
    [ -n "$json_schema" ] && sch="$json_schema" || { [ -n "$json_kind$json_version" ] && sch="$json_kind/v$json_version"; }
    case "$json_status" in passed|failed|blocked|partial|inconclusive|candidate|reviewed|rejected|archived|completed|running|available) stat="$json_status" ;; esac
    [ -n "$json_id" ] && case "$json_kind" in verification-result) art="verification:$json_id" ;; repair-attempt-result) art="repair-attempt:$json_id" ;; repair-loop-result) art="repair-loop:$json_id" ;; *) art="$(family "$path"):$json_id" ;; esac
  else
    art="$(intrinsic "$file" "$path")"; stat="$(status "$file" "$path")"; sch="$(schema "$file" "$path")"
  fi
  if [[ "$path" == *.json || "$path" == *.yaml || "$path" == *.yml ]] && ! jq -e . "$file" >/dev/null 2>&1; then
    case "$path" in */manifest.yaml) : ;; *) fam=unknown; cls=unknown; typ=unknown; stat=malformed; sch=unknown; diagnostic=malformed_json_or_json_yaml ;; esac
  fi
  jq -cn --arg id "$art" --arg revision "$rev" --arg family "$fam" --arg class "$cls" --arg kind "$typ" --arg path "$path" --arg schema "$sch" --arg status "$stat" --arg updated "$updated" --arg type "$(ctype "$path")" --arg diagnostic "$diagnostic" --argjson workspace "$([ "$ws" = null ] && echo null || jq -Rn --arg x "$ws" '$x')" --argjson byte_size "$size" '{artifact_id:$id,revision_id:$revision,family:$family,class:$class,kind:$kind,path:$path,schema:$schema,workspace:$workspace,status:$status,updated_at:{value:$updated,provenance:"filesystem_mtime_epoch"},content_type:$type,byte_size:$byte_size,relations:[],diagnostic:(if $diagnostic=="null" then null else $diagnostic end)}'
}
symlink() {
  local path target
  path="$(rel "$1")" || return; target="$(readlink "$1" 2>/dev/null || echo unavailable)"
  jq -cn --arg id "file:$path" --arg revision "sha256:$(hash_text "$target")" --arg path "$path" '{artifact_id:$id,revision_id:$revision,family:"unknown",class:"unknown",kind:"unknown",path:$path,schema:"unknown",workspace:null,status:"quarantined",updated_at:{value:"unavailable",provenance:"not_followed_symlink"},content_type:"inode/symlink",byte_size:0,relations:[],diagnostic:"symlink_not_followed"}'
}
catalog() {
  [ -e "$mana" ] || { echo '[]'; return; }; [ -d "$mana" ] || { echo "ERROR: .mana is not a directory" >&2; exit "$malformed"; }
  tmp="$(mktemp "${TMPDIR:-/tmp}/mana-inspect.XXXXXX")" || fatal "cannot allocate scan buffer"; trap 'rm -f "$tmp" "$tmp.files" "$tmp.digests" "$tmp.mtimes"' EXIT
  find -P "$mana" -type f -print0 > "$tmp.files"
  if [ -s "$tmp.files" ]; then
    if command -v sha256sum >/dev/null; then xargs -0 sha256sum < "$tmp.files" > "$tmp.digests"; else xargs -0 shasum -a 256 < "$tmp.files" > "$tmp.digests"; fi
    MANA_INSPECT_DIGEST_MAP="$tmp.digests"
    if stat -f '%m' "$mana" >/dev/null 2>&1; then xargs -0 stat -f '%m  %N' < "$tmp.files" > "$tmp.mtimes"; else xargs -0 stat -c '%Y  %n' < "$tmp.files" > "$tmp.mtimes"; fi
    MANA_INSPECT_MTIME_MAP="$tmp.mtimes"
  fi
  while IFS= read -r -d '' file; do
    case "$file" in */latest.json|*/latest.md) continue ;; esac
    if [ -L "$file" ]; then symlink "$file" >> "$tmp"; elif [ -f "$file" ]; then entry "$file" >> "$tmp"; fi
  done < <(find -P "$mana" -mindepth 1 \( -type f -o -type l \) -print0 | LC_ALL=C sort -z)
  jq -sc 'sort_by(.artifact_id,.path) | group_by(.artifact_id) | map(if length == 1 then .[0] else (sort_by(.path)[0] + {status:"ambiguous",diagnostic:"duplicate_artifact_id"}) end)' "$tmp"
}
safe_source_path() {
  case "$1" in ''|/*|.mana|.mana/*|*'//'|../*|*/../*|*/..|..) return 1 ;; esac
  case "/$1/" in *'/../'*|*'/./'*) return 1 ;; esac
  return 0
}
source_staleness() {
  local path="$1" revision="$2" full head
  full="$root/$path"
  if [ -L "$full" ]; then echo unsafe; return; fi
  if [ ! -f "$full" ]; then echo missing; return; fi
  head="$(git -C "$root" rev-parse HEAD 2>/dev/null || true)"
  [ -n "$head" ] || { echo unknown; return; }
  if [ "$revision" = "$head" ]; then
    git -C "$root" diff --quiet HEAD -- "$path" 2>/dev/null && echo fresh || echo working_tree_only
  else echo stale; fi
}
anchor_relations() {
  local wanted_path="${1:-}" wanted_journey="${2:-}" wanted_anchor="${3:-}" file journey id path revision start end state
  [ -d "$mana/learning/journeys" ] || { echo '[]'; return; }
  while IFS= read -r -d '' file; do
    journey="$(basename "$(dirname "$(dirname "$file")")")"
    [[ "$journey" =~ ^jrn_[a-f0-9]{24}$ ]] || continue
    jq -e '(.schema=="mana.learning.record/v1") and (.record_type=="anchor") and (.id|test("^anc_[a-f0-9]{24}$")) and (.node_id|test("^jn_[a-f0-9]{24}$")) and (.revision|type=="string") and (.path|type=="string") and (.range.start_line|type=="number") and (.range.end_line|type=="number")' "$file" >/dev/null 2>&1 || continue
    IFS='|' read -r id path revision start end <<<"$(jq -r '[.id,.path,.revision,(.range.start_line|tostring),(.range.end_line|tostring)]|join("|")' "$file")"
    safe_source_path "$path" || continue
    [ -z "$wanted_path" ] || [ "$path" = "$wanted_path" ] || continue
    [ -z "$wanted_journey" ] || [ "$journey" = "$wanted_journey" ] || continue
    [ -z "$wanted_anchor" ] || [ "$id" = "$wanted_anchor" ] || continue
    state="$(source_staleness "$path" "$revision")"
    jq -cn --arg artifact "journey-record:$id" --arg journey "$journey" --arg anchor "$id" --arg path "$path" --arg revision "$revision" --arg staleness "$state" --argjson start "$start" --argjson end "$end" '{relation_type:"references-source/v1",artifact_id:$artifact,journey_id:$journey,anchor_id:$anchor,source:{path:$path,revision:$revision,range:{start_line:$start,end_line:$end}},staleness:$staleness}'
  done < <(find -P "$mana/learning/journeys" -type f -path '*/records/*-anchor.yaml' -print0 2>/dev/null | LC_ALL=C sort -z) | jq -sc 'sort_by(.artifact_id,.anchor_id)'
}
payload_for() {
  local file="$1" path="$2" size value depth declared
  size="$(wc -c < "$file" | tr -d ' ')"
  [ "$size" -le "${MANA_INSPECT_MAX_PAYLOAD_BYTES:-65536}" ] 2>/dev/null || { jq -cn --argjson size "$size" '{included:false,reason:"payload_too_large",byte_size:$size,max_bytes:65536}'; return; }
  if [[ "$path" == *.json || "$path" == *.yaml || "$path" == *.yml ]] && jq -e . "$file" >/dev/null 2>&1; then
    declared="$(jq -r '.schema // .kind // empty' "$file")"
    case "$declared" in mana.learning.journey/v1|mana.learning.record/v1|verification-result|repair-attempt-result|repair-loop-result|user-context-candidate) ;; *) jq -cn --arg schema "$declared" '{included:false,reason:"unsupported_schema",schema:(if $schema=="" then "unknown" else $schema end)}'; return ;; esac
    depth="$(jq '[paths|length]|max // 0' "$file" 2>/dev/null || echo 999)"
    [ "$depth" -le 32 ] 2>/dev/null || { jq -cn --argjson depth "$depth" '{included:false,reason:"json_depth_exceeded",depth:$depth,max_depth:32}'; return; }
    jq -cn --argjson value "$(jq -cS . "$file")" --argjson depth "$depth" '{included:true,kind:"structured_json",depth:$depth,value:$value}'
  elif [[ "$path" == *.md || "$path" == *.txt || "$path" == *.log || "$path" == *.puml ]] && LC_ALL=C grep -Iq . "$file"; then
    jq -Rs '{included:true,kind:"text",value:.}' < "$file"
  else jq -cn '{included:false,reason:"unsupported_or_binary_content"}'; fi
}
artifact_detail() {
  local entries summary path file journey anchor relations payload
  entries="$(catalog)"
  if [[ "$target" == .mana/* ]]; then
    case "$target" in *'..'*|*'//'*) fail "unsafe artifact path" ;; esac
    summary="$(jq -c --arg path "$target" '[.[]|select(.path==$path)]|if length==1 then .[0] else empty end' <<<"$entries")"
  else summary="$(jq -c --arg id "$target" '[.[]|select(.artifact_id==$id)]|if length==1 then .[0] else empty end' <<<"$entries")"; fi
  [ -n "$summary" ] && [ "$summary" != null ] || { echo "ERROR: artifact not found or ambiguous" >&2; exit "$invalid"; }
  [ "$(jq -r .diagnostic <<<"$summary")" != duplicate_artifact_id ] || { echo "ERROR: artifact identifier is ambiguous" >&2; exit "$invalid"; }
  path="$(jq -r .path <<<"$summary")"; file="$root/$path"; [ -f "$file" ] && ! [ -L "$file" ] || { echo "ERROR: artifact is unavailable or unsafe" >&2; exit "$malformed"; }
  relations='[]'
  case "$path" in
    */journey.yaml) journey="$(jq -r '.id // empty' "$file" 2>/dev/null)"; [[ "$journey" =~ ^jrn_[a-f0-9]{24}$ ]] && relations="$(anchor_relations '' "$journey")" ;;
    */records/*-anchor.yaml) anchor="$(jq -r '.id // empty' "$file" 2>/dev/null)"; relations="$(anchor_relations '' '' "$anchor")" ;;
  esac
  payload="$(payload_for "$file" "$path")"
  response="$(jq -cn --argjson summary "$summary" --argjson payload "$payload" --argjson relations "$relations" '{schema:"mana.inspect.artifact/v1",artifact:$summary,payload:$payload,relations:$relations,guarantees:{model_calls:0,writes:false,relation_coverage:"explicit_structured_only"},diagnostics:[]}')"
  validate_and_emit "$response" artifact
}
source_detail() {
  local full availability relations
  safe_source_path "$target" || fail "unsafe source path"
  full="$root/$target"; if [ -L "$full" ]; then echo "ERROR: source symlink is not supported" >&2; exit "$malformed"; elif [ -f "$full" ]; then availability=present; else availability=missing; fi
  relations="$(anchor_relations "$target")"
  response="$(jq -cn --arg path "$target" --arg availability "$availability" --argjson relations "$relations" '{schema:"mana.inspect.source/v1",source:{path:$path,availability:$availability},relations:$relations,coverage:(if ($relations|length)>0 then "explicit_journey_anchors" else "unknown" end),guarantees:{model_calls:0,writes:false,relation_coverage:"explicit_structured_only"},diagnostics:[]}')"
  validate_and_emit "$response" source
}
manifest_scalar() {
  # Bounded parser for exact, single-line canonical manifest scalars only.
  local file="$1" key="$2"
  awk -v key="$key" '$0 ~ "^" key ":[[:space:]]*" { sub("^[^:]*:[[:space:]]*", ""); gsub(/^"|"$/, ""); print; exit }' "$file"
}
semantic_artifacts() {
  local entries="$1" wid="$2" type wsid workspace_root
  type="${wid%%:*}"; wsid="${wid#*:}"; workspace_root=".mana/${type}s/$wsid"
  jq -c --arg wid "$wid" --arg workspace_root "$workspace_root" '
    [.[] | select(.workspace==$wid and .class!="ephemeral" and .status!="quarantined") |
      . + {work_item_id:$wid, section_id:(if .path==($workspace_root+"/index.md") then "overview"
        elif (.path|test("/context/(story-context|epic-goal-contract|open-questions)\\.md$")) then "requirements"
        elif (.path|test("/planning/")) then "plan"
        elif .path|test("/decisions/") then "decisions"
        elif .path|test("/(evidence|tests|validation)/") then "evidence"
        elif .path|test("/pr/") then "review"
        elif .path|test("/agent-memory/story-trace\\.md$") then "timeline"
        else "artifacts" end)} |
      {artifact_id,path,kind,status,work_item_id,section_id,label:null}]
    | sort_by(.artifact_id,.path)' <<<"$entries"
}
active_work_item_id() {
  local value
  [ -f "$mana/active-workspace" ] && ! [ -L "$mana/active-workspace" ] || return 0
  value="$(sed -n '1p' "$mana/active-workspace")"
  case "$value" in
    .mana/features/[A-Za-z0-9._-]*) [ "$(dirname "$value")" = .mana/features ] && printf 'feature:%s\n' "${value##*/}" ;;
    .mana/sessions/[A-Za-z0-9._-]*) [ "$(dirname "$value")" = .mana/sessions ] && printf 'session:%s\n' "${value##*/}" ;;
  esac
}
semantic_summary() {
  local type="$1" wsid="$2" dir="$3" entries="$4" manifest="$dir/manifest.yaml" wid="$type:$wsid"
  local branch purpose feature canonical artifacts diagnostics lifecycle attention review
  diagnostics='[]'; branch=''; purpose=''; feature=''; canonical='null'
  if [ -f "$manifest" ] && ! [ -L "$manifest" ]; then
    [ "$(manifest_scalar "$manifest" workspace_type)" = "$type" ] && [ "$(manifest_scalar "$manifest" workspace_id)" = "$wsid" ] || diagnostics='[{"id":"manifest-identity","kind":"malformed_canonical_source","severity":"warning","provenance":"canonical_path","related_artifact_ids":[]}]'
    branch="$(manifest_scalar "$manifest" branch)"; purpose="$(manifest_scalar "$manifest" purpose)"; feature="$(manifest_scalar "$manifest" feature_id)"; canonical="$(manifest_scalar "$manifest" canonical_branch)"
  else diagnostics='[{"id":"manifest-unavailable","kind":"unavailable_source","severity":"warning","provenance":"canonical_path","related_artifact_ids":[]}]'; fi
  case "$canonical" in true|false) ;; *) canonical=null;; esac
  artifacts="$(semantic_artifacts "$entries" "$wid")"
  lifecycle='{"state":"unknown","provenance":"unavailable","coverage":"unknown"}'
  [ "$(active_work_item_id)" = "$wid" ] && lifecycle='{"state":"in_progress","provenance":"canonical_path","coverage":"explicit_structured_only"}'
  jq -e 'any(.[]; .status=="failed")' <<<"$artifacts" >/dev/null && lifecycle='{"state":"failed","provenance":"explicit_workspace_manifest","coverage":"explicit_structured_only"}'
  jq -e 'any(.[]; .status=="blocked")' <<<"$artifacts" >/dev/null && lifecycle='{"state":"blocked","provenance":"explicit_workspace_manifest","coverage":"explicit_structured_only"}'
  attention="$(jq -c --arg wid "$wid" '[.[]|select(.status=="failed")|{id:("failed-verification:"+.artifact_id),category:"failed_verification",severity:"error",work_item_id:$wid,label:null,next_action:null,related_artifact_ids:[.artifact_id],provenance:"explicit_workspace_manifest"}]' <<<"$artifacts")"
  while IFS='|' read -r artifact path; do
    [ -f "$root/$path" ] && ! [ -L "$root/$path" ] && jq -e '.staleness=="stale"' "$root/$path" >/dev/null 2>&1 || continue
    attention="$(jq -c --arg wid "$wid" --arg artifact "$artifact" '. + [{id:("stale-evidence:"+$artifact),category:"stale_evidence",severity:"warning",work_item_id:$wid,label:null,next_action:null,related_artifact_ids:[$artifact],provenance:"explicit_workspace_manifest"}]' <<<"$attention")"
  done < <(jq -r '.[]|select(.path|endswith(".json"))|[.artifact_id,.path]|join("|")' <<<"$artifacts")
  if [ -f "$dir/decisions/developer-choice-log.md" ] && ! [ -L "$dir/decisions/developer-choice-log.md" ] && grep -Fq '| needs_owner_review |' "$dir/decisions/developer-choice-log.md"; then
    attention="$(jq -c --arg wid "$wid" '. + [{id:"pending-decision:developer-choice-log",category:"pending_decision",severity:"warning",work_item_id:$wid,label:null,next_action:null,related_artifact_ids:[("file:.mana/"+($wid|sub(":";"s/"))+"/decisions/developer-choice-log.md")],provenance:"conservative_fallback"}]' <<<"$attention")"
  fi
  review='{"state":"unknown","provenance":"unavailable","coverage":"unknown"}'
  jq -cn --arg wid "$wid" --arg type "$type" --arg feature "$feature" --arg branch "$branch" --arg purpose "$purpose" --argjson canonical "$canonical" --argjson lifecycle "$lifecycle" --argjson review "$review" --argjson attention "$attention" --argjson artifacts "$artifacts" --argjson diagnostics "$diagnostics" '{summary:{work_item_id:$wid,work_item_type:$type,external_ticket_id:{value:(if $feature=="" or $feature=="null" then null else $feature end),provenance:(if $feature=="" or $feature=="null" then "unavailable" else "explicit_workspace_manifest" end)},title:{value:null,provenance:"unavailable"},purpose:{value:(if $purpose=="" then null else $purpose end),provenance:(if $purpose=="" then "unavailable" else "explicit_workspace_manifest" end)},branch:{value:(if $branch=="" then null else $branch end),provenance:(if $branch=="" then "unavailable" else "explicit_workspace_manifest" end)},canonical_branch:$canonical,lifecycle:$lifecycle,review:$review,attention_items:$attention,artifacts:$artifacts},diagnostics:$diagnostics}'
}
semantic_workspaces() {
  local entries="$1" rootdir type dir wsid
  for rootdir in "$mana/features" "$mana/sessions"; do
    [ -d "$rootdir" ] && ! [ -L "$rootdir" ] || continue
    type="$(basename "$rootdir")"; [ "$type" = features ] && type=feature || type=session
    while IFS= read -r -d '' dir; do wsid="$(basename "$dir")"; [[ "$wsid" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || continue; semantic_summary "$type" "$wsid" "$dir" "$entries"; done < <(find -P "$rootdir" -mindepth 1 -maxdepth 1 -type d -print0 | LC_ALL=C sort -z)
  done
}
context_response() {
  local entries categories category selector artifacts
  entries="$(catalog)"
  categories='[]'
  for category in architecture project_decisions integrations engineering_guards glossary learning_journeys testing_policy database_policy; do
    case "$category" in architecture) selector=.mana/global/architecture.md;; project_decisions) selector=.mana/global/team-decisions/;; integrations) selector=.mana/global/integration-map.md;; engineering_guards) selector=.mana/global/engineering-guards.md;; glossary) selector=.mana/global/domain-glossary.md;; learning_journeys) selector=.mana/learning/journeys/;; testing_policy) selector=.mana/global/testing-policy.md;; database_policy) selector=.mana/global/database-policy.md;; esac
    artifacts="$(jq -c --arg p "$selector" '[.[]|select(if ($p|endswith("/")) then (.path|startswith($p)) else .path==$p end)|{artifact_id,path,kind,status,work_item_id:null,section_id:null,label:null}]' <<<"$entries")"
    categories="$(jq -c --arg c "$category" --argjson a "$artifacts" '.+[{category:$c,artifacts:$a,coverage:(if ($a|length)>0 then "canonical_path_category" else "missing" end)}]' <<<"$categories")"
  done
  jq -cn --argjson categories "$categories" '{schema:"mana.inspect.project-context/v1",categories:$categories,coverage:(if ($categories|map(.artifacts|length)|add)==0 then "none" else "canonical_global_context" end),diagnostics:[],guarantees:{model_calls:0,writes:false,semantic_inference:"canonical_structured_sources_only"}}'
}
activity_response() {
  local entries events
  entries="$(catalog)"
  events="$(jq -cn --argjson e "$entries" --arg root "$root" '
    [$e[] | select(.path|endswith(".json")) | . as $a |
      ($root+"/"+$a.path) as $f |
      try ([$f] | .[0]) catch empty ]' 2>/dev/null)"
  # JSONL runtime events and structured verification timestamps are authoritative.
  events='[]'
  while IFS= read -r -d '' file; do
    path="$(rel "$file")"; ws="$(workspace "$path")"; artifact="$(jq -r --arg p "$path" '.[]|select(.path==$p)|.artifact_id' <<<"$entries")"
    while IFS= read -r line; do
      jq -e '(.eventId|type=="string") and (.timestamp|type=="string")' <<<"$line" >/dev/null 2>&1 || continue
      event="$(jq -cn --argjson v "$line" --arg artifact "$artifact" --argjson ws "$([ "$ws" = null ] && echo null || jq -Rn --arg x "$ws" '$x')" '{event_id:$v.eventId,timestamp:{value:$v.timestamp,provenance:"explicit_domain_timestamp"},event_kind:"unknown",work_item_id:$ws,related_artifact_ids:[$artifact],summary:null,provenance:"explicit_workspace_manifest"}')"
      events="$(jq -c --argjson x "$event" '.+[$x]' <<<"$events")"
    done < "$file"
  done < <(find -P "$mana/runtime/events" -type f -name '*.jsonl' -print0 2>/dev/null | LC_ALL=C sort -z)
  while IFS='|' read -r artifact path ws; do
    file="$root/$path"; [ -f "$file" ] || continue
    stamp="$(jq -r 'if .kind=="verification-result" then (.generatedAt // .finishedAt // empty) else empty end' "$file" 2>/dev/null)"
    [ -n "$stamp" ] && jq -e --arg t "$stamp" '$t|fromdateiso8601' >/dev/null 2>&1 || continue
    event="$(jq -cn --arg id "verification:$artifact" --arg t "$stamp" --arg artifact "$artifact" --argjson ws "$([ "$ws" = null ] && echo null || jq -Rn --arg x "$ws" '$x')" '{event_id:$id,timestamp:{value:$t,provenance:"explicit_domain_timestamp"},event_kind:"verification_completed",work_item_id:$ws,related_artifact_ids:[$artifact],summary:null,provenance:"explicit_workspace_manifest"}')"
    events="$(jq -c --argjson x "$event" '.+[$x]' <<<"$events")"
  done < <(jq -r '.[]|[.artifact_id,.path,(.workspace//"null")]|join("|")' <<<"$entries")
  # Artifact updates are the only mtime fallback and retain that explicit basis.
  fallback="$(jq -c '[.[]|select(.updated_at.provenance=="filesystem_mtime_epoch" and (.updated_at.value|test("^[0-9]+$")))|{event_id:("artifact-update:"+.artifact_id),timestamp:{value:.updated_at.value,provenance:"filesystem_mtime_epoch"},event_kind:"artifact_updated",work_item_id:.workspace,related_artifact_ids:[.artifact_id],summary:null,provenance:"conservative_fallback"}]' <<<"$entries")"
  events="$(jq -c --argjson f "$fallback" '.+$f' <<<"$events")"
  jq -cn --argjson e "$events" '{schema:"mana.inspect.activity/v1",events:($e|unique_by(.event_id)|sort_by((if .timestamp.provenance=="explicit_domain_timestamp" then (.timestamp.value|fromdateiso8601) else (.timestamp.value|tonumber) end),.event_id)),coverage:(if ($e|length)==0 then "none" elif any($e[]; .timestamp.provenance=="filesystem_mtime_epoch") then "explicit_and_filesystem_fallback" else "explicit_structured_events" end),diagnostics:[],guarantees:{model_calls:0,writes:false,semantic_inference:"canonical_structured_sources_only"}}'
}
work_items_response() {
  local entries items
  entries="$(catalog)"; items="$(semantic_workspaces "$entries" | jq -sc 'sort_by(.summary.work_item_id)')"
  response="$(jq -cn --argjson items "$items" '{schema:"mana.inspect.work-items/v1",work_items:[$items[].summary],coverage:(if ($items|length)==0 then "none" else "canonical_workspace_manifests" end),diagnostics:[$items[].diagnostics[]],guarantees:{model_calls:0,writes:false,semantic_inference:"canonical_structured_sources_only"}}')"
  printf '%s\n' "$response"
}
work_item_response() {
  local entries type wsid dir item artifacts sections
  [[ "$target" =~ ^(feature|session):[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || fail "unsafe or malformed work-item ID"
  type="${target%%:*}"; wsid="${target#*:}"; dir="$mana/${type}s/$wsid"; [ -d "$dir" ] && ! [ -L "$dir" ] || fail "work item not found"
  entries="$(catalog)"; item="$(semantic_summary "$type" "$wsid" "$dir" "$entries")"; artifacts="$(jq -c .summary.artifacts <<<"$item")"
  sections="$(jq -cn --argjson a "$artifacts" '["overview","requirements","plan","decisions","evidence","review","timeline","artifacts"]|map(. as $section | {section_id:$section,artifacts:[$a[]|select(.section_id==$section)],summary:null})')"
  response="$(jq -cn --argjson item "$item" --argjson sections "$sections" '{schema:"mana.inspect.work-item/v1",work_item:$item.summary,sections:$sections,attention_items:$item.summary.attention_items,coverage:"canonical_workspace_artifacts",diagnostics:$item.diagnostics,guarantees:{model_calls:0,writes:false,semantic_inference:"canonical_structured_sources_only"}}')"
  printf '%s\n' "$response"
}
validate_and_emit() {
  local response="$1" contract="$2"
  case "$contract" in
    project)
      jq -e 'type=="object" and (keys|sort)==["capabilities","diagnostics","framework","git","guarantees","mana","operations","project_id","schema"] and .schema=="mana.inspect.project/v1" and (.project_id|test("^project:[0-9a-f]{64}$")) and (.framework=={version:"0.4.1",compatibility:"mana-inspect/v1"}) and (.mana|type=="object") and (.git|type=="object") and (.capabilities|type=="array") and (.operations|type=="array") and (.guarantees=={model_calls:0,writes:false,paths:"project_relative_only"}) and (.diagnostics|type=="array")' <<<"$response" >/dev/null || internal "project response violated mana.inspect.project/v1"
      ;;
    artifacts)
      jq -e 'type=="object" and (keys|sort)==["artifacts","diagnostics","guarantees","schema"] and .schema=="mana.inspect.artifacts/v1" and (.guarantees=={model_calls:0,writes:false,paths:"project_relative_only"}) and (.diagnostics|type=="array") and (.artifacts|type=="array") and all(.artifacts[]; (keys|sort)==["artifact_id","byte_size","class","content_type","diagnostic","family","kind","path","relations","revision_id","schema","status","updated_at","workspace"] and (.artifact_id|type=="string") and (.revision_id|test("^sha256:[0-9a-f]{64}$")) and (.path|test("^\\.mana/")) and (.byte_size|type=="number") and (.relations|type=="array"))' <<<"$response" >/dev/null || internal "catalog response violated mana.inspect.artifacts/v1"
      ;;
    artifact)
      jq -e 'type=="object" and (keys|sort)==["artifact","diagnostics","guarantees","payload","relations","schema"] and .schema=="mana.inspect.artifact/v1" and (.artifact|type=="object") and (.payload|type=="object") and (.relations|type=="array") and (.guarantees=={model_calls:0,writes:false,relation_coverage:"explicit_structured_only"}) and (.diagnostics|type=="array")' <<<"$response" >/dev/null || internal "artifact response violated mana.inspect.artifact/v1"
      ;;
    source)
      jq -e 'type=="object" and (keys|sort)==["coverage","diagnostics","guarantees","relations","schema","source"] and .schema=="mana.inspect.source/v1" and (.source|type=="object" and (.path|type=="string") and (.availability|IN("present","missing"))) and (.relations|type=="array") and (.coverage|IN("explicit_journey_anchors","unknown")) and (.guarantees=={model_calls:0,writes:false,relation_coverage:"explicit_structured_only"}) and (.diagnostics|type=="array")' <<<"$response" >/dev/null || internal "source response violated mana.inspect.source/v1"
      ;;
    *) internal "unsupported inspect contract validation" ;;
  esac
  printf '%s\n' "$response"
}
if [ "$command" = project ]; then
  remote="$(git -C "$root" remote get-url origin 2>/dev/null || true)"; [ -n "$remote" ] && id="project:$(hash_text "remote:$remote")" || id="project:$(hash_text "root:$root")"
  branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unavailable)"; head="$(git -C "$root" rev-parse HEAD 2>/dev/null || echo unavailable)"; dirty=false; if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1 && [ -n "$(git -C "$root" status --porcelain --untracked-files=normal 2>/dev/null)" ]; then dirty=true; fi
  active=null; if [ -f "$mana/active-workspace" ] && ! [ -L "$mana/active-workspace" ]; then value="$(sed -n '1p' "$mana/active-workspace")"; case "$value" in .mana/features/*|.mana/sessions/*) active="$(jq -Rn --arg x "$value" '$x')";; esac; fi
  response="$(jq -cn --arg project_id "$id" --arg branch "$branch" --arg head "$head" --argjson dirty "$dirty" --argjson present "$([ -d "$mana" ] && echo true || echo false)" --argjson active "$active" '{schema:"mana.inspect.project/v1",project_id:$project_id,framework:{version:"0.4.1",compatibility:"mana-inspect/v1"},mana:{present:$present,active_workspace:$active},git:{branch:$branch,head:$head,working_tree_dirty:$dirty},capabilities:(if $present then ["workspace","artifact_catalog","artifact_detail","source_relations","semantic_work_items","semantic_project_context","semantic_activity"] else [] end),operations:[{name:"project",schema:"mana.inspect.project/v1"},{name:"artifacts",schema:"mana.inspect.artifacts/v1"},{name:"artifact",schema:"mana.inspect.artifact/v1"},{name:"source",schema:"mana.inspect.source/v1"},{name:"work-items",schema:"mana.inspect.work-items/v1"},{name:"work-item",schema:"mana.inspect.work-item/v1"},{name:"project-context",schema:"mana.inspect.project-context/v1"},{name:"activity",schema:"mana.inspect.activity/v1"}],guarantees:{model_calls:0,writes:false,paths:"project_relative_only"},diagnostics:[]}')"
  validate_and_emit "$response" project
elif [ "$command" = artifacts ]; then
  entries="$(catalog)"; response="$(jq -cn --argjson artifacts "$entries" '{schema:"mana.inspect.artifacts/v1",artifacts:$artifacts,guarantees:{model_calls:0,writes:false,paths:"project_relative_only"},diagnostics:[]}')"; validate_and_emit "$response" artifacts
elif [ "$command" = artifact ]; then
  artifact_detail
elif [ "$command" = work-items ]; then
  work_items_response
elif [ "$command" = work-item ]; then
  work_item_response
elif [ "$command" = project-context ]; then
  context_response
elif [ "$command" = activity ]; then
  activity_response
else
  source_detail
fi
