#!/usr/bin/env bash
# Host trust root and fail-closed transport tests. Every executable is a stub.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd -P)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/capsule" "$tmp/scratch"
cat > "$tmp/bin/provider" <<'STUB'
#!/bin/bash
printf 'PROVIDER_REACHED_SECRET_CANARY\n'
STUB
cat > "$tmp/bin/sandbox-exec" <<STUB
#!/bin/bash
printf 'CALLER_BACKEND_REACHED\n' > '$tmp/caller-backend'
exit 0
STUB
chmod 700 "$tmp/bin/provider" "$tmp/bin/sandbox-exec"
for fault in mkdir chmod; do
  if bash -c '
    source "$1/scripts/lib/provider-execution.sh"
    if [ "$4" = mkdir ]; then mkdir() { return 1; }; else chmod() { return 1; }; fi
    MANA_CTX07B_ISOLATION_ENABLED=true
    MANA_CTX07B_ISOLATION_SANDBOX=/usr/bin/false
    mana_provider_execute claude "$2" fault-probe packet "$3"
  ' fault "$root" "$tmp/scratch" "$tmp/bin/provider" "$fault" > "$tmp/$fault.out" 2>&1; then
    echo "ERROR: $fault failure executed provider" >&2; exit 1
  fi
  if grep -q PROVIDER_REACHED "$tmp/$fault.out"; then
    echo 'ERROR: provider escaped isolation on metric failure' >&2; exit 1
  fi
done
# Missing OS support is allowed to fail closed; a caller backend must never run.
PATH="$tmp/bin:$PATH" bash -c 'source "$1/scripts/lib/worker-isolation.sh"; mana_worker_isolation_probe' probe "$root" > "$tmp/probe.log" 2>&1 || true
[ ! -e "$tmp/caller-backend" ] || { echo 'ERROR: PATH replaced host backend' >&2; exit 1; }
printf 'UNCHANGED\n' > "$tmp/outside"
ln "$tmp/outside" "$tmp/capsule/hardlink"
if bash -c 'source "$1/scripts/lib/worker-isolation.sh"; mana_worker_isolation_capsule_valid "$2"' test "$root" "$tmp/capsule"; then
  echo 'ERROR: hardlink capsule accepted' >&2; exit 1
fi
rm "$tmp/capsule/hardlink"
ln -s "$tmp/outside" "$tmp/capsule/symlink"
if bash -c 'source "$1/scripts/lib/worker-isolation.sh"; mana_worker_isolation_capsule_valid "$2"' test "$root" "$tmp/capsule"; then
  echo 'ERROR: symlink capsule accepted' >&2; exit 1
fi
[ "$(cat "$tmp/outside")" = UNCHANGED ]
echo 'CTX-07B host boundary regressions passed (zero-token)'
