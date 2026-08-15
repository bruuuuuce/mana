#!/usr/bin/env bash
# Host-owned disposable workspace materialization and candidate import helpers.
# This is faulty-provider containment, not an OS security boundary.

MANA_REPAIR_CONTAINMENT_CAPABILITY="faulty-contained"
MANA_REPAIR_CONTAINMENT_BACKEND="disposable-workspace"
MANA_REPAIR_PROJECTION_EXCLUSIONS='.git/,.mana/,untracked target/,build/,out/,.gradle/,node_modules/'

repair_file_mode() {
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null
}

repair_projection_generated_path() {
  case "/$1/" in
    */target/*|*/build/*|*/out/*|*/.gradle/*|*/node_modules/*) return 0 ;;
    *) return 1 ;;
  esac
}

repair_projection_control_path() {
  case "/$1/" in
    */.git/*|*/.mana/*) return 0 ;;
    *) return 1 ;;
  esac
}

repair_projection_path_tracked() {
  git -C "$1" ls-files --error-unmatch -- "$2" >/dev/null 2>&1
}

repair_materialize_workspace() {
  # $1 live project, $2 empty destination. Copies current worktree contents,
  # including pre-existing dirty files. Host control state is never copied.
  local source="$1" destination="$2" absolute relative parent
  [ -d "$source" ] && [ -d "$destination" ] || return 1
  while IFS= read -r -d '' absolute; do
    relative="${absolute#"$source"/}"
    repair_safe_path "$relative" || return 1
    repair_projection_control_path "$relative" && continue
    if repair_projection_generated_path "$relative" && ! repair_projection_path_tracked "$source" "$relative"; then
      continue
    fi
    if [ -L "$absolute" ]; then
      return 1
    elif [ -d "$absolute" ]; then
      mkdir -p "$destination/$relative" || return 1
    elif [ -f "$absolute" ]; then
      parent="${relative%/*}"; [ "$parent" != "$relative" ] || parent=.
      mkdir -p "$destination/$parent" || return 1
      cp -p "$absolute" "$destination/$relative" || return 1
    else
      return 1
    fi
  done < <(find "$source" -mindepth 1 \( -name .git -o -name .mana \) -prune -o -print0)
}

repair_workspace_manifest() {
  # $1 workspace root, $2 JSON output, $3 scratch directory.
  local workspace="$1" output="$2" scratch="$3" absolute relative type mode digest
  local jsonl="$scratch/manifest.$$.jsonl"
  : > "$jsonl" || return 1
  [ -d "$workspace" ] || return 1
  while IFS= read -r -d '' absolute; do
    relative="${absolute#"$workspace"/}"
    repair_safe_path "$relative" || return 1
    mode="$(repair_file_mode "$absolute")" || return 1
    if [ -L "$absolute" ]; then
      type=symlink; digest="$(readlink "$absolute" | verification_digest_text)" || return 1
    elif [ -f "$absolute" ]; then
      type="file"; digest="$(verification_digest_file "$absolute")" || return 1
    elif [ -d "$absolute" ]; then
      type=directory; digest=unavailable
    else
      type=other; digest=unavailable
    fi
    jq -cn --arg path "$relative" --arg type "$type" --arg mode "$mode" --arg digest "$digest" \
      '{path:$path,type:$type,mode:$mode,digest:$digest}' >> "$jsonl" || return 1
  done < <(find "$workspace" -mindepth 1 -print0)
  jq -s 'sort_by(.path)' "$jsonl" > "$output" || return 1
}

repair_candidate_delta() {
  # $1 staged baseline manifest, $2 post-provider manifest, $3 JSON output.
  jq -n --slurpfile before "$1" --slurpfile after "$2" '
    ($before[0] | map({key:.path,value:.}) | from_entries) as $b |
    ($after[0] | map({key:.path,value:.}) | from_entries) as $a |
    ([($b|keys[]),($a|keys[])] | unique | sort |
      map(select(($b[.] // null) != ($a[.] // null)))) as $paths |
    {changedPaths:$paths,changes:[$paths[] as $p | {path:$p,before:($b[$p] // null),after:($a[$p] // null)}]}
  ' > "$3"
}

repair_supported_text_file() {
  [ -f "$1" ] && [ ! -L "$1" ] || return 1
  perl -e 'local $/; my $v = <>; exit(index($v, "\0") >= 0 ? 1 : 0)' "$1"
}

repair_prepare_import() {
  # $1 candidate, $2 live target, $3 mode, $4 expected candidate digest.
  # The caller revalidates the live baseline after this preparation and then
  # publishes with repair_publish_import, keeping the compare/rename gap small.
  local candidate="$1" target="$2" mode="$3" expected="$4" sibling
  MANA_REPAIR_IMPORT_TEMP=""
  sibling="$(mktemp "$(dirname "$target")/.mana-repair-import.XXXXXX")" || return 1
  if ! cp "$candidate" "$sibling" || ! chmod "$mode" "$sibling" ||
     [ "$(verification_digest_file "$sibling")" != "$expected" ]; then
    rm -f "$sibling"
    return 1
  fi
  MANA_REPAIR_IMPORT_TEMP="$sibling"
}

repair_publish_import() {
  [ -n "${1:-}" ] && [ -f "$1" ] && [ ! -L "$1" ] || return 1
  mv -f "$1" "$2"
}

repair_cleanup_disposable_root() {
  # Only delete the exact unique root created by this attempt.
  local disposable_root="$1" temp_base="${TMPDIR:-/tmp}"
  temp_base="${temp_base%/}"
  case "$disposable_root" in
    "$temp_base"/mana-repair-workspace.*) rm -rf "$disposable_root" ;;
    *) return 1 ;;
  esac
}
