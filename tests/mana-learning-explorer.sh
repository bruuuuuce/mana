#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
app="$root/apps/mana_learning_explorer"
fail() { echo "FAIL: $*" >&2; exit 1; }
[ -f "$app/pubspec.yaml" ] || fail 'Flutter explorer pubspec is missing'
[ -f "$app/lib/main.dart" ] || fail 'Flutter explorer entrypoint is missing'
grep -q 'watch(recursive: true)' "$app/lib/main.dart" || fail 'Explorer does not watch Journey changes'
grep -q 'mana-journey.sh' "$app/lib/main.dart" || fail 'Explorer does not use authoritative materialization'
grep -q 'requestExpansion' "$app/lib/main.dart" || fail 'Explorer does not expose expansion request action'
(cd "$app" && flutter test)
echo 'Mana Learning Explorer v0 acceptance tests passed'
