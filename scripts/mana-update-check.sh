#!/usr/bin/env bash
set -u

usage() {
  cat <<'USAGE'
Usage:
  scripts/mana-update-check.sh [options]

Checks whether the local Mana repository appears up to date.
It never pulls, merges, rebases, or modifies files.

Options:
  --root <path>       Mana repository root. Defaults to this script's parent repo.
  --mode <mode>       off, warn, or strict. Defaults to warn.
  --no-fetch          Do not contact the remote; compare only existing refs.
  --profile <name>    Profile requesting the check, used only in messages.
  --help              Show this help.

Environment:
  MANA_UPDATE_CHECK   off, warn, or strict. Overrides default mode.

Exit behavior:
  off     Always exits 0 without checks.
  warn    Prints warnings and exits 0.
  strict  Exits non-zero when Mana is dirty, untracked, missing upstream, or behind.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"
mode="${MANA_UPDATE_CHECK:-warn}"
profile=""
fetch=true

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      root="${2:-}"
      [ -n "$root" ] || fail "--root requires a path"
      shift 2
      ;;
    --mode)
      mode="${2:-}"
      [ -n "$mode" ] || fail "--mode requires off, warn, or strict"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
      shift 2
      ;;
    --no-fetch)
      fetch=false
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

case "$mode" in
  off) exit 0 ;;
  warn|strict) ;;
  *) fail "invalid mode: $mode" ;;
esac

root="$(cd "$root" && pwd)"

warnings=0

note_prefix="Mana update check"
if [ -n "$profile" ]; then
  note_prefix="$note_prefix [$profile]"
fi

warn() {
  echo "WARN: $note_prefix: $*" >&2
  warnings=$((warnings + 1))
}

info() {
  echo "INFO: $note_prefix: $*" >&2
}

if ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  warn "Mana root is not a Git repository: $root"
  [ "$mode" = strict ] && exit 1
  exit 0
fi

branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
head_sha="$(git -C "$root" rev-parse --short HEAD 2>/dev/null || true)"

if [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]; then
  warn "Mana repository has local uncommitted changes at $root"
fi

upstream="$(git -C "$root" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
if [ -z "$upstream" ]; then
  warn "current branch ${branch:-unknown} has no upstream; cannot verify freshness"
else
  if [ "$fetch" = true ]; then
    if git -C "$root" fetch --dry-run --quiet >/dev/null 2>&1; then
      info "remote reachability verified with fetch --dry-run"
    else
      warn "could not contact remote with git fetch --dry-run"
    fi
  fi

  counts="$(git -C "$root" rev-list --left-right --count "HEAD...@{upstream}" 2>/dev/null || true)"
  if [ -n "$counts" ]; then
    ahead="$(printf '%s' "$counts" | awk '{print $1}')"
    behind="$(printf '%s' "$counts" | awk '{print $2}')"
    if [ "${behind:-0}" -gt 0 ]; then
      warn "Mana is behind upstream $upstream by $behind commit(s)"
    fi
    if [ "${ahead:-0}" -gt 0 ]; then
      warn "Mana has $ahead local commit(s) ahead of upstream $upstream"
    fi
    if [ "${ahead:-0}" -eq 0 ] && [ "${behind:-0}" -eq 0 ]; then
      info "Mana branch ${branch:-unknown} at ${head_sha:-unknown} matches upstream $upstream"
    fi
  else
    warn "could not compare Mana HEAD with upstream $upstream"
  fi
fi

if [ "$mode" = strict ] && [ "$warnings" -gt 0 ]; then
  exit 1
fi

exit 0
