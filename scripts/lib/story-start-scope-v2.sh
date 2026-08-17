#!/usr/bin/env bash
# Internal, non-default Story Start Scope v2 phase support. SS02 adds only
# discovery; public Story Start integration remains reserved for SS06.

mana_story_start_scope_v2_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

mana_story_start_scope_v2_discovery_prompt() {
  local package="$1"
  cat <<'CONTRACT'
You are Mana Story Start Discovery v2. Return exactly one JSON object matching
the supplied discovery-inventory v2 schema and use only the compact evidence
package below. Discover and report evidence; distinguish observed facts from
inferences; preserve bounded provenance; relate evidence to acceptance criteria
only where the evidence supports it; record pre-existing status, ambiguities,
open questions, decisions, and a suggested owner when evidence supports one.

This is discovery, not planning. Do not decide implementation scope. Do not produce implementation tasks. Do not estimate remediation work. Do not choose between unresolved architectures. Do not assume a discovered defect belongs to the current story. Do not turn missing evidence into a fabricated requirement.
Do not inspect a repository, ticket system, network, or any data outside this
package. A missing fact is evidence_gap evidence, never a requirement.

Use findings only for neutral facts, constraints, defects, suspected defects,
risks, readiness, ambiguities, or optional opportunities. Use openQuestions
when an answer is unknown without complete decision alternatives. Use decisions
only when alternatives and an owner are evidenced. Keep an open decision's
selectedOptionId null. Do not include tasks, estimates, classifications, or a
final total: the discovery schema rejects them.

COMPACT_DISCOVERY_PACKAGE
CONTRACT
  jq -cS . "$package"
}

mana_story_start_scope_v2_validate_discovery() {
  local artifact="$1" root
  root="$(mana_story_start_scope_v2_root)"
  python3 "$root/tests/lib/json_schema_subset.py" \
    "$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json" \
    "$artifact"
}

# Arguments: provider model compact-package.json normalized-output.json.
# The caller owns evidence collection. This phase gives the provider only a
# compact package, so later phases need not receive a repository.
mana_story_start_scope_v2_discover() {
  local provider="$1" model="$2" package="$3" output="$4"
  local root schema normalizer scratch prompt program output_file status_file stage timeout code signal timed_out descendants
  root="$(mana_story_start_scope_v2_root)"
  schema="$root/contracts/story-start/scope-v2/schemas/discovery-inventory.schema.json"
  normalizer="$root/scripts/lib/story-start-scope-v2-normalize.py"
  [ -f "$package" ] || { echo "ERROR: missing Discovery v2 package: $package" >&2; return 2; }
  [ -f "$schema" ] && [ -f "$normalizer" ] || { echo 'ERROR: Story Start Scope v2 contract is unavailable' >&2; return 2; }
  jq -e 'type == "object"' "$package" >/dev/null || { echo 'ERROR: Discovery v2 package must be a JSON object' >&2; return 2; }
  [ "$(wc -c < "$package" | tr -d ' ')" -le 262144 ] || { echo 'ERROR: Discovery v2 package exceeds 262144 bytes' >&2; return 2; }
  timeout="${MANA_STORY_START_SCOPE_V2_DISCOVERY_TIMEOUT_SECONDS:-120}"
  [[ "$timeout" =~ ^[1-9][0-9]*$ ]] && [ "$timeout" -le 300 ] || { echo 'ERROR: Discovery v2 timeout must be 1..300 seconds' >&2; return 2; }
  scratch="$(mktemp -d "${TMPDIR:-/tmp}/mana-story-start-discovery-v2.XXXXXX")" || return 2
  mkdir -p "$scratch/empty"
  prompt="$(mana_story_start_scope_v2_discovery_prompt "$package")" || { rm -rf "$scratch"; return 2; }
  MANA_PROVIDER_PROGRAM="$provider"
  mana_provider_synthesis_args "$provider" "$scratch/empty" "$model" host-disposable-non-git "$schema" || { rm -rf "$scratch"; echo 'ERROR: Discovery v2 provider arguments could not be constructed' >&2; return 2; }
  program="${MANA_PROVIDER_PROGRAM:-$provider}"
  command -v "$program" >/dev/null 2>&1 || { rm -rf "$scratch"; echo "ERROR: Discovery v2 provider is unavailable: $program" >&2; return 2; }
  output_file="$scratch/provider-output.json"
  status_file="$scratch/status.tsv"
  perl "$root/scripts/lib/verification-exec.pl" --timeout "$timeout" --output-cap 262144 --stderr-cap 4096 --stdout "$output_file" --stderr "$scratch/provider.stderr" --status "$status_file" -- "$program" "${MANA_PROVIDER_ARGS[@]}" "$prompt" || true
  if [ ! -f "$status_file" ] || ! IFS=$'\t' read -r code signal timed_out descendants _ < "$status_file" || [ "$code" -ne 0 ] || [ "$timed_out" != 0 ] || [ "$descendants" != 0 ]; then
    rm -rf "$scratch"
    echo 'ERROR: Discovery v2 provider execution failed' >&2
    return 1
  fi
  mana_story_start_scope_v2_validate_discovery "$output_file" || { rm -rf "$scratch"; echo 'ERROR: Discovery v2 provider output failed schema validation' >&2; return 1; }
  mkdir -p "$(dirname "$output")"
  [ ! -L "$output" ] || { rm -rf "$scratch"; echo "ERROR: unsafe Discovery v2 output symlink: $output" >&2; return 2; }
  stage="$(mktemp "$(dirname "$output")/.${output##*/}.tmp.XXXXXX")" || { rm -rf "$scratch"; return 2; }
  if ! python3 "$normalizer" normalize-discovery "$schema" "$output_file" "$stage"; then rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: Discovery v2 normalization failed' >&2; return 1; fi
  mana_story_start_scope_v2_validate_discovery "$stage" || { rm -f "$stage"; rm -rf "$scratch"; echo 'ERROR: normalized Discovery v2 artifact failed schema validation' >&2; return 1; }
  mv "$stage" "$output"
  rm -rf "$scratch"
}
