#!/usr/bin/env bash
set -eu
root="$(cd "$(dirname "$0")/.." && pwd)"; tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-rationale.XXXXXX")"; trap 'rm -rf "$tmp"' EXIT
p="$tmp/project"; j="$($root/scripts/mana-journey.sh --project-root "$p" create --title rationale --start-kind symbol --start-value Router --termination-kind code --termination-condition done)"; n="$($root/scripts/mana-journey.sh --project-root "$p" add-node "$j" --kind code --label ProviderRouter)"; a="$($root/scripts/mana-journey.sh --project-root "$p" add-anchor "$j" --node "$n" --revision WORKTREE --path Router.java --start-line 1 --end-line 2)"; $root/scripts/mana-journey.sh --project-root "$p" add-evidence "$j" --kind source_range --anchor "$a" --summary boundary >/dev/null
r="$tmp/request.json"; $root/scripts/mana-rationale.sh --project-root "$p" request --journey "$j" --node "$n" --out "$r" >/dev/null; $root/scripts/mana-rationale.sh --project-root "$p" propose --request "$r" > "$tmp/result.json"; $root/scripts/mana-rationale.sh --project-root "$p" apply --journey "$j" --request "$r" --result "$tmp/result.json" >/dev/null
$root/scripts/mana-journey.sh --project-root "$p" materialize "$j" | jq -e '(.hypotheses|length == 2) and ([.hypotheses[].confidence] | all(. == "plausible")) and ([.hypotheses[].verification_suggestions | length] | all(. > 0))' >/dev/null
echo 'Mana rationale v0 acceptance tests passed'
