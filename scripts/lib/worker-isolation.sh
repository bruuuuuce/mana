#!/usr/bin/env bash
# CTX-07B-R1B host-owned read-isolation for a single private worker capsule.
# This is intentionally not a provider flag: the policy is created and owned
# by the host and defaults to deny.  Read-only provider sandboxes are not used
# as a substitute because they may still read the project filesystem.

mana_worker_isolation_quote() {
  # sandbox(7) strings use backslash and quote escaping.
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

mana_worker_isolation_probe() {
  local sandbox capsule outside policy denied
  # The OS backend is a trust root, never a caller PATH lookup.
  sandbox=/usr/bin/sandbox-exec
  [ -x "$sandbox" ] && [ ! -L "$sandbox" ] || return 1
  capsule="$(mktemp -d "${TMPDIR:-/tmp}/mana-worker-isolation-probe.XXXXXX")" || return 1
  outside="$(mktemp -d "${TMPDIR:-/tmp}/mana-worker-isolation-outside.XXXXXX")" || { rm -rf "$capsule"; return 1; }
  capsule="$(cd "$capsule" && pwd -P)"
  outside="$(cd "$outside" && pwd -P)"
  policy="$capsule/policy.sb"
  printf 'capsule\n' > "$capsule/allowed"
  for denied in project-secret run-head evidence-store sibling-evidence unauthorized-evidence absolute-outside; do
    printf 'secret\n' > "$outside/$denied"
  done
  ln -s "$outside/absolute-outside" "$capsule/symlink-outside" || { rm -rf "$capsule" "$outside"; return 1; }
  cat > "$policy" <<EOF
(version 1)
(deny default)
(allow process*)
(allow sysctl-read)
(allow file-read* (literal "/"))
(allow file-read* (subpath "/bin") (subpath "/System") (subpath "/usr/lib") (subpath $(mana_worker_isolation_quote "$capsule")))
(allow file-read* file-write* (literal "/dev/null"))
EOF
  # shellcheck disable=SC2016 # positional arguments expand in the sandboxed shell
  (cd "$capsule" && "$sandbox" -f "$policy" /bin/bash -c '
    test "$(/bin/cat "$1/allowed")" = capsule || exit 10
    for candidate in "$2/project-secret" "$2/run-head" "$2/evidence-store" \
      "$2/sibling-evidence" "$2/unauthorized-evidence" "$2/absolute-outside" \
      "$1/../$3/absolute-outside" "$1/symlink-outside"; do
      /bin/cat "$candidate" >/dev/null 2>&1 && exit 11
    done
    exit 0
  ' probe "$capsule" "$outside" "$(basename "$outside")")
  local status=$?
  rm -rf "$capsule"
  rm -rf "$outside"
  return "$status"
}

mana_worker_isolation_link_count() {
  local path="$1"
  case "$(uname -s)" in
    Darwin)
      stat -f '%l' "$path"
      ;;
    Linux)
      stat -c '%h' "$path"
      ;;
    *)
      return 1
      ;;
  esac
}

mana_worker_isolation_capsule_valid() {
  local capsule="$1"
  [ -d "$capsule" ] && [ ! -L "$capsule" ] || return 1
  # find's link count catches a hardlink even when it is not a symbolic link.
  local item links
  while IFS= read -r -d '' item; do
    [ ! -L "$item" ] || return 1
    [ -f "$item" ] || continue
    links="$(mana_worker_isolation_link_count "$item")" || return 1
    [ "$links" = 1 ] || return 1
  done < <(find "$capsule" -xdev -print0)
}

mana_worker_isolation_prepare() {
  # $1 capsule; $2 private writable output/temp directory; $3 provider binary
  local capsule="$1" writable="$2" provider_program="$3" sandbox session_launcher
  mana_worker_isolation_probe || return 1
  mana_worker_isolation_capsule_valid "$capsule" || return 1
  [ -d "$writable" ] && [ ! -L "$writable" ] || return 1
  [ -x "$provider_program" ] && [ ! -L "$provider_program" ] || return 1
  session_launcher="${MANA_PROVIDER_SESSION_LAUNCHER:-}"
  [ -x "$session_launcher" ] && [ ! -L "$session_launcher" ] || return 1
  sandbox=/usr/bin/sandbox-exec
  MANA_CTX07B_ISOLATION_POLICY="$writable/host-worker-policy.sb"
  cat > "$MANA_CTX07B_ISOLATION_POLICY" <<EOF
(version 1)
(deny default)
(allow process*)
(allow sysctl-read)
(allow file-read* (literal "/"))
(allow file-read* (subpath "/bin") (subpath "/System") (subpath "/usr/lib")
  (subpath $(mana_worker_isolation_quote "$capsule"))
  (literal $(mana_worker_isolation_quote "$provider_program"))
  (literal $(mana_worker_isolation_quote "$session_launcher")))
(allow file-write* (subpath $(mana_worker_isolation_quote "$writable")))
(allow file-read* file-write* (literal "/dev/null"))
EOF
  chmod 600 "$MANA_CTX07B_ISOLATION_POLICY" || return 1
  export MANA_CTX07B_ISOLATION_POLICY MANA_CTX07B_ISOLATION_SANDBOX="$sandbox"
}

mana_worker_isolation_prepare_test_only() {
  # Called solely by tests/run-context-workers-test-only.sh.  It exercises the
  # production capsule/argv/supervision flow without claiming OS containment.
  local capsule="$1" writable="$2" launcher="$3"
  mana_worker_isolation_capsule_valid "$capsule" || return 1
  [ -d "$writable" ] && [ ! -L "$writable" ] || return 1
  [ -x "$launcher" ] && [ ! -L "$launcher" ] || return 1
  MANA_CTX07B_ISOLATION_POLICY="$writable/test-only-policy"
  : > "$MANA_CTX07B_ISOLATION_POLICY"
  chmod 600 "$MANA_CTX07B_ISOLATION_POLICY" || return 1
  MANA_CTX07B_ISOLATION_SANDBOX="$launcher"
  export MANA_CTX07B_ISOLATION_POLICY MANA_CTX07B_ISOLATION_SANDBOX
}

mana_worker_isolation_launch() {
  [ -n "${MANA_CTX07B_ISOLATION_POLICY:-}" ] || return 126
  [ -n "${MANA_CTX07B_ISOLATION_SANDBOX:-}" ] || return 126
  "$MANA_CTX07B_ISOLATION_SANDBOX" -f "$MANA_CTX07B_ISOLATION_POLICY" -- "$@"
}
