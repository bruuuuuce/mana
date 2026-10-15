#!/usr/bin/env bash
# P2: preserve filename bytes/order and fail closed when assembling selections.
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"
. "$root/scripts/lib/verification.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-selection-paths.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
project="$tmp/project"
mkdir -p "$project/scripts"
git -C "$project" init -q
printf '#!/usr/bin/env bash\ntrue\n' > "$project/scripts/check.sh"
git -C "$project" add scripts/check.sh
printf '#!/usr/bin/env bash\necho safe\n' > "$project/scripts/check.sh"
verify="$root/scripts/mana-verify.sh"

# Exercise the actual caller first: the unmodified P2 must fail this regression.
parents=("$tmp/tmp with spaces" "$tmp/tmp quote'\"\\*?[];" "$tmp/"$'tmp\twith\nnewline')
for index in 0 1 2; do
  parent="${parents[$index]}"; mkdir -p "$parent"
  for mode in explicit automatic; do
    args=(--project-root "$project" --dry-run --json)
    if [ "$mode" = explicit ]; then args+=(--skill shell-syntax-verification); count=1; else count=3; fi
    if ! TMPDIR="$parent" "$BASH" "$verify" "${args[@]}" > "$tmp/plan.json" 2> "$tmp/plan.err"; then
      cat "$tmp/plan.err" >&2; fail "plan failed for TMPDIR case $index / $mode"
    fi
    jq -e --argjson count "$count" '.status=="planned" and (.selections|length)==$count and (.actions|length)==1 and .actions[0].adapter=="bash_syntax" and ([.selections[].skillId]==([.selections[].skillId]|sort))' "$tmp/plan.json" >/dev/null || fail 'plan selections/order/actions changed'
    [ ! -e "$project/.mana" ] || fail 'dry-run wrote project state'
    echo "PASS: TMPDIR case $index / $mode plan ($count selection files)"
  done
done

# Zero/one/multiple files, including control characters in directory and basename.
# Filename order is the oracle, deliberately unrelated to the JSON values.
for index in 0 1; do
  if [ "$index" = 0 ]; then directory="$tmp/ordinary"; else directory="$tmp/"$'dir space\t\nquote\'"\\*?[]'; fi
  mkdir -p "$directory"
  value="$(printf 'not JSON; stdin must be ignored' | verification_selection_array "$directory")" || fail 'empty collection failed'
  [ "$value" = '[]' ] || fail 'zero files did not produce exactly one empty array'
  printf '{"ordinal":30}\n' > "$directory/z.json"
  value="$(verification_selection_array "$directory")" || fail 'one file failed'
  jq -e 'map(.ordinal)==[30]' <<< "$value" >/dev/null || fail 'single file changed'
  printf '{"ordinal":20}\n' > "$directory/"$'a space\t\nquote\'"\\*?[].json'
  printf '{"ordinal":10}\n' > "$directory/"$'Z\nfirst.json'
  value="$(verification_selection_array "$directory")" || fail 'multiple files failed'
  jq -e 'map(.ordinal)==[10,20,30]' <<< "$value" >/dev/null || fail 'C filename ordering/filename bytes changed'
  repeated="$(verification_selection_array "$directory")" || fail 'repeat failed'
  [ "$value" = "$repeated" ] || fail 'assembly is not deterministic'
  echo "PASS: directory case $index / zero, one, multiple files; C order; deterministic bytes"
done
before_locale="${LC_ALL-}"; before_options="$(shopt -p nullglob || true)"
verification_selection_array "$directory" > /dev/null
[ "${LC_ALL-}" = "$before_locale" ] && [ "$(shopt -p nullglob || true)" = "$before_options" ] || fail 'helper changed caller locale/glob options'

# Parse and read errors must retain jq's nonzero status; no successful fallback.
errors="$tmp/errors"; mkdir -p "$errors"
printf '{invalid\n' > "$errors/bad.json"
if jq -s '.' "$errors/bad.json" > /dev/null 2> /dev/null; then fail 'malformed fixture is valid'; else expected_status=$?; fi
if verification_selection_array "$errors" > "$tmp/error.out" 2> "$tmp/error.err"; then fail 'malformed JSON was accepted'; else status=$?; fi
[ "$status" = "$expected_status" ] && [ -s "$tmp/error.err" ] || fail 'parse error status was masked'
rm "$errors/bad.json"
ln -s "$errors/absent" "$errors/unreadable.json"
if verification_selection_array "$errors" > "$tmp/error.out" 2> "$tmp/error.err"; then fail 'unreadable input was accepted'; else status=$?; fi
[ "$status" = 2 ] && [ -s "$tmp/error.err" ] || fail 'read error status was masked'
if verification_selection_array "$tmp/missing-directory" > "$tmp/error.out"; then fail 'missing directory was accepted'; fi
echo 'PASS: parse/read/missing-directory errors remain nonzero; caller options unchanged'

# Simulate jq emitting valid output before a failure. The CLI must publish no
# plan/result or workspace and must retain its operational-error exit code 2.
real_jq="$(command -v jq)"; mkdir -p "$tmp/bin"
cat > "$tmp/bin/jq" <<'SHIM'
#!/usr/bin/env bash
if [ "$#" -ge 3 ] && [ "$1" = -s ] && [ "$2" = . ]; then
  case "$3" in */selection/*.json) printf '[{"partial":true}]\n'; echo 'injected selection read failure' >&2; exit 7;; esac
fi
exec "$SELECTION_TEST_REAL_JQ" "$@"
SHIM
chmod +x "$tmp/bin/jq"
if SELECTION_TEST_REAL_JQ="$real_jq" PATH="$tmp/bin:$PATH" TMPDIR="${parents[0]}" "$BASH" "$verify" --project-root "$project" --skill shell-syntax-verification --dry-run --json > "$tmp/failure.out" 2> "$tmp/failure.err"; then fail 'partial output was published as success'; else status=$?; fi
[ "$status" = 2 ] && [ ! -s "$tmp/failure.out" ] && [ ! -e "$project/.mana" ] || fail 'caller did not stop before publication'
grep -Fq 'ERROR: could not assemble verification selections' "$tmp/failure.err" || fail 'assembly error diagnostic missing'
echo 'PASS: jq output-then-error yields CLI exit 2, no JSON publication or project writes'

# Execute the real verifier through the repaired spaced-TMPDIR path. Successful
# checks remain exit 0; a syntax failure remains exit 1 with canonical evidence.
# Execution uses the environment Bash: baseline runtime-events needs Bash 4+.
TMPDIR="${parents[0]}" bash "$verify" --project-root "$project" --skill shell-syntax-verification --json > "$tmp/passed.json"
jq -e '.overallResult=="passed" and (.selections|length)==1 and (.checks|length)==1 and .checks[0].exitCode==0' "$tmp/passed.json" >/dev/null || fail 'successful execution semantics changed'
printf '#!/usr/bin/env bash\nif then\n' > "$project/scripts/check.sh"
if TMPDIR="${parents[0]}" bash "$verify" --project-root "$project" --skill shell-syntax-verification --json > "$tmp/failed.json"; then fail 'invalid syntax passed'; else status=$?; fi
[ "$status" = 1 ] || fail 'check failure exit code changed'
jq -e '.overallResult=="failed" and .checks[0].result=="failed" and .checks[0].exitCode!=0' "$tmp/failed.json" >/dev/null || fail 'check failure evidence changed'
echo 'PASS: spaced-TMPDIR execution retains exit 0 / exit 1 and canonical result semantics'
echo 'Verification selection path regressions passed'
