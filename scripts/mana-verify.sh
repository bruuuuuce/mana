#!/usr/bin/env bash
# Deterministic Verification Skills runner. This command never invokes a model
# runner and never accepts executable free-form commands.
set -u

root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/verification.sh"
. "$root/scripts/lib/runtime-events.sh"

project_root="$(pwd)"; dry_run=false; explain=false; json=false; list_only=false
base=""; explicit_skills=""; rerun_file=""; rerun_check=""; rerun_path=""; rerun_digest=""; rerun_reference=""; rerun_run=""; newline=$'\n'; tab=$'\t'
usage() { cat <<'USAGE'
Usage: mana verify [--skill <id>] [--list] [--dry-run] [--explain] [--json] [--base <ref>]
       mana verify --rerun <verification-result.json> --check <check-id> [--json]

Runs bounded deterministic Verification Skills. It never starts Codex, Claude,
OpenCode, Junie, or another model runner.
USAGE
}
fail() { echo "ERROR: $*" >&2; exit 2; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-root) project_root="${2:-}"; [ -n "$project_root" ] || fail '--project-root requires a path'; shift 2;;
    --skill) value="${2:-}"; [ -n "$value" ] || fail '--skill requires an id'; explicit_skills="${explicit_skills}${explicit_skills:+$newline}$value"; shift 2;;
    --base) base="${2:-}"; [ -n "$base" ] || fail '--base requires a ref'; shift 2;;
    --rerun) rerun_file="${2:-}"; [ -n "$rerun_file" ] || fail '--rerun requires a result path'; shift 2;;
    --check) rerun_check="${2:-}"; [ -n "$rerun_check" ] || fail '--check requires an id'; shift 2;;
    --list) list_only=true; shift;; --dry-run) dry_run=true; shift;; --explain) explain=true; shift;; --json) json=true; shift;;
    --help|-h) usage; exit 0;; *) fail "unknown option: $1";;
  esac
done
command -v jq >/dev/null 2>&1 || fail 'jq is required for mana verify'
project_root="$(cd "$project_root" 2>/dev/null && pwd -P)" || fail "project root not found: $project_root"

if [ -n "$rerun_file" ]; then
  [ -n "$rerun_check" ] || fail '--rerun requires --check'
  [ -f "$rerun_file" ] || fail "rerun evidence not found: $rerun_file"
  rerun_file="$(cd "$(dirname "$rerun_file")" && pwd -P)/$(basename "$rerun_file")"
  case "$rerun_file" in "$project_root"/.mana/*/evidence/verification/*/result.json) ;; *) fail 'rerun evidence must be a canonical project-local verification result' ;; esac
  verification_result_validate "$rerun_file" || fail 'rerun evidence is malformed or non-canonical'
  [ "$(jq -r .schemaVersion "$rerun_file")" = 2 ] || fail 'verification evidence predates repair-capable schema; rerun verification first'
  [ "$(jq --arg id "$rerun_check" '[.checks[]|select(.checkId==$id)]|length' "$rerun_file")" = 1 ] || fail "rerun check is missing or ambiguous: $rerun_check"
  rerun_digest="$(verification_digest_file "$rerun_file")"
  [ -f "$(dirname "$rerun_file")/result.sha256" ] && [ "$(sed -n '1p' "$(dirname "$rerun_file")/result.sha256")" = "$rerun_digest" ] || fail 'rerun evidence digest sidecar is missing or mismatched'
  rerun_path="$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.rerunDescriptor.path' "$rerun_file")"
  verification_safe_repository_path "$rerun_path" || fail 'rerun descriptor contains an unsafe repository path'
  [ "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.rerunDescriptor.kind' "$rerun_file")" = repository_path ] || fail 'unsupported rerun descriptor kind'
  rerun_skill="$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.skillId' "$rerun_file")"
  rerun_adapter="$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.adapter' "$rerun_file")"
  [ "$rerun_adapter" = bash_syntax ] || fail "rerun adapter is not supported by the bounded rerun path: $rerun_adapter"
  rerun_skill_file="$root/skills/$rerun_skill/SKILL.md"; rerun_spec_file="$root/skills/$rerun_skill/verification.yaml"
  [ "$(verification_frontmatter_field "$rerun_skill_file" version)" = "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.skillVersion' "$rerun_file")" ] || fail 'rerun skill version identity changed'
  [ "$(verification_digest_file "$rerun_spec_file")" = "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.specDigest' "$rerun_file")" ] || fail 'rerun verification spec identity changed'
  [ "$(cat "$root/scripts/mana-verify.sh" "$root/scripts/lib/verification.sh" | verification_digest_text)" = "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.adapterImplementationDigest' "$rerun_file")" ] || fail 'rerun adapter implementation identity changed'
  rerun_bash="$(command -v bash 2>/dev/null || true)"; [ -f "$rerun_bash" ] || fail 'rerun bash executable is unavailable'
  [ "$(verification_digest_file "$rerun_bash")" = "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.executable.digest' "$rerun_file")" ] || fail 'rerun executable identity changed'
  [ "$(verification_environment_digest)" = "$(jq -r --arg id "$rerun_check" '.checks[]|select(.checkId==$id)|.environmentDigest' "$rerun_file")" ] || fail 'rerun environment identity changed'
  explicit_skills="$rerun_skill"; rerun_run="$(jq -r .runId "$rerun_file")"; rerun_reference="${rerun_file#"$project_root"/}"
fi
[ -z "$rerun_check" ] || [ -n "$rerun_file" ] || fail '--check is only valid with --rerun'

verification_skills() { awk '$1=="-"&&$2=="id:"{id=$3} $1=="capability:"&&$2=="verification"{print id}' "$root/skills/index.yaml" | LC_ALL=C sort; }
skill_known() { printf '%s\n' "$(verification_skills)" | grep -Fxq "$1"; }

if [ "$list_only" = true ]; then
  skills="$(verification_skills)"
  if [ "$json" = true ]; then
    printf '%s\n' "$skills" | jq -Rsc --argjson schema 1 '{schemaVersion:$schema,verificationSkills:(split("\n")|map(select(length>0))),modelCalls:0}'
  else
    echo 'MANA VERIFICATION SKILLS'; printf '%s\n' "$skills" | sed 's/^/- /'; echo 'Model calls: 0'
  fi
  exit 0
fi
command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 || fail 'a SHA-256 tool (sha256sum or shasum) is required for mana verify'

while IFS= read -r requested; do
  [ -z "$requested" ] || skill_known "$requested" || fail "unknown verification skill: $requested"
done <<EOF
$explicit_skills
EOF

tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-verify.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
selection_dir="$tmp/selection"; action_file="$tmp/actions.tsv"; mkdir -p "$selection_dir"; : > "$action_file"

repo_available=false; head_ref=unknown; project_revision=unknown; dirty_before=false; scope_status=resolved; scope_mode=repository
changed_file="$tmp/changed"; changed_raw="$tmp/changed.raw"; unsafe_path_file="$tmp/unsafe-path"; : > "$changed_file"; : > "$changed_raw"
if git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  repo_available=true
  if git -C "$project_root" rev-parse --verify HEAD >/dev/null 2>&1; then
    head_ref="$(git -C "$project_root" rev-parse HEAD)"
    project_revision="$(git -C "$project_root" rev-parse --short HEAD)"
  else
    head_ref=unknown; project_revision=workspace
  fi
  [ -z "$(git -C "$project_root" status --porcelain 2>/dev/null)" ] || dirty_before=true
  if [ -n "$base" ]; then
    git -C "$project_root" rev-parse --verify "$base^{commit}" >/dev/null 2>&1 || fail "base ref is not available: $base"
  else
    upstream="$(git -C "$project_root" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    remote_head="$(git -C "$project_root" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    if [ -n "$upstream" ]; then base="$upstream"
    elif [ -n "$remote_head" ]; then base="$remote_head"
    else
      candidates=""
      for candidate in origin/main origin/master origin/develop origin/dev main master develop dev; do git -C "$project_root" rev-parse --verify "$candidate^{commit}" >/dev/null 2>&1 && candidates="${candidates}${candidates:+$newline}$candidate"; done
      count="$(printf '%s\n' "$candidates" | sed '/^$/d' | wc -l | tr -d ' ')"
      if [ "$count" -eq 1 ]; then base="$candidates"
      elif [ "$count" -gt 1 ]; then scope_status=ambiguous
      else base=HEAD; scope_mode=working-tree-only
      fi
    fi
  fi
  if [ "$scope_status" = resolved ]; then
    if [ "$base" != HEAD ]; then git -C "$project_root" diff --name-only -z --diff-filter=ACMRTD "$base...HEAD" >> "$changed_raw" 2>/dev/null || true; fi
    git -C "$project_root" diff --name-only -z --diff-filter=ACMRTD >> "$changed_raw" 2>/dev/null || true
    git -C "$project_root" diff --cached --name-only -z --diff-filter=ACMRTD >> "$changed_raw" 2>/dev/null || true
    git -C "$project_root" ls-files --others --exclude-standard -z >> "$changed_raw" 2>/dev/null || true
    while IFS= read -r -d '' path; do
      case "$path" in *$'\t'*|*$'\n'*) : > "$unsafe_path_file";; *) printf '%s\n' "$path";; esac
    done < "$changed_raw" | LC_ALL=C sort -u > "$changed_file"
    if [ -n "$rerun_file" ]; then printf '%s\n' "$rerun_path" > "$changed_file"; fi
  fi
else
  scope_status=blocked
fi
changed_paths="$(cat "$changed_file")"; changed_digest="$(printf '%s\n' "$changed_paths" | verification_digest_text)"

glob_matches() { local pattern="$1" path; while IFS= read -r path; do [ -n "$path" ] || continue; case "$path" in $pattern) return 0;; esac; done < "$changed_file"; return 1; }
predicate_evaluate() {
  local predicate="$1" type path ext pattern; type="$(jq -r .type <<<"$predicate")"; PRED_DETAIL=""
  case "$type" in
    repository_available) if [ "$repo_available" = true ]; then PRED_DETAIL="Git repository available at project root"; return 0; else PRED_DETAIL="project root is not a Git repository"; return 1; fi;;
    explicit_invocation) if [ "$SKILL_EXPLICIT" = true ]; then PRED_DETAIL="skill was explicitly requested"; return 0; else PRED_DETAIL="skill was not explicitly requested"; return 1; fi;;
    changed_extension)
      while IFS= read -r ext; do while IFS= read -r path; do case "$path" in *."$ext") PRED_DETAIL="changed path $path has .$ext extension"; return 0;; esac; done < "$changed_file"; done < <(jq -r '.extensions[]' <<<"$predicate")
      PRED_DETAIL="no changed path has a declared extension"; return 1;;
    changed_path)
      while IFS= read -r pattern; do if glob_matches "$pattern"; then PRED_DETAIL="changed paths match $pattern"; return 0; fi; done < <(jq -r '.patterns[]' <<<"$predicate")
      PRED_DETAIL="changed paths match none of the declared patterns"; return 1;;
    manifest_exists)
      while IFS= read -r path; do if [ -e "$project_root/$path" ]; then PRED_DETAIL="repository evidence exists: $path"; return 0; fi; done < <(jq -r '.paths[]' <<<"$predicate")
      PRED_DETAIL="none of the declared repository evidence paths exists"; return 1;;
    *) PRED_DETAIL="unsupported predicate $type"; return 1;;
  esac
}

selected_skills=""; selected_count=0
for skill in $(verification_skills); do
  if [ -n "$explicit_skills" ] && ! printf '%s\n' "$explicit_skills" | grep -Fxq "$skill"; then continue; fi
  SKILL_EXPLICIT=false; printf '%s\n' "$explicit_skills" | grep -Fxq "$skill" && SKILL_EXPLICIT=true || true
  spec_name="$(verification_index_field "$root/skills/index.yaml" "$skill" verification_spec)"; spec="$root/skills/$skill/$spec_name"
  verification_spec_validate "$spec" "$skill" || fail "verification spec became invalid: $spec"
  reasons="$tmp/reasons-$skill.jsonl"; : > "$reasons"; all_pass=true; any_pass=false; any_count=0
  while IFS= read -r predicate; do
    if predicate_evaluate "$predicate"; then passed=true; else passed=false; all_pass=false; fi
    jq -cn --arg group all --arg type "$(jq -r .type <<<"$predicate")" --arg detail "$PRED_DETAIL" --argjson pass "$passed" '{group:$group,predicate:$type,pass:$pass,detail:$detail}' >> "$reasons"
  done < <(jq -c '.applicability.all[]' "$spec")
  while IFS= read -r predicate; do
    any_count=$((any_count+1)); if predicate_evaluate "$predicate"; then passed=true; any_pass=true; else passed=false; fi
    jq -cn --arg group any --arg type "$(jq -r .type <<<"$predicate")" --arg detail "$PRED_DETAIL" --argjson pass "$passed" '{group:$group,predicate:$type,pass:$pass,detail:$detail}' >> "$reasons"
  done < <(jq -c '.applicability.any[]' "$spec")
  [ "$any_count" -eq 0 ] && any_pass=true
  applicability=not_applicable; selected=false
  if [ "$scope_status" = ambiguous ]; then applicability=blocked
  elif [ "$scope_status" = blocked ]; then applicability=blocked
  elif [ "$all_pass" = true ] && [ "$any_pass" = true ]; then applicability=applicable; selected=true; fi
  if [ "$selected" = true ] && [ "$SKILL_EXPLICIT" != true ] && [ "$selected_count" -ge "$MANA_VERIFY_MAX_AUTO_SKILLS" ]; then applicability=blocked; selected=false; jq -cn '{group:"budget",predicate:"max_auto_skills",pass:false,detail:"automatic skill budget reached"}' >> "$reasons"; fi
  if [ "$selected" = true ]; then selected_count=$((selected_count+1)); selected_skills="${selected_skills}${selected_skills:+$newline}$skill"; fi
  jq -s --arg skill "$skill" --arg result "$applicability" --argjson selected "$selected" --arg mode "$([ "$SKILL_EXPLICIT" = true ] && echo explicit || echo automatic)" '{skillId:$skill,mode:$mode,applicability:$result,selected:$selected,reasons:.}' "$reasons" > "$selection_dir/$skill.json"
done

scenario_profile() { sed -n 's/^\*\*Profile:\*\* `\([^`]*\)`.*/\1/p' "$1/scenario.md" | head -n1; }
select_scenarios() {
  local broad=false path id profile changed_skill changed_agent p scenario
  [ "$SKILL_EXPLICIT" = true ] && broad=true
  while IFS= read -r path; do
    case "$path" in
      skills/index.yaml|scripts/mana-eval.sh|scripts/lib/execution-plan.sh|scripts/lib/profile-metadata.sh) broad=true;;
      evals/scenarios/*/*) id="${path#evals/scenarios/}"; printf '%s\n' "${id%%/*}";;
      profiles/*.yaml) profile="$(basename "$path" .yaml)"; for scenario in "$root"/evals/scenarios/*; do [ "$(scenario_profile "$scenario")" = "$profile" ] && basename "$scenario"; done;;
      skills/*/SKILL.md) changed_skill="${path#skills/}"; changed_skill="${changed_skill%%/*}"; for p in "$root"/profiles/*.yaml; do grep -Eq "^- $changed_skill$|^  - $changed_skill$" "$p" || continue; profile="$(basename "$p" .yaml)"; for scenario in "$root"/evals/scenarios/*; do [ "$(scenario_profile "$scenario")" = "$profile" ] && basename "$scenario"; done; done;;
      agents/*/AGENT.md|agents/*/playbook.md) changed_agent="${path#agents/}"; changed_agent="${changed_agent%%/*}"; for p in "$root"/profiles/*.yaml; do grep -Eq "^- $changed_agent$|^  - $changed_agent$" "$p" || continue; profile="$(basename "$p" .yaml)"; for scenario in "$root"/evals/scenarios/*; do [ "$(scenario_profile "$scenario")" = "$profile" ] && basename "$scenario"; done; done;;
    esac
  done < "$changed_file"
  if [ "$broad" = true ]; then
    find "$root/evals/scenarios" -mindepth 2 -maxdepth 2 -type f -name eval.yaml -print | while IFS= read -r manifest; do basename "$(dirname "$manifest")"; done
  fi
}
catalog_field_for_id() { local catalog="$1" id="$2" key="$3"; awk -v target="$id" -v key="$key" '/^  - id: / {if(a)exit;v=$0;sub(/^  - id: "/,"",v);sub(/"$/,"",v);a=(v==target);next} a && $0 ~ "^    " key ": " {v=$0;sub("^    " key ": ","",v);gsub(/^"|"$/,"",v);print v;exit}' "$catalog"; }
catalog_entry_count() { awk -v target="$2" '/^  - id: / {v=$0;sub(/^  - id: "/,"",v);sub(/"$/,"",v);if(v==target)n++} END{print n+0}' "$1"; }
find_testbook() {
  local candidate relative canonical
  for candidate in "$project_root/.mana/global/testbook.yaml" "$project_root/.mana/testbook.yaml"; do
    if [ -f "$candidate" ]; then canonical="$(cd "$(dirname "$candidate")" && pwd -P)/$(basename "$candidate")"; case "$canonical" in "$project_root"/.mana/*) printf '%s\n' "$canonical"; return;; esac; fi
  done
  if [ -f "$project_root/.mana/active-workspace" ]; then
    relative="$(sed -n '1p' "$project_root/.mana/active-workspace")"
    case "$relative" in .mana/features/*|.mana/sessions/*) candidate="$project_root/$relative/tests/testbook.yaml";; *) return;; esac
    if [ -f "$candidate" ]; then canonical="$(cd "$(dirname "$candidate")" && pwd -P)/$(basename "$candidate")"; case "$canonical" in "$project_root"/.mana/*) printf '%s\n' "$canonical";; esac; fi
  fi
}

add_action() { # skill version specDigest baseId instanceId adapter target timeout cost trust effects scope required skillMaxSeconds skillMaxOutput
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}" "${13}" "${14}" "${15}" >> "$action_file"
}
for skill in $selected_skills; do
  SKILL_EXPLICIT=false; printf '%s\n' "$explicit_skills" | grep -Fxq "$skill" && SKILL_EXPLICIT=true || true
  skill_file="$root/skills/$skill/SKILL.md"; version="$(verification_frontmatter_field "$skill_file" version)"; spec="$root/skills/$skill/$(verification_frontmatter_field "$skill_file" verification_spec)"; spec_digest="$(verification_digest_file "$spec")"; skill_max_seconds="$(jq -r .limits.max_seconds "$spec")"; skill_max_output="$(jq -r .limits.max_output_bytes "$spec")"
  while IFS= read -r check; do
    check_id="$(jq -r .id <<<"$check")"; adapter="$(jq -r .adapter <<<"$check")"; timeout_seconds="$(jq -r .timeout_seconds <<<"$check")"; cost="$(jq -r .cost <<<"$check")"; trust="$(jq -r .trust_origin <<<"$check")"; effects="$(jq -c .effects <<<"$check")"; scope="$(jq -r .scope <<<"$check")"; required="$(jq -r .required <<<"$check")"
    case "$adapter" in
      bash_syntax)
        while IFS= read -r path; do case "$path" in *.sh|hooks/pre-commit|hooks/pre-push) instance="$skill--bash-syntax-$(printf '%s' "$path" | verification_digest_text | cut -d: -f2 | cut -c1-16)"; add_action "$skill" "$version" "$spec_digest" "$check_id" "$instance" "$adapter" "$path" "$timeout_seconds" "$cost" "$trust" "$effects" "$scope" "$required" "$skill_max_seconds" "$skill_max_output";; esac; done < "$changed_file";;
      mana_eval)
        scenarios="$(select_scenarios | sed '/^$/d' | LC_ALL=C sort -u)"; [ -n "$scenarios" ] || scenarios="$(find "$root/evals/scenarios" -mindepth 2 -maxdepth 2 -type f -name eval.yaml -print | while IFS= read -r manifest; do basename "$(dirname "$manifest")"; done | LC_ALL=C sort -u)"
        while IFS= read -r scenario; do [ -n "$scenario" ] || continue; add_action "$skill" "$version" "$spec_digest" "$check_id" "$skill--mana-eval-$scenario" "$adapter" "$scenario" "$timeout_seconds" "$cost" "$trust" "$effects" "$scope" "$required" "$skill_max_seconds" "$skill_max_output"; done <<EOF
$scenarios
EOF
        ;;
      java_approved_test)
        manifest=; entry=; tool=; expected_command=; expected_origin=; expected_prerequisite=
        if [ -f "$project_root/pom.xml" ]; then manifest=pom.xml; entry=maven-unit-test; tool=maven; expected_origin=pom_or_test_layout; expected_prerequisite=java_and_maven; expected_command=mvn; [ -x "$project_root/mvnw" ] && expected_command=./mvnw
        elif [ -f "$project_root/build.gradle" ] || [ -f "$project_root/build.gradle.kts" ]; then manifest="$([ -f "$project_root/build.gradle.kts" ] && echo build.gradle.kts || echo build.gradle)"; entry=gradle-unit-test; tool=gradle; expected_origin=build_file; expected_prerequisite=java_or_gradle; expected_command=gradle; [ -x "$project_root/gradlew" ] && expected_command=./gradlew; fi
        catalog="$(find_testbook | head -n1)"; actual_trust=derived; target="blocked:$tool:$entry:$manifest:no-approved-structured-entry"
        catalog_timeout="${catalog:+$(catalog_field_for_id "$catalog" "$entry" timeout_seconds)}"
        if [ "$SKILL_EXPLICIT" != true ]; then target="blocked:$tool:$entry:$manifest:explicit-skill-invocation-required"
        elif [ -n "$catalog" ] && [ "$(catalog_entry_count "$catalog" "$entry")" = 1 ] && [ "$(catalog_field_for_id "$catalog" "$entry" kind)" = unit ] && [ "$(catalog_field_for_id "$catalog" "$entry" command)" = "$expected_command test" ] && [ "$(catalog_field_for_id "$catalog" "$entry" command_origin)" = "$expected_origin" ] && [ "$(catalog_field_for_id "$catalog" "$entry" source)" = "$manifest" ] && [ "$(catalog_field_for_id "$catalog" "$entry" prerequisites)" = "$expected_prerequisite" ] && [ "$(catalog_field_for_id "$catalog" "$entry" approved)" = true ] && [ "$(catalog_field_for_id "$catalog" "$entry" execution_status)" = runnable ] && [ "$(catalog_field_for_id "$catalog" "$entry" environment)" = local ] && [ "$(catalog_field_for_id "$catalog" "$entry" safety)" = normal ] && [[ "$catalog_timeout" =~ ^[0-9]+$ ]] && [ "$catalog_timeout" -ge 1 ] && [ "$catalog_timeout" -le "$timeout_seconds" ]; then
          actual_trust=project_approved; timeout_seconds="$catalog_timeout"; target="approved:$tool:$entry:$manifest:${catalog#"$project_root"/}"
        fi
        add_action "$skill" "$version" "$spec_digest" "$check_id" "$skill--$check_id" "$adapter" "$target" "$timeout_seconds" "$cost" "$actual_trust" "$effects" "$scope" "$required" "$skill_max_seconds" "$skill_max_output";;
    esac
  done < <(jq -c '.checks[]' "$spec")
done

if [ -n "$rerun_file" ]; then
  [ "$(awk -F'\t' -v id="$rerun_check" '$5==id{n++} END{print n+0}' "$action_file")" = 1 ] || fail 'current skill/spec no longer resolves the originating rerun target'
  awk -F'\t' -v id="$rerun_check" '$5==id' "$action_file" > "$tmp/rerun-action"
  mv "$tmp/rerun-action" "$action_file"
fi

action_count="$(wc -l < "$action_file" | tr -d ' ')"; plan_blockers=""
[ "$scope_status" = ambiguous ] && plan_blockers="diff base is ambiguous; provide --base <ref>"
[ "$scope_status" = blocked ] && plan_blockers="project root is not a Git repository"
[ -f "$unsafe_path_file" ] && plan_blockers="${plan_blockers}${plan_blockers:+$newline}changed paths containing tabs or newlines are unsupported in v1"
if [ "$action_count" -gt "$MANA_VERIFY_MAX_CHECKS" ]; then plan_blockers="${plan_blockers}${plan_blockers:+$newline}planned checks ($action_count) exceed framework maximum ($MANA_VERIFY_MAX_CHECKS)"; fi
for skill in $selected_skills; do
  spec="$root/skills/$skill/$(verification_frontmatter_field "$root/skills/$skill/SKILL.md" verification_spec)"
  skill_max="$(jq -r .limits.max_checks "$spec")"; skill_count="$(awk -F'\t' -v wanted="$skill" '$1==wanted{n++} END{print n+0}' "$action_file")"
  if [ "$skill_count" -gt "$skill_max" ]; then plan_blockers="${plan_blockers}${plan_blockers:+$newline}$skill planned checks ($skill_count) exceed its maximum ($skill_max)"; fi
done

selections_json="$(find "$selection_dir" -type f -name '*.json' -print | LC_ALL=C sort | xargs jq -s '.' 2>/dev/null || printf '[]')"
actions_json() {
  while IFS="$tab" read -r skill version spec_digest base_id instance_id adapter target timeout_seconds cost trust effects scope required skill_max_seconds skill_max_output; do
    [ -n "$skill" ] || continue
    case "$adapter:$target" in
      bash_syntax:*) argv="$(jq -cn --arg path "$target" '["bash","-n","--",$path]')";;
      mana_eval:*) argv="$(jq -cn --arg script "$root/scripts/mana-eval.sh" --arg project "$project_root" --arg scenario "$target" '[$script,"--project-root",$project,"run",$scenario,"--json"]')";;
      java_approved_test:approved:maven:*) wrapper=mvn; [ -x "$project_root/mvnw" ] && wrapper=./mvnw; argv="$(jq -cn --arg w "$wrapper" '[$w,"test"]')";;
      java_approved_test:approved:gradle:*) wrapper=gradle; [ -x "$project_root/gradlew" ] && wrapper=./gradlew; argv="$(jq -cn --arg w "$wrapper" '[$w,"test"]')";;
      java_approved_test:blocked:*) tool="$(printf '%s' "$target" | cut -d: -f2)"; entry="$(printf '%s' "$target" | cut -d: -f3)"; argv="$(jq -cn --arg tool "$tool" --arg entry "$entry" '["proposed",$tool,"testbook-entry",$entry]')";;
      *) argv='[]';;
    esac
    target_fingerprint="$(verification_target_fingerprint "$adapter" "$argv" "$project_root" "$scope")"
    jq -cn --arg skill "$skill" --arg check "$instance_id" --arg baseCheck "$base_id" --arg adapter "$adapter" --arg target "$target" --arg targetFingerprint "$target_fingerprint" --arg trust "$trust" --arg scope "$scope" --arg cost "$cost" --argjson required "$required" --argjson timeout "$timeout_seconds" --argjson effects "$effects" --argjson argv "$argv" --argjson skillMaxSeconds "$skill_max_seconds" --argjson skillMaxOutput "$skill_max_output" '{skillId:$skill,checkId:$check,baseCheckId:$baseCheck,adapter:$adapter,target:$target,targetFingerprint:$targetFingerprint,trustOrigin:$trust,scope:$scope,required:$required,cost:$cost,timeoutSeconds:$timeout,skillLimits:{maxSeconds:$skillMaxSeconds,maxOutputBytes:$skillMaxOutput},effects:$effects,effectiveArgv:$argv}'
  done < "$action_file" | jq -s '.'
}
planned_actions_json="$(actions_json)"

plan_json="$(jq -cn --arg status "$([ -n "$plan_blockers" ] && echo blocked || echo planned)" --arg base "$base" --arg head "$head_ref" --arg mode "$scope_mode" --arg digest "$changed_digest" --argjson dirty "$dirty_before" --argjson changed "$(cat "$changed_file" | verification_json_array_lines)" --argjson selections "$selections_json" --argjson actions "$planned_actions_json" --arg blockers "$plan_blockers" --argjson maxSkills "$MANA_VERIFY_MAX_AUTO_SKILLS" --argjson maxChecks "$MANA_VERIFY_MAX_CHECKS" --argjson maxSeconds "$MANA_VERIFY_MAX_SECONDS" --argjson maxOutput "$MANA_VERIFY_MAX_OUTPUT_BYTES" '{schemaVersion:"1",kind:"verification-plan",status:$status,scope:{base:$base,head:$head,mode:$mode,changedPathsDigest:$digest,changedPaths:$changed},workingTreeDirtyBefore:$dirty,selections:$selections,actions:$actions,blockers:($blockers|split("\n")|map(select(length>0))),limits:{maxAutomaticSkills:$maxSkills,maxChecks:$maxChecks,maxSeconds:$maxSeconds,maxOutputBytesPerCheck:$maxOutput},modelCalls:0,inputTokens:0,outputTokens:0}')"

render_plan_human() {
  echo 'MANA VERIFY PLAN'; echo "status: $(jq -r .status <<<"$plan_json")"; echo "scope: base=$(jq -r .scope.base <<<"$plan_json") head=$(jq -r .scope.head <<<"$plan_json") mode=$(jq -r .scope.mode <<<"$plan_json")"
  echo 'Selections:'; jq -r '.selections[] | "- " + .skillId + ": " + .applicability + (if .selected then " (selected)" else "" end)' <<<"$plan_json"
  if [ "$explain" = true ]; then jq -r '.selections[] | .skillId as $s | .reasons[] | "  - " + $s + ": " + .predicate + "=" + (.pass|tostring) + " — " + .detail' <<<"$plan_json"; fi
  echo 'Checks:'; jq -r '.actions[] | "- " + .skillId + "/" + .checkId + ": adapter=" + .adapter + ", trust=" + .trustOrigin + ", timeout=" + (.timeoutSeconds|tostring) + "s, effects=" + (.effects|tojson) + ", argv=" + (.effectiveArgv|tojson)' <<<"$plan_json"
  jq -r '.blockers[] | "BLOCKED: " + .' <<<"$plan_json"; echo 'Model calls: 0'
}
if [ "$dry_run" = true ]; then if [ "$json" = true ]; then printf '%s\n' "$plan_json"; else render_plan_human; fi; [ -z "$plan_blockers" ]; exit; fi
if [ -n "$plan_blockers" ]; then if [ "$json" = true ]; then printf '%s\n' "$plan_json"; else render_plan_human; fi; exit 1; fi

# Real execution begins here. Planning above creates no Mana workspace or audit files.
umask 077
started_epoch="$(date +%s)"; started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; run_id="verification-$(date -u +%Y%m%dT%H%M%SZ)-$$"
if [ -n "$rerun_file" ]; then
  workspace="${rerun_file%%/evidence/verification/*}"; active_relative="${workspace#"$project_root"/}"
else
  "$root/scripts/mana-workspace.sh" init --root "$project_root" --purpose verification >/dev/null || fail 'workspace initialization failed'
  active_relative="$(sed -n '1p' "$project_root/.mana/active-workspace")"; workspace="$project_root/$active_relative"
fi
evidence_parent="$workspace/evidence/verification"; evidence_dir="$evidence_parent/$run_id"; checks_dir="$evidence_dir/checks"; mkdir -p "$evidence_parent"; mkdir "$evidence_dir" || fail "verification run identity collision: $run_id"; mkdir "$checks_dir"
runtime_init "$project_root" verification || echo "WARNING: $MANA_RUNTIME_WARNING" >&2
runtime_emit verification.started verification "$run_id" started "checks=$action_count modelCalls=0" "${active_relative}/evidence/verification/$run_id" false || true
verification_interrupted() { runtime_emit verification.interrupted verification "$run_id" interrupted "modelCalls=0" "${active_relative}/evidence/verification/$run_id" false || true; runtime_finish failed; exit 130; }
trap verification_interrupted INT TERM

tracked_state_before="$tmp/tracked-state-before"; tracked_paths_before="$tmp/tracked-paths-before"; untracked_before="$tmp/untracked-before"; verification_snapshot_source_state "$project_root" "$tracked_state_before" "$tracked_paths_before" "$untracked_before"
repository_input_digest="$(verification_repository_input_digest "$project_revision" "$tracked_state_before" "$untracked_before")"; environment_digest="$(verification_environment_digest)"

run_bounded() { # timeout output-cap stdout stderr argv...
  local seconds="$1" output_cap="$2" out="$3" err="$4" status_file="$tmp/supervisor-status-$$-$executed"; shift 4
  if ! command -v perl >/dev/null 2>&1; then
    printf '%s\n' 'Perl is required for bounded verification execution.' > "$err"; : > "$out"
    RUN_CODE=125; RUN_SIGNAL=0; RUN_TIMED_OUT=false; RUN_DESCENDANTS_TERMINATED=false; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$err" | tr -d ' ')"; RUN_DURATION_MS=0
  elif ! perl "$root/scripts/lib/verification-exec.pl" --timeout "$seconds" --output-cap "$output_cap" --stdout "$out" --stderr "$err" --status "$status_file" -- "$@"; then
    printf '%s\n' 'Verification execution supervisor failed.' > "$err"; : > "$out"
    RUN_CODE=125; RUN_SIGNAL=0; RUN_TIMED_OUT=false; RUN_DESCENDANTS_TERMINATED=false; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$err" | tr -d ' ')"; RUN_DURATION_MS=0
  else
    IFS="$tab" read -r RUN_CODE RUN_SIGNAL timed_out descendants OUT_BYTES ERR_BYTES RUN_DURATION_MS < "$status_file"
    RUN_TIMED_OUT=false; [ "$timed_out" = 1 ] && RUN_TIMED_OUT=true
    RUN_DESCENDANTS_TERMINATED=false; [ "$descendants" = 1 ] && RUN_DESCENDANTS_TERMINATED=true
  fi
  OUT_TRUNCATED=false; ERR_TRUNCATED=false; [ "$OUT_BYTES" -le "$output_cap" ] || OUT_TRUNCATED=true; [ "$ERR_BYTES" -le "$output_cap" ] || ERR_TRUNCATED=true
}

result_fragments="$tmp/results"; dedup_dir="$tmp/dedup"; mkdir -p "$result_fragments" "$dedup_dir"; executed=0; stop_for_mutation=false
while IFS="$tab" read -r skill version spec_digest base_id instance_id adapter target timeout_seconds cost trust effects scope required skill_max_seconds skill_max_output; do
  [ -n "$skill" ] || continue
  command_origin="$trust"; RUN_SIGNAL=0; RUN_TIMED_OUT=false; RUN_DESCENDANTS_TERMINATED=false; RUN_DURATION_MS=0
  check_dir="$checks_dir/$instance_id"; mkdir -p "$check_dir"; stdout="$check_dir/stdout.log"; stderr="$check_dir/stderr.log"; : > "$stdout"; : > "$stderr"
  case "$adapter:$target" in
    bash_syntax:*) argv_json="$(jq -cn --arg path "$target" '["bash","-n","--",$path]')"; input_digest="$([ -f "$project_root/$target" ] && verification_digest_file "$project_root/$target" || printf missing)";;
    mana_eval:*) argv_json="$(jq -cn --arg script "$root/scripts/mana-eval.sh" --arg project "$project_root" --arg scenario "$target" '[$script,"--project-root",$project,"run",$scenario,"--json"]')"; scenario_digest="$(find "$root/evals/scenarios/$target" -type f -maxdepth 2 -print 2>/dev/null | LC_ALL=C sort | while IFS= read -r f; do verification_digest_file "$f"; done | verification_digest_text)"; input_digest="$(printf '%s\n%s\n' "$repository_input_digest" "$scenario_digest" | verification_digest_text)";;
    java_approved_test:approved:maven:*) wrapper=mvn; command_origin=system_tool; [ -x "$project_root/mvnw" ] && { wrapper=./mvnw; command_origin=repository_script; }; argv_json="$(jq -cn --arg w "$wrapper" '[$w,"test"]')"; input_digest="$repository_input_digest";;
    java_approved_test:approved:gradle:*) wrapper=gradle; command_origin=system_tool; [ -x "$project_root/gradlew" ] && { wrapper=./gradlew; command_origin=repository_script; }; argv_json="$(jq -cn --arg w "$wrapper" '[$w,"test"]')"; input_digest="$repository_input_digest";;
    java_approved_test:blocked:*) argv_json="$(jq -cn --arg target "$target" '["proposed",$target]')"; input_digest="$changed_digest";;
    *) argv_json='[]'; input_digest="$changed_digest";;
  esac
  argv0="$(jq -r '.[0] // ""' <<<"$argv_json")"; executable_path=unavailable; executable_digest=unavailable
  if [ -n "$argv0" ]; then
    case "$argv0" in ./*) [ -f "$project_root/${argv0#./}" ] && executable_path="$(cd "$(dirname "$project_root/${argv0#./}")" && pwd -P)/$(basename "$argv0")";; /*) [ -f "$argv0" ] && executable_path="$argv0";; *) executable_path="$(command -v "$argv0" 2>/dev/null || printf unavailable)";; esac
    [ "$executable_path" = unavailable ] || executable_digest="$(verification_digest_file "$executable_path")"
  fi
  executable_identity="$executable_path|$executable_digest"; effects="$(jq -cS . <<<"$effects")"; contract_digest="$(printf '%s\n%s\n%s\n%s\n%s\n%s\n' "$adapter" "$scope" "$timeout_seconds" "$cost" "$trust" "$effects" | verification_digest_text)"
  target_fingerprint="$(verification_target_fingerprint "$adapter" "$argv_json" "$project_root" "$scope")"
  fingerprint="$(verification_action_fingerprint "$target_fingerprint" "$contract_digest" "$input_digest" "$executable_identity" "$trust" "$effects" "$environment_digest")"
  execution_fingerprint="$(verification_execution_fingerprint "$target_fingerprint" "$input_digest" "$executable_identity" "$trust" "$effects" "$environment_digest" "$timeout_seconds|$skill_max_output")"; fingerprint_key="$(printf '%s' "$execution_fingerprint" | tr ':/' '__')"
  if ! verification_dedup_claim "$dedup_dir" "$execution_fingerprint"; then
    dedup_concern="concern:${skill}:${base_id}:$(printf '%s' "$adapter|$target" | verification_digest_text)"; oracle_path="mana-framework/skills/$skill/verification.yaml"
    jq --arg skill "$skill" --arg version "$version" --arg spec "$spec_digest" --arg check "$instance_id" --arg baseCheck "$base_id" --arg concern "$dedup_concern" --arg oraclePath "$oracle_path" --arg actionFingerprint "$fingerprint" --arg targetFingerprint "$target_fingerprint" --arg executionFingerprint "$execution_fingerprint" --arg scope "$scope" --arg cost "$cost" --argjson effects "$effects" --argjson required "$required" '.checkId as $fromCheck | .skillId=$skill | .skillVersion=$version | .specDigest=$spec | .checkId=$check | .baseCheckId=$baseCheck | .concernKey=$concern | .evaluationSurface |= map(if .role=="oracle" then .path=$oraclePath | .digest=$spec else . end) | .required=$required | .actionFingerprint=$actionFingerprint | .targetFingerprint=$targetFingerprint | .executionFingerprint=$executionFingerprint | .scope=$scope | .costClass=$cost | .declaredEffects=$effects | .deduplicated=true | .deduplicatedFrom=$executionFingerprint | .deduplicatedFromCheckId=$fromCheck' "$dedup_dir/$fingerprint_key.json" > "$result_fragments/$executed.json"
    executed=$((executed+1)); continue
  fi
  if [ "$executed" -ge "$MANA_VERIFY_MAX_CHECKS" ]; then break; fi
  now_epoch="$(date +%s)"; elapsed=$(( now_epoch - started_epoch ))
  skill_clock="$tmp/skill-clock-$skill"; [ -f "$skill_clock" ] || printf '%s\n' "$now_epoch" > "$skill_clock"; skill_elapsed=$(( now_epoch - $(sed -n '1p' "$skill_clock") )); skill_remaining=$(( skill_max_seconds - skill_elapsed )); total_remaining=$(( MANA_VERIFY_MAX_SECONDS - elapsed )); effective_timeout="$timeout_seconds"; [ "$effective_timeout" -le "$skill_remaining" ] || effective_timeout="$skill_remaining"; [ "$effective_timeout" -le "$total_remaining" ] || effective_timeout="$total_remaining"; effective_output="$skill_max_output"; [ "$effective_output" -le "$MANA_VERIFY_MAX_OUTPUT_BYTES" ] || effective_output="$MANA_VERIFY_MAX_OUTPUT_BYTES"
  if [ "$effective_timeout" -le 0 ]; then result=blocked; code=null; printf '%s\n' "Skill or total time budget exhausted before execution." > "$stderr"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false; duration_ms=0
  elif [ "$stop_for_mutation" = true ]; then result=blocked; code=null; printf '%s\n' 'Skipped because an earlier check unexpectedly modified source.' > "$stderr"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false; duration_ms=0
  elif ! verification_trust_executable "$trust"; then result=blocked; code=null; printf '%s\n' "Trust origin is not directly executable in v1: $trust" > "$stderr"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false; duration_ms=0
  elif [ "$adapter" = java_approved_test ] && case "$target" in blocked:*) true;; *) false;; esac; then result=blocked; code=null; printf '%s\n' "Derived Java action is not executable without an approved runnable local testbook entry: $target" > "$stderr"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false; duration_ms=0
  else
    runtime_emit check.started check "$skill/$instance_id" started "adapter=$adapter trust=$trust" "${active_relative}/evidence/verification/$run_id/checks/$instance_id" false || true
    check_start="$(date +%s)"; args=(); while IFS= read -r arg; do args+=("$arg"); done < <(jq -r '.[]' <<<"$argv_json")
    if [ "$adapter" = bash_syntax ] && [ ! -f "$project_root/$target" ]; then result=inconclusive; RUN_CODE=125; printf '%s\n' "Changed shell file is unavailable: $target" > "$stderr"; : > "$stdout"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false
    elif [ "$adapter" = java_approved_test ] && ! command -v "${args[0]}" >/dev/null 2>&1 && [ ! -x "$project_root/${args[0]#./}" ]; then result=inconclusive; RUN_CODE=125; printf '%s\n' "Required build tool is unavailable: ${args[0]}" > "$stderr"; : > "$stdout"; OUT_BYTES=0; ERR_BYTES="$(wc -c < "$stderr" | tr -d ' ')"; OUT_TRUNCATED=false; ERR_TRUNCATED=false
    else old_pwd="$PWD"; cd "$project_root" || fail 'project root became unavailable'; run_bounded "$effective_timeout" "$effective_output" "$stdout" "$stderr" "${args[@]}"; cd "$old_pwd" || fail 'working directory became unavailable'; result=passed; [ "$RUN_CODE" -eq 0 ] || result=failed; [ "$RUN_TIMED_OUT" = true ] && result=inconclusive; [ "$RUN_DESCENDANTS_TERMINATED" = true ] && result=inconclusive; [ "$RUN_CODE" -eq 125 ] && result=inconclusive; fi
    code="$RUN_CODE"; duration_ms="${RUN_DURATION_MS:-$(( ($(date +%s) - check_start) * 1000 ))}"
  fi
  mutation_scratch="$tmp/mutation-after"; mkdir -p "$mutation_scratch"; mutations="$(verification_detect_source_mutations "$project_root" "$tracked_state_before" "$tracked_paths_before" "$untracked_before" "$mutation_scratch")"
  source_mutation=false; if [ -n "$mutations" ]; then source_mutation=true; stop_for_mutation=true; result=inconclusive; fi
  excerpt_file="$tmp/excerpt-$executed"; { sed -n '1,40p' "$stderr"; sed -n '1,40p' "$stdout"; } | head -c 4096 | verification_redact_stream > "$excerpt_file"
  native_artifacts='[]'; eval_failures="$tmp/eval-failures-$executed"; : > "$eval_failures"; native_rejected=false
  if [ "$adapter" = mana_eval ] && jq -e 'type=="object" and (.results|type=="array")' "$stdout" >/dev/null 2>&1; then
    native_lines="$tmp/native-lines-$executed"; : > "$native_lines"
    while IFS= read -r artifact; do
      [ -n "$artifact" ] || continue
      if [ -f "$artifact" ]; then canonical_artifact="$(cd "$(dirname "$artifact")" 2>/dev/null && pwd -P)/$(basename "$artifact")"; else canonical_artifact=unavailable; fi
      case "$canonical_artifact" in "$project_root"/.mana/evaluations/results/*)
        relative_artifact="${canonical_artifact#"$project_root"/}"; printf '%s\n' "$relative_artifact" >> "$native_lines"
        jq -r '.assertions[]? | select(.pass==false) | (.reasonCode + ": " + .reason)' "$canonical_artifact" 2>/dev/null | verification_redact_stream >> "$eval_failures" || true;;
        *) native_rejected=true;;
      esac
    done < <(jq -r '.results[]' "$stdout")
    native_artifacts="$(cat "$native_lines" | verification_json_array_lines)"
  fi
  if [ "$result" = passed ]; then normalized="$(jq -cn --arg id "$base_id" '[{id:$id,result:"satisfied"}]')"
  elif [ "$adapter" = bash_syntax ]; then normalized="$(verification_bash_syntax_observations "$stderr" "$base_id")"
  elif [ "$adapter" = mana_eval ] && [ -s "$eval_failures" ]; then normalized="$(jq -Rn --arg id "$base_id" '[inputs|select(length>0)][0:10] as $lines | [{id:$id,result:"not_satisfied",messages:$lines}]' < "$eval_failures")"
  else normalized="$(jq -Rn --arg id "$base_id" '[inputs|select(length>0)][0:10] as $lines | [{id:$id,result:"not_satisfied",messages:$lines}]' < "$excerpt_file")"; fi
  mutation_json="$(printf '%s\n' "$mutations" | verification_json_array_lines)"; relevant_json="$(printf '%s\n' "$target" | verification_json_array_lines)"
  rel_stdout="${stdout#"$project_root"/}"; rel_stderr="${stderr#"$project_root"/}"; stdout_digest="$(verification_digest_file "$stdout")"; stderr_digest="$(verification_digest_file "$stderr")"
  if [ "$result" = passed ]; then failure_fingerprint=null; else failure_fingerprint="$(printf '%s\n%s\n%s\n' "$target_fingerprint" "$result" "$normalized" | verification_digest_text)"; fi
  limitations="$(jq -cn --arg result "$result" --argjson nativeRejected "$native_rejected" --argjson descendants "$RUN_DESCENDANTS_TERMINATED" --argjson repositoryScript "$([ "$command_origin" = repository_script ] && echo true || echo false)" --argjson truncated "$([ "$OUT_TRUNCATED" = true ] || [ "$ERR_TRUNCATED" = true ] && echo true || echo false)" '[if $result=="blocked" then "Action did not satisfy its trust, approval, effects, or execution budget gate." elif $result=="inconclusive" then "Evidence did not establish a mechanical pass or failure." else empty end, if $nativeRejected then "An eval artifact reference outside project-local Mana evaluation evidence was rejected." else empty end, if $descendants then "Descendant processes outlived the command leader and were terminated." else empty end, if $repositoryScript then "Approved repository code executed without an OS sandbox; deliberately detached processes are outside v1 containment." else empty end, if $truncated then "Command output exceeded the retained artifact limit; byte counts describe discarded output." else empty end]')"
  adapter_digest="$(cat "$root/scripts/mana-verify.sh" "$root/scripts/lib/verification.sh" | verification_digest_text)"
  concern_key="concern:${skill}:${base_id}:$(printf '%s' "$adapter|$target" | verification_digest_text)"
  evaluation_surface="$(jq -cn --arg input "$target" --arg inputDigest "$input_digest" --arg specPath "mana-framework/skills/$skill/verification.yaml" --arg specDigest "$spec_digest" --arg verifierPath "mana-framework/scripts/mana-verify.sh+scripts/lib/verification.sh" --arg verifierDigest "$adapter_digest" '[{role:"mutable_input",path:$input,digest:$inputDigest,protected:false},{role:"oracle",path:$specPath,digest:$specDigest,protected:true},{role:"verifier",path:$verifierPath,digest:$verifierDigest,protected:true}]')"
  rerun_descriptor="$(jq -cn --arg path "$target" '{kind:"repository_path",path:$path}')"
  jq -cn --arg skill "$skill" --arg version "$version" --arg spec "$spec_digest" --arg check "$instance_id" --arg baseCheck "$base_id" --arg adapter "$adapter" --arg adapterDigest "$adapter_digest" --arg concernKey "$concern_key" --arg trust "$trust" --arg commandOrigin "${command_origin:-$trust}" --arg fingerprint "$fingerprint" --arg targetFingerprint "$target_fingerprint" --arg executionFingerprint "$execution_fingerprint" --arg inputDigest "$input_digest" --arg environmentDigest "$environment_digest" --arg executablePath "$executable_path" --arg executableDigest "$executable_digest" --arg failureFingerprint "$failure_fingerprint" --arg scope "$scope" --arg cost "$cost" --arg result "$result" --argjson rerunDescriptor "$rerun_descriptor" --argjson evaluationSurface "$evaluation_surface" --argjson required "$required" --argjson argv "$argv_json" --argjson effects "$effects" --argjson exitCode "$code" --argjson signal "$RUN_SIGNAL" --argjson timedOut "$RUN_TIMED_OUT" --argjson descendants "$RUN_DESCENDANTS_TERMINATED" --argjson duration "$duration_ms" --argjson timeout "$effective_timeout" --argjson outputLimit "$effective_output" --argjson relevant "$relevant_json" --argjson nativeArtifacts "$native_artifacts" --rawfile excerpt "$excerpt_file" --arg stdout "$rel_stdout" --arg stderr "$rel_stderr" --arg stdoutDigest "$stdout_digest" --arg stderrDigest "$stderr_digest" --argjson outBytes "$OUT_BYTES" --argjson errBytes "$ERR_BYTES" --argjson outTruncated "$OUT_TRUNCATED" --argjson errTruncated "$ERR_TRUNCATED" --argjson observations "$normalized" --argjson sourceMutation "$source_mutation" --argjson mutationPaths "$mutation_json" --argjson limitations "$limitations" '{skillId:$skill,skillVersion:$version,specDigest:$spec,checkId:$check,baseCheckId:$baseCheck,required:$required,concernKey:$concernKey,targetFingerprint:$targetFingerprint,actionFingerprint:$fingerprint,executionFingerprint:$executionFingerprint,failureFingerprint:(if $failureFingerprint=="null" then null else $failureFingerprint end),deduplicated:false,adapter:$adapter,adapterImplementationDigest:$adapterDigest,rerunDescriptor:$rerunDescriptor,evaluationSurface:$evaluationSurface,trustOrigin:$trust,commandOrigin:$commandOrigin,effectiveArgv:$argv,executable:{path:$executablePath,digest:$executableDigest},workingDirectory:".",environmentClassification:"local",environmentDigest:$environmentDigest,inputDigest:$inputDigest,scope:$scope,costClass:$cost,result:$result,exitCode:$exitCode,signal:$signal,timedOut:$timedOut,descendantsTerminated:$descendants,durationMs:$duration,timeoutSeconds:$timeout,outputLimitBytes:$outputLimit,relevantFiles:$relevant,observations:$observations,nativeArtifacts:$nativeArtifacts,output:{excerpt:$excerpt,stdoutArtifact:$stdout,stderrArtifact:$stderr,stdoutDigest:$stdoutDigest,stderrDigest:$stderrDigest,stdoutBytes:$outBytes,stderrBytes:$errBytes,stdoutTruncated:$outTruncated,stderrTruncated:$errTruncated},declaredEffects:$effects,observedEffects:{unexpectedSourceMutation:$sourceMutation,mutationPaths:$mutationPaths},limitations:$limitations}' > "$result_fragments/$executed.json"
  cp "$result_fragments/$executed.json" "$dedup_dir/$fingerprint_key.json"
  runtime_emit "check.$result" check "$skill/$instance_id" "$result" "adapter=$adapter exitCode=${code:-none} durationMs=$duration_ms" "${active_relative}/evidence/verification/$run_id/checks/$instance_id" false || true
  executed=$((executed+1))
done < "$action_file"

if [ "$executed" -eq 0 ]; then checks_json='[]'; else checks_json="$(jq -s '.' "$result_fragments"/*.json)"; fi
overall="$(verification_overall_result "$checks_json" "$stop_for_mutation")"
finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; duration_ms=$(( ($(date +%s) - started_epoch) * 1000 )); result_file="$evidence_dir/result.json"; summary_file="$evidence_dir/summary.md"; result_tmp="$evidence_dir/.result.json.tmp.$$"; summary_tmp="$evidence_dir/.summary.md.tmp.$$"
result_relative="${result_file#"$project_root"/}"
framework_digest="$(cat "$root/scripts/mana-verify.sh" "$root/scripts/lib/verification.sh" | verification_digest_text)"
rerun_of="$(if [ -n "$rerun_file" ]; then jq -cn --arg ref "$rerun_reference" --arg digest "$rerun_digest" --arg run "$rerun_run" --arg check "$rerun_check" '{resultReference:$ref,resultDigest:$digest,runId:$run,checkId:$check}'; else printf null; fi)"
jq -n --arg run "$run_id" --arg runtime "$MANA_RUNTIME_EXECUTION_ID" --arg generated "$finished_at" --arg started "$started_at" --arg projectRevision "$project_revision" --arg base "$base" --arg head "$head_ref" --arg mode "$scope_mode" --arg digest "$changed_digest" --arg inputDigest "$repository_input_digest" --arg frameworkDigest "$framework_digest" --arg overall "$overall" --argjson rerunOf "$rerun_of" --argjson dirty "$dirty_before" --argjson changed "$(cat "$changed_file" | verification_json_array_lines)" --argjson selections "$selections_json" --argjson checks "$checks_json" --argjson duration "$duration_ms" --argjson sourceMutation "$stop_for_mutation" '{schemaVersion:"2",kind:"verification-result",runId:$run,runtimeExecutionId:$runtime,generatedAt:$generated,startedAt:$started,projectRevision:$projectRevision,workingTreeDirtyBefore:$dirty,scope:{base:$base,head:$head,mode:$mode,changedPathsDigest:$digest,changedPaths:$changed,inputDigest:$inputDigest},frameworkIdentity:{verificationImplementationDigest:$frameworkDigest},rerunOf:$rerunOf,overallResult:$overall,selections:$selections,checks:$checks,observedEffects:{unexpectedSourceMutation:$sourceMutation},cost:{wallTimeMs:$duration,checksExecuted:($checks|map(select(.deduplicated==false))|length),duplicateActionsSuppressed:($checks|map(select(.deduplicated==true))|length),modelCalls:0,inputTokens:0,outputTokens:0},judgment:null}' > "$result_tmp" || fail 'could not assemble verification result'
verification_result_validate "$result_tmp" || fail 'verification result failed canonical validation'
mv "$result_tmp" "$result_file" || fail 'could not publish verification result'
verification_digest_file "$result_file" > "$evidence_dir/.result.sha256.tmp.$$" && mv "$evidence_dir/.result.sha256.tmp.$$" "$evidence_dir/result.sha256"
{
  echo '# Mana Verification Evidence'; echo; echo "- Run: \`$run_id\`"; echo "- Result: \`$overall\`"; echo "- Base: \`$base\`"; echo "- Head: \`$head_ref\`"; echo '- Model calls: `0`'; echo '- Judgment: _not produced by verification_'; echo; echo '## Selection'; echo; jq -r '.selections[] | "- `" + .skillId + "`: " + .applicability + (if .selected then "; selected" else "" end)' "$result_file"; echo; echo '## Checks'; echo; echo '| Check | Adapter | Trust | Result | Exit | Duration |'; echo '|---|---|---|---|---:|---:|'; jq -r '.checks[] | "| `" + .checkId + "` | `" + .adapter + "` | `" + .trustOrigin + "` | `" + .result + "` | " + ((.exitCode // "-")|tostring) + " | " + (.durationMs|tostring) + " ms |"' "$result_file"; echo; echo '## Evidence'; echo; jq -r '.checks[] | "- `" + .checkId + "`: `" + .output.stdoutArtifact + "`, `" + .output.stderrArtifact + "`."' "$result_file"; echo; echo '## Boundary'; echo; echo 'This artifact contains verification evidence only. Existing reviewers and accountable humans create findings and judgment.'; } > "$summary_tmp"
mv "$summary_tmp" "$summary_file" || fail 'could not publish verification summary'
runtime_emit evidence.created verification "$run_id" created "result=$overall modelCalls=0" "$result_relative" false || true
runtime_emit verification.completed verification "$run_id" "$overall" "checks=$executed sourceMutation=$stop_for_mutation modelCalls=0" "$result_relative" false || true
runtime_finish completed

if [ "$json" = true ]; then cat "$result_file"; else echo 'MANA VERIFY'; echo "result: $overall"; echo "evidence: $result_relative"; echo "runtime execution: $MANA_RUNTIME_EXECUTION_ID"; echo 'model calls: 0'; fi
[ "$overall" = passed ]
