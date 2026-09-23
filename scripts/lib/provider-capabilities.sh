#!/usr/bin/env bash
# Provider-neutral CTX-02 capability probing. Reports contain only version,
# safe evidence identifiers, and tri-state capability metadata.

mana_provider_capabilities_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

mana_provider_capabilities_error() {
  printf 'ERROR: %s\n' "$*" >&2
}

# Resolve provider evidence only after the adapter has collected both sides.
# The internal map deliberately retains provenance until this boundary:
# {
#   capability: {
#     positiveEvidence: [safe evidence IDs],
#     negativeEvidence: [safe evidence IDs],
#     ambiguousEvidence: [safe evidence IDs],
#     unknownEvidence: [safe evidence IDs]
#   }
# }
# Raw help/config output is never included. The public v1 contract is then
# derived with the authoritative conservative truth table:
#   0/0 unknown, 1/0 supported, 0/1 unsupported, 1/1 unknown.
mana_provider_capabilities_resolve_evidence_map() {
  jq -c '
    def hasPositive: ((.positiveEvidence // []) | length) > 0;
    def hasNegative: ((.negativeEvidence // []) | length) > 0;
    def hasAmbiguous: ((.ambiguousEvidence // []) | length) > 0;
    def resolvedState:
      if hasAmbiguous then "unknown"
      elif hasPositive and hasNegative then "unknown"
      elif hasPositive then "supported"
      elif hasNegative then "unsupported"
      else "unknown"
      end;
    def resolvedEvidence:
      if hasAmbiguous then
        ((.positiveEvidence // []) + (.negativeEvidence // []) + (.ambiguousEvidence // []))
      elif hasPositive and hasNegative then
        ((.positiveEvidence // []) + (.negativeEvidence // []))
      elif hasPositive then (.positiveEvidence // [])
      elif hasNegative then (.negativeEvidence // [])
      else (.unknownEvidence // ["probe:no-authoritative-evidence"])
      end;
    with_entries(
      .value = {
        status: (.value | resolvedState),
        evidence: (.value | resolvedEvidence)
      }
    )
  '
}

# Resolve an all-required composite from already-resolved prerequisite states.
# This boundary intentionally accepts only the public tri-state vocabulary. It
# cannot inspect or reinterpret positive/negative/ambiguous evidence from an
# atomic prerequisite.
mana_provider_capabilities_resolve_required_states() {
  [ "$#" -gt 0 ] || return 2
  local state saw_unknown=false saw_unsupported=false
  for state in "$@"; do
    case "$state" in
      supported) ;;
      unknown) saw_unknown=true ;;
      unsupported) saw_unsupported=true ;;
      *) return 2 ;;
    esac
  done
  if [ "$saw_unsupported" = true ]; then
    printf 'unsupported\n'
  elif [ "$saw_unknown" = true ]; then
    printf 'unknown\n'
  else
    printf 'supported\n'
  fi
}

# Combine a prerequisite-derived composite state with optional direct evidence
# about the composite itself. The optional direct input must already have been
# atomically resolved. Absence is distinct from an observed-but-unknown direct
# result. Direct authoritative negative evidence may prove an otherwise unknown
# composite unsupported, but it conflicts with derived support and therefore
# resolves to unknown.
mana_provider_capabilities_combine_composite_states() {
  [ "$#" -eq 1 ] || [ "$#" -eq 2 ] || return 2
  local derived="$1" direct="${2:-}"
  case "$derived" in supported|unsupported|unknown) ;; *) return 2 ;; esac
  if [ "$#" -eq 1 ]; then
    printf '%s\n' "$derived"
    return 0
  fi
  case "$direct" in supported|unsupported|unknown) ;; *) return 2 ;; esac
  case "$derived:$direct" in
    supported:supported) printf 'supported\n' ;;
    unknown:unsupported) printf 'unsupported\n' ;;
    unsupported:unsupported) printf 'unsupported\n' ;;
    *) printf 'unknown\n' ;;
  esac
}

# Render one public composite capability record. Prerequisite evidence is
# represented only by its resolved derived state and one bounded safe ID;
# optional direct composite evidence is represented the same way. Raw atomic
# evidence maps are deliberately not accepted by this API.
mana_provider_capabilities_composite_record() {
  [ "$#" -eq 2 ] || [ "$#" -eq 4 ] || return 2
  local derived="$1" derived_evidence="$2" direct="${3:-}" direct_evidence="${4:-}" status
  case "$derived_evidence" in ''|*[!a-z0-9._:-]*) return 2 ;; esac
  if [ "$#" -eq 4 ]; then
    case "$direct_evidence" in ''|*[!a-z0-9._:-]*) return 2 ;; esac
    status="$(mana_provider_capabilities_combine_composite_states "$derived" "$direct")" || return $?
    jq -cn --arg status "$status" --arg derived "$derived_evidence" --arg direct "$direct_evidence" \
      '{status:$status,evidence:([$derived,$direct] | unique)}'
  else
    status="$(mana_provider_capabilities_combine_composite_states "$derived")" || return $?
    jq -cn --arg status "$status" --arg evidence "$derived_evidence" \
      '{status:$status,evidence:[$evidence]}'
  fi
}

mana_provider_capabilities_adapter_path() {
  local root provider
  root="$(mana_provider_capabilities_root)"
  provider="$1"
  printf '%s/scripts/lib/providers/%s.sh\n' "$root" "$provider"
}

mana_provider_capabilities_load_adapter() {
  local provider="$1" adapter
  case "$provider" in codex|claude|opencode) ;; *)
    mana_provider_capabilities_error "provider adapter does not exist: $provider"
    return 2
  esac
  adapter="$(mana_provider_capabilities_adapter_path "$provider")"
  [ -r "$adapter" ] || {
    mana_provider_capabilities_error "provider adapter is unavailable: $adapter"
    return 2
  }
  # shellcheck disable=SC1090
  . "$adapter"
}

mana_provider_capabilities_validate_fixture_files() {
  local fixture="$1"
  shift
  [ -d "$fixture" ] || {
    mana_provider_capabilities_error "capability fixture directory is missing: $fixture"
    return 2
  }
  local name
  for name in "$@"; do
    [ -f "$fixture/$name" ] || {
      mana_provider_capabilities_error "capability fixture is malformed: missing $name"
      return 2
    }
  done
}

mana_provider_capabilities_extract_version() {
  local provider="$1" version_file="$2" first_line version
  first_line="$(sed -n '1p' "$version_file" | tr -d '\r')"
  case "$provider" in
    codex)
      version="$(printf '%s\n' "$first_line" | sed -nE 's/^codex-cli ([0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9._-]+)?)$/\1/p')"
      ;;
    claude)
      version="$(printf '%s\n' "$first_line" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9._-]+)?) \(Claude Code\)$/\1/p')"
      ;;
    opencode)
      version="$(printf '%s\n' "$first_line" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9._-]+)?)$/\1/p')"
      ;;
  esac
  [ -n "$version" ] || {
    mana_provider_capabilities_error "unexpected $provider --version output"
    return 6
  }
  printf '%s\n' "$version"
}

mana_provider_capabilities_report() {
  local provider="$1" source="${2:-live}" location="${3:-}" adapter probe_dir cleanup=false binary version capabilities evidence
  mana_provider_capabilities_load_adapter "$provider" || return $?

  if [ "$source" = fixture ]; then
    probe_dir="$location"
    "mana_provider_capabilities_validate_${provider}_fixture" "$probe_dir" || return $?
  elif [ "$source" = live ]; then
    binary="${location:-$provider}"
    if [[ "$binary" == */* ]]; then
      [ -x "$binary" ] || {
        mana_provider_capabilities_error "provider binary is missing or not executable: $binary"
        return 3
      }
    else
      command -v "$binary" >/dev/null 2>&1 || {
        mana_provider_capabilities_error "provider binary is missing from PATH: $binary"
        return 3
      }
    fi
    probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/mana-provider-capabilities.XXXXXX")" || return 1
    cleanup=true
    if "mana_provider_capabilities_probe_${provider}" "$binary" "$probe_dir"; then
      :
    else
      local probe_status=$?
      [ "$cleanup" = false ] || rm -rf "$probe_dir"
      return "$probe_status"
    fi
  else
    mana_provider_capabilities_error "unknown probe source: $source"
    return 2
  fi

  version="$(mana_provider_capabilities_extract_version "$provider" "$probe_dir/version.txt")" || {
    local version_status=$?
    [ "$cleanup" = false ] || rm -rf "$probe_dir"
    return "$version_status"
  }
  capabilities="$("mana_provider_capabilities_render_${provider}" "$probe_dir")" || {
    local render_status=$?
    [ "$cleanup" = false ] || rm -rf "$probe_dir"
    return "$render_status"
  }
  evidence="$("mana_provider_capabilities_evidence_${provider}" "$probe_dir")" || {
    local evidence_status=$?
    [ "$cleanup" = false ] || rm -rf "$probe_dir"
    return "$evidence_status"
  }
  jq -n \
    --arg schemaVersion 'mana.context-runtime.provider-capabilities/v1' \
    --arg provider "$provider" \
    --arg providerVersion "$version" \
    --arg probeSource "$source" \
    --argjson probeEvidence "$evidence" \
    --argjson capabilities "$capabilities" \
    '{schemaVersion:$schemaVersion,provider:$provider,providerVersion:$providerVersion,
      probeSource:$probeSource,probeEvidence:$probeEvidence,capabilities:$capabilities}'
  local report_status=$?
  [ "$cleanup" = false ] || rm -rf "$probe_dir"
  return "$report_status"
}
