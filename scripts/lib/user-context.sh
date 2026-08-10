#!/usr/bin/env bash
# Shared configuration, status, and materialization helpers for the optional
# User Context Layer. The external source is always treated as read-only.
# Public functions intentionally return status through MANA_UC_* globals.
# shellcheck disable=SC2034

mana_user_context_reset() {
  MANA_UC_CONFIGURED=false
  MANA_UC_CONFIG_SOURCE=none
  MANA_UC_SOURCE=""
  MANA_UC_SOURCE_USABLE=false
  MANA_UC_MATERIALIZED=false
  MANA_UC_FRESHNESS=unavailable
  MANA_UC_FILE_COUNT=0
  MANA_UC_SKIPPED_COUNT=0
  MANA_UC_DIGEST=""
  MANA_UC_ERROR=""
}

mana_user_context_config_file() {
  if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    case "$XDG_CONFIG_HOME" in /*) printf '%s/mana/config.env' "$XDG_CONFIG_HOME";; *) return 1;; esac
  elif [ -n "${HOME:-}" ]; then
    case "$HOME" in /*) printf '%s/.config/mana/config.env' "$HOME";; *) return 1;; esac
  else
    printf '%s' ""
  fi
}

mana_user_context_parse_config() {
  local file="$1" parsed
  parsed="$(awk '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    /^[[:space:]]*MANA_USER_CONTEXT_ROOT[[:space:]]*=/ {
      count++
      if (count > 1) { invalid=1; next }
      line=$0
      sub(/^[[:space:]]*MANA_USER_CONTEXT_ROOT[[:space:]]*=[[:space:]]*/, "", line)
      sub(/[[:space:]]*$/, "", line)
      print line
    }
    END { if (invalid) exit 2 }
  ' "$file")" || return 1
  case "$parsed" in
    \"*\") [ "${parsed%\"}" != "$parsed" ] || return 1; parsed="${parsed#\"}"; parsed="${parsed%\"}" ;;
    \'*\') [ "${parsed%\'}" != "$parsed" ] || return 1; parsed="${parsed#\'}"; parsed="${parsed%\'}" ;;
  esac
  printf '%s' "$parsed"
}

mana_user_context_resolve_config() {
  mana_user_context_reset
  local config_file value
  if [ "${MANA_USER_CONTEXT_ROOT+x}" = x ]; then
    MANA_UC_CONFIG_SOURCE=environment
    value="$MANA_USER_CONTEXT_ROOT"
  else
    if ! config_file="$(mana_user_context_config_file)"; then
      MANA_UC_ERROR="invalid User Context configuration: XDG_CONFIG_HOME and HOME must be absolute"
      MANA_UC_FRESHNESS=invalid
      return 1
    fi
    if [ -n "$config_file" ] && [ -f "$config_file" ]; then
      MANA_UC_CONFIG_SOURCE=user-config
      if ! value="$(mana_user_context_parse_config "$config_file")"; then
        MANA_UC_ERROR="invalid User Context configuration: expected one MANA_USER_CONTEXT_ROOT assignment"
        MANA_UC_FRESHNESS=invalid
        return 1
      fi
    else
      return 0
    fi
  fi
  [ -n "$value" ] || return 0
  case "$value" in
    /*) ;;
    *) MANA_UC_ERROR="invalid User Context configuration: MANA_USER_CONTEXT_ROOT must be absolute"; MANA_UC_FRESHNESS=invalid; return 1 ;;
  esac
  MANA_UC_CONFIGURED=true
  MANA_UC_SOURCE="$value"
}

mana_user_context_builtin_excluded() {
  local rel="$1" base
  base="${rel##*/}"
  case "/$rel/" in
    */.git/*|*/node_modules/*|*/build/*|*/target/*|*/dist/*|*/coverage/*|*/.ssh/*|*/.aws/*|*/.gnupg/*) return 0 ;;
  esac
  case "$base" in
    .manaignore|.DS_Store|.env|.env.*|*.key|*.pem|*.p12|*.jks) return 0 ;;
  esac
  return 1
}

mana_user_context_supported_text() {
  local lower
  lower="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    *.md|*.markdown|*.txt|*.rst|*.adoc) return 0 ;;
    *) return 1 ;;
  esac
}

mana_user_context_ignored() {
  local source="$1" rel="$2" git_dir="$3" ignore_worktree
  [ -f "$source/.manaignore" ] && [ ! -L "$source/.manaignore" ] || return 1
  ignore_worktree="${git_dir%/*}/ignore-worktree"
  git --git-dir="$git_dir" --work-tree="$ignore_worktree" \
    -c core.excludesFile="$source/.manaignore" \
    check-ignore --no-index -q -- "$rel" 2>/dev/null
}

# Writes a sorted tab-delimited manifest: hash, size, relative path.
# Sets MANA_UC_FILE_COUNT, MANA_UC_SKIPPED_COUNT, and MANA_UC_DIGEST.
mana_user_context_inventory() {
  local source="$1" manifest="$2" scratch="$3" git_dir candidates file rel size hash total=0
  git_dir="$scratch/ignore.git"
  candidates="$scratch/candidates"
  git init --bare -q "$git_dir" >/dev/null 2>&1 || return 1
  mkdir -p "$scratch/ignore-worktree" || return 1
  find "$source" \
    -type d \( -name .git -o -name node_modules -o -name build -o -name target -o -name dist -o -name coverage -o -name .ssh -o -name .aws -o -name .gnupg \) -prune -o \
    -type f -print0 > "$candidates" 2>/dev/null || return 1
  : > "$manifest"
  MANA_UC_FILE_COUNT=0
  MANA_UC_SKIPPED_COUNT=0
  while IFS= read -r -d '' file; do
    rel="${file#"$source"/}"
    case "$rel" in *$'\n'*|*$'\t'*|*'|'*) MANA_UC_SKIPPED_COUNT=$((MANA_UC_SKIPPED_COUNT + 1)); continue ;; esac
    if mana_user_context_builtin_excluded "$rel" ||
       ! mana_user_context_supported_text "$rel" ||
       mana_user_context_ignored "$source" "$rel" "$git_dir"; then
      MANA_UC_SKIPPED_COUNT=$((MANA_UC_SKIPPED_COUNT + 1))
      continue
    fi
    size="$(wc -c < "$file" | tr -d ' ')"
    if [ "$size" -gt 1048576 ] || ! LC_ALL=C grep -Iq '' "$file"; then
      MANA_UC_SKIPPED_COUNT=$((MANA_UC_SKIPPED_COUNT + 1))
      continue
    fi
    total=$((total + size))
    [ "$MANA_UC_FILE_COUNT" -lt 2000 ] && [ "$total" -le 26214400 ] || return 1
    hash="$(git hash-object "$file" 2>/dev/null)" || return 1
    printf '%s\t%s\t%s\n' "$hash" "$size" "$rel" >> "$manifest"
    MANA_UC_FILE_COUNT=$((MANA_UC_FILE_COUNT + 1))
  done < "$candidates"
  LC_ALL=C sort -o "$manifest" "$manifest"
  MANA_UC_DIGEST="$(git hash-object "$manifest" 2>/dev/null)" || return 1
}

# Verifies that a generated mirror contains exactly the expected safe files.
# It rejects writable files/directories and all links or special file types.
mana_user_context_verify_mirror() {
  local target="$1" expected_digest="$2" scratch="$3" manifest candidates file rel size hash total=0 count=0 digest
  [ -d "$target" ] && [ ! -L "$target" ] || return 1
  if find "$target" -type l -print -quit | grep -q . ||
     find "$target" ! -type d ! -type f -print -quit | grep -q . ||
     find "$target" \( -type f -o -type d \) \( -perm -0200 -o -perm -0020 -o -perm -0002 \) -print -quit | grep -q .; then
    return 1
  fi
  manifest="$scratch/mirror-manifest"
  candidates="$scratch/mirror-candidates"
  find "$target" -type f -print0 > "$candidates" 2>/dev/null || return 1
  : > "$manifest"
  while IFS= read -r -d '' file; do
    rel="${file#"$target"/}"
    case "$rel" in *$'\n'*|*$'\t'*|*'|'*) return 1;; esac
    mana_user_context_builtin_excluded "$rel" && return 1
    mana_user_context_supported_text "$rel" || return 1
    size="$(wc -c < "$file" | tr -d ' ')"
    [ "$size" -le 1048576 ] && LC_ALL=C grep -Iq '' "$file" || return 1
    total=$((total + size)); count=$((count + 1))
    [ "$count" -le 2000 ] && [ "$total" -le 26214400 ] || return 1
    hash="$(git hash-object "$file" 2>/dev/null)" || return 1
    printf '%s\t%s\t%s\n' "$hash" "$size" "$rel" >> "$manifest"
  done < "$candidates"
  LC_ALL=C sort -o "$manifest" "$manifest"
  digest="$(git hash-object "$manifest" 2>/dev/null)" || return 1
  [ -n "$expected_digest" ] && [ "$digest" = "$expected_digest" ]
}

mana_user_context_local_usable() {
  local project="$1" target state scratch result=1
  target="$project/.mana/user-context"
  state="$project/.mana/user-context-state"
  [ -f "$state" ] || return 1
  mana_user_context_read_state "$state"
  [ "${MANA_UC_STATE_STATUS:-}" = healthy ] && [ -n "${MANA_UC_STATE_DIGEST:-}" ] || return 1
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-context-verify.XXXXXX")" || return 1
  mana_user_context_verify_mirror "$target" "$MANA_UC_STATE_DIGEST" "$scratch" && result=0
  rm -rf "$scratch"
  return "$result"
}

mana_user_context_read_state() {
  local state="$1"
  MANA_UC_STATE_STATUS="$(awk -F= '$1=="status" {print $2; exit}' "$state" 2>/dev/null)"
  MANA_UC_STATE_DIGEST="$(awk -F= '$1=="digest" {print $2; exit}' "$state" 2>/dev/null)"
  MANA_UC_STATE_FILE_COUNT="$(awk -F= '$1=="file_count" {print $2; exit}' "$state" 2>/dev/null)"
  MANA_UC_STATE_SKIPPED_COUNT="$(awk -F= '$1=="skipped_count" {print $2; exit}' "$state" 2>/dev/null)"
}

mana_user_context_write_state() {
  local project="$1" status="$2" digest="$3" count="$4" skipped="$5" state tmp
  state="$project/.mana/user-context-state"
  tmp="$project/.mana/.user-context-state.$$"
  mkdir -p "$project/.mana" || return 1
  printf 'schema=1\nstatus=%s\ndigest=%s\nfile_count=%s\nskipped_count=%s\n' \
    "$status" "$digest" "$count" "$skipped" > "$tmp" || return 1
  mv "$tmp" "$state"
}

mana_user_context_mark_unavailable() {
  local project="$1" state="$2" old_digest="" old_count=0 old_skipped=0
  if [ -f "$state" ]; then
    mana_user_context_read_state "$state"
    old_digest="${MANA_UC_STATE_DIGEST:-}"
    old_count="${MANA_UC_STATE_FILE_COUNT:-0}"
    old_skipped="${MANA_UC_STATE_SKIPPED_COUNT:-0}"
  fi
  mana_user_context_write_state "$project" unavailable "$old_digest" "$old_count" "$old_skipped" || true
}

mana_user_context_validate_source() {
  local project="$1" source_real project_real
  [ "$MANA_UC_CONFIGURED" = true ] || return 1
  if [ ! -d "$MANA_UC_SOURCE" ]; then MANA_UC_ERROR="configured User Context source directory does not exist"; return 1; fi
  if [ ! -r "$MANA_UC_SOURCE" ] || [ ! -x "$MANA_UC_SOURCE" ]; then MANA_UC_ERROR="configured User Context source directory is unreadable"; return 1; fi
  source_real="$(cd "$MANA_UC_SOURCE" 2>/dev/null && pwd -P)" || { MANA_UC_ERROR="configured User Context source directory is unreadable"; return 1; }
  project_real="$(cd "$project" 2>/dev/null && pwd -P)" || { MANA_UC_ERROR="project root is unavailable"; return 1; }
  case "$source_real/" in "$project_real/"*) MANA_UC_ERROR="User Context source must be outside the project root"; return 1 ;; esac
  case "$project_real/" in "$source_real/"*) MANA_UC_ERROR="User Context source must not contain the project root"; return 1 ;; esac
  MANA_UC_SOURCE="$source_real"
  MANA_UC_SOURCE_USABLE=true
}

mana_user_context_status() {
  local project="$1" target state scratch manifest source_digest source_count source_skipped
  target="$project/.mana/user-context"
  state="$project/.mana/user-context-state"
  [ -d "$target" ] && MANA_UC_MATERIALIZED=true
  mana_user_context_resolve_config || { [ -d "$target" ] && MANA_UC_MATERIALIZED=true; return 0; }
  [ -d "$target" ] && MANA_UC_MATERIALIZED=true
  if [ -f "$state" ]; then
    mana_user_context_read_state "$state"
    MANA_UC_FILE_COUNT="${MANA_UC_STATE_FILE_COUNT:-0}"
    MANA_UC_SKIPPED_COUNT="${MANA_UC_STATE_SKIPPED_COUNT:-0}"
    MANA_UC_DIGEST="${MANA_UC_STATE_DIGEST:-}"
  fi
  if [ "$MANA_UC_CONFIGURED" != true ]; then
    MANA_UC_FRESHNESS=disabled
    return 0
  fi
  if ! mana_user_context_validate_source "$project"; then
    MANA_UC_FRESHNESS=unavailable
    return 0
  fi
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-context-status.XXXXXX")" || { MANA_UC_ERROR="cannot create status scratch directory"; MANA_UC_FRESHNESS=broken; return 0; }
  manifest="$scratch/manifest"
  if ! mana_user_context_inventory "$MANA_UC_SOURCE" "$manifest" "$scratch"; then
    rm -rf "$scratch"
    MANA_UC_ERROR="cannot inventory configured User Context source"
    MANA_UC_FRESHNESS=broken
    return 0
  fi
  source_digest="$MANA_UC_DIGEST"
  source_count="$MANA_UC_FILE_COUNT"
  source_skipped="$MANA_UC_SKIPPED_COUNT"
  if [ "$MANA_UC_MATERIALIZED" = true ] &&
     [ "${MANA_UC_STATE_STATUS:-}" = healthy ] &&
     [ -n "${MANA_UC_STATE_DIGEST:-}" ] &&
     [ "$source_digest" = "$MANA_UC_STATE_DIGEST" ] &&
     mana_user_context_verify_mirror "$target" "$source_digest" "$scratch"; then
    MANA_UC_FRESHNESS=current
  elif [ "$MANA_UC_MATERIALIZED" = true ]; then
    MANA_UC_FRESHNESS=stale
  else
    MANA_UC_FRESHNESS=not-materialized
  fi
  MANA_UC_DIGEST="$source_digest"
  MANA_UC_FILE_COUNT="$source_count"
  MANA_UC_SKIPPED_COUNT="$source_skipped"
  rm -rf "$scratch"
}

mana_user_context_cleanup_generated_path() {
  local path="$1"
  if [ -L "$path" ]; then
    rm -f "$path"
  elif [ -d "$path" ]; then
    chmod -R u+w "$path" 2>/dev/null || true
    rm -rf "$path"
  elif [ -e "$path" ]; then
    rm -f "$path"
  fi
}

mana_user_context_acquire_lock() {
  local lock="$1" pid
  if mkdir "$lock" 2>/dev/null; then
    printf '%s\n' "$$" > "$lock/pid"
    return 0
  fi
  pid="$(sed -n '1p' "$lock/pid" 2>/dev/null || true)"
  case "$pid" in ''|*[!0-9]*) :;; *) kill -0 "$pid" 2>/dev/null && return 1;; esac
  mana_user_context_cleanup_generated_path "$lock"
  mkdir "$lock" 2>/dev/null || return 1
  printf '%s\n' "$$" > "$lock/pid"
}

mana_user_context_release_lock() {
  mana_user_context_cleanup_generated_path "$1"
}

# Removes abandoned stages and restores the one possible interrupted backup.
# Call only while holding the project-local refresh lock.
mana_user_context_recover() {
  local project="$1" target path backup="" backup_count=0
  target="$project/.mana/user-context"
  if { [ -e "$target" ] || [ -L "$target" ]; } && { [ ! -d "$target" ] || [ -L "$target" ]; }; then
    mana_user_context_cleanup_generated_path "$target"
  fi
  for path in "$project/.mana"/.user-context-refresh.*; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    mana_user_context_cleanup_generated_path "$path"
  done
  for path in "$project/.mana"/.user-context-previous.*; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    if [ -d "$target" ] && [ ! -L "$target" ]; then
      mana_user_context_cleanup_generated_path "$path"
    else
      backup="$path"
      backup_count=$((backup_count + 1))
    fi
  done
  if [ ! -d "$target" ] && [ "$backup_count" -eq 1 ] && [ -d "$backup" ] && [ ! -L "$backup" ]; then
    mv "$backup" "$target" || return 1
  elif [ ! -d "$target" ] && [ "$backup_count" -gt 1 ]; then
    return 1
  fi
}

mana_user_context_refresh_locked() {
  local project="$1" target state scratch manifest stage backup hash size rel
  target="$project/.mana/user-context"
  state="$project/.mana/user-context-state"
  if ! mana_user_context_resolve_config; then
    [ -d "$target" ] && MANA_UC_MATERIALIZED=true
    mana_user_context_mark_unavailable "$project" "$state"
    return 2
  fi
  [ -d "$target" ] && MANA_UC_MATERIALIZED=true
  if [ "$MANA_UC_CONFIGURED" != true ]; then
    if [ -e "$target" ] || [ -L "$target" ]; then mana_user_context_cleanup_generated_path "$target"; fi
    rm -f "$state"
    MANA_UC_FRESHNESS=disabled
    return 0
  fi
  if ! mana_user_context_validate_source "$project"; then
    mana_user_context_mark_unavailable "$project" "$state"
    return 2
  fi
  mkdir -p "$project/.mana" || return 2
  scratch="$(mktemp -d "$project/.mana/.user-context-refresh.XXXXXX")" || return 2
  manifest="$scratch/manifest"
  if ! mana_user_context_inventory "$MANA_UC_SOURCE" "$manifest" "$scratch"; then rm -rf "$scratch"; MANA_UC_ERROR="cannot inventory configured User Context source"; mana_user_context_mark_unavailable "$project" "$state"; return 2; fi
  if [ -f "$state" ] && [ -d "$target" ]; then
    mana_user_context_read_state "$state"
    if [ "${MANA_UC_STATE_DIGEST:-}" = "$MANA_UC_DIGEST" ] &&
       [ "${MANA_UC_STATE_STATUS:-}" = healthy ] &&
       mana_user_context_verify_mirror "$target" "$MANA_UC_DIGEST" "$scratch"; then
      rm -rf "$scratch"
      MANA_UC_MATERIALIZED=true
      MANA_UC_FRESHNESS=current
      return 0
    fi
  fi
  stage="$scratch/tree"
  mkdir -p "$stage" || { rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
  while IFS=$'\t' read -r hash size rel; do
    [ -n "$rel" ] || continue
    mkdir -p "$(dirname "$stage/$rel")" || { rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
    if [ ! -f "$MANA_UC_SOURCE/$rel" ] || [ -L "$MANA_UC_SOURCE/$rel" ]; then
      rm -rf "$scratch"
      MANA_UC_ERROR="source changed during refresh"
      mana_user_context_mark_unavailable "$project" "$state"
      return 2
    fi
    cp -P "$MANA_UC_SOURCE/$rel" "$stage/$rel" || { rm -rf "$scratch"; MANA_UC_ERROR="failed to copy User Context file"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
    [ "$(git hash-object "$stage/$rel" 2>/dev/null)" = "$hash" ] || { rm -rf "$scratch"; MANA_UC_ERROR="source changed during refresh"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
  done < "$manifest"
  if find "$stage" -type l -print -quit | grep -q .; then rm -rf "$scratch"; MANA_UC_ERROR="symlink encountered during refresh"; mana_user_context_mark_unavailable "$project" "$state"; return 2; fi
  find "$stage" -type f -exec chmod 0444 {} + || { rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
  find "$stage" -type d -exec chmod 0555 {} + || { rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
  # macOS rename requires the staged directory itself to remain writable.
  chmod 0755 "$stage" || { rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }
  backup="$project/.mana/.user-context-previous.$$"
  if [ -d "$target" ]; then mv "$target" "$backup" || { chmod -R u+w "$stage" 2>/dev/null || true; rm -rf "$scratch"; mana_user_context_mark_unavailable "$project" "$state"; return 2; }; fi
  if ! mv "$stage" "$target"; then
    [ ! -d "$backup" ] || mv "$backup" "$target"
    chmod -R u+w "$scratch" 2>/dev/null || true
    rm -rf "$scratch"
    mana_user_context_mark_unavailable "$project" "$state"
    return 2
  fi
  if ! chmod 0555 "$target"; then
    chmod -R u+w "$target" 2>/dev/null || true
    rm -rf "$target"
    [ ! -d "$backup" ] || mv "$backup" "$target"
    chmod -R u+w "$scratch" 2>/dev/null || true
    rm -rf "$scratch"
    mana_user_context_mark_unavailable "$project" "$state"
    return 2
  fi
  if ! mana_user_context_write_state "$project" healthy "$MANA_UC_DIGEST" "$MANA_UC_FILE_COUNT" "$MANA_UC_SKIPPED_COUNT"; then
    chmod -R u+w "$target" 2>/dev/null || true
    rm -rf "$target"
    [ ! -d "$backup" ] || mv "$backup" "$target"
    chmod -R u+w "$scratch" 2>/dev/null || true
    rm -rf "$scratch"
    mana_user_context_mark_unavailable "$project" "$state"
    return 2
  fi
  if [ -d "$backup" ]; then chmod -R u+w "$backup" 2>/dev/null || true; rm -rf "$backup"; fi
  chmod -R u+w "$scratch" 2>/dev/null || true
  rm -rf "$scratch"
  MANA_UC_MATERIALIZED=true
  MANA_UC_FRESHNESS=current
}

mana_user_context_refresh() {
  local project="$1" lock result
  lock="$project/.mana/user-context-refresh.lock"
  mkdir -p "$project/.mana" || return 2
  if ! mana_user_context_acquire_lock "$lock"; then
    MANA_UC_ERROR="another User Context refresh is already running"
    return 2
  fi
  trap 'mana_user_context_recover "$project" >/dev/null 2>&1 || true; mana_user_context_release_lock "$lock"; exit 130' HUP INT TERM
  if ! mana_user_context_recover "$project"; then
    MANA_UC_ERROR="cannot recover an interrupted User Context refresh"
    result=2
  elif mana_user_context_refresh_locked "$project"; then
    result=0
  else
    result=$?
  fi
  trap - HUP INT TERM
  mana_user_context_release_lock "$lock"
  return "$result"
}
