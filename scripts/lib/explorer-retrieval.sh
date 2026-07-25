#!/usr/bin/env bash
# Deterministic, read-only retrieval controller shared by mana_explorer prompts
# and the local `mana explore` inspection command. It intentionally does not
# create agents or invoke external tools.

explorer_normalize() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]_./-' ' ' | sed 's/^ *//; s/ *$//; s/  */ /g'; }
explorer_json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }
explorer_runtime_emit() {
  # Optional integration: explorer remains independently testable.
  command -v runtime_emit >/dev/null 2>&1 && [ -n "${MANA_RUNTIME_ROOT:-}" ] && runtime_emit "$1" retrieval "$2" "$3" "$4" "$5" false || true
}

# Public API. Arguments: project root, question, optional maximum cycles.
# Results are returned in EXPLORER_* globals. Evidence rows are
# path|reason|provenance and cycle rows are compact, stable descriptions.
explorer_retrieve() {
  local project="$1" question="$2" maximum="${3:-3}" normalized cycle=1 terms term files file reason
  EXPLORER_QUESTION="$question"; EXPLORER_CYCLES=""; EXPLORER_EVIDENCE=""; EXPLORER_REJECTED=""
  EXPLORER_PROBABLY_MODIFY=""; EXPLORER_INSPECT=""; EXPLORER_DO_NOT_TOUCH=""; EXPLORER_GAPS=""; EXPLORER_STATUS="insufficient-evidence"; EXPLORER_NEXT_ACTION="request human clarification"
  normalized="$(explorer_normalize "$question")"
  [ -n "$normalized" ] || { EXPLORER_GAPS="an investigated question is required"; return 2; }
  case "$maximum" in ''|*[!0-9]*) maximum=3;; esac
  [ "$maximum" -gt 0 ] || maximum=3; [ "$maximum" -gt 3 ] && maximum=3
  if [ "${MANA_EXPLORER_TOOL_BLOCKED:-false}" = true ]; then
    EXPLORER_STATUS="blocked"; EXPLORER_GAPS="repository retrieval is blocked by the configured tool boundary"; EXPLORER_CYCLES="1|$question|none|tool boundary|none|blocked|$EXPLORER_GAPS|stop"
    explorer_runtime_emit retrieval.cycle.started cycle-1 started "question=$normalized" ""; explorer_runtime_emit retrieval.stopped tool-boundary blocked "reason=tool-boundary" ""
    return 0
  fi
  if [ "${MANA_EXPLORER_HUMAN_INPUT_REQUIRED:-false}" = true ]; then
    EXPLORER_STATUS="human-input-required"; EXPLORER_GAPS="the question requires owner-provided scope or approval"; EXPLORER_CYCLES="1|$question|none|human input|none|human-input-required|$EXPLORER_GAPS|stop"
    explorer_runtime_emit retrieval.stopped human-input required "reason=human-input-required" ""; return 0
  fi
  terms="$(printf '%s\n' "$normalized" | tr ' ' '\n' | awk 'length($0) >= 4 && $0 !~ /^(with|from|that|this|into|need|should|would|before|after)$/ {print}' | head -n 6)"
  while [ "$cycle" -le "$maximum" ]; do
    explorer_runtime_emit retrieval.cycle.started "cycle-$cycle" started "question=$normalized" ""
    files=""
    while IFS= read -r term; do
      [ -n "$term" ] || continue
      # Filename and content search return only provenance, never full files.
      while IFS= read -r file; do
        case "$EXPLORER_EVIDENCE" in *"$file|"*) EXPLORER_REJECTED="${EXPLORER_REJECTED}${EXPLORER_REJECTED:+$'\n'}$file|already retrieved"; explorer_runtime_emit evidence.rejected "$file" skipped "reason=unchanged" "$file";; *) files="${files}${files:+$'\n'}$file|term $term";; esac
      done < <(rg -l -i --glob '!.git/**' --glob '!.mana/**' -- "$term" "$project" 2>/dev/null | sed "s#^$project/##" | grep -v '^\.mana/' | sort | head -n 8)
    done <<EOF
$terms
EOF
    # The Service Context is authoritative for a second refinement where the
    # question signals contracts, integration, database, or architecture.
    if [ "$cycle" -gt 1 ] && printf '%s' "$normalized" | grep -Eqi 'contract|integration|kafka|api|database|liquibase|architecture'; then
      if [ "$cycle" -eq 2 ]; then context_files='.mana/global/integration-map.md'; else context_files='.mana/global/architecture.md .mana/global/engineering-guards.md'; fi
      for file in $context_files; do
        [ -f "$project/$file" ] || continue
        case "$EXPLORER_EVIDENCE" in *"$file|"*) :;; *) files="${files}${files:+$'\n'}$file|authoritative Service Context refinement";; esac
      done
    fi
    files="$(printf '%s\n' "$files" | sed '/^$/d' | sort -u | head -n 12)"
    if [ -z "$files" ]; then
      if [ -n "$EXPLORER_EVIDENCE" ]; then
        EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|existing evidence|none|none|sufficient|no further refinement needed|stop"
        EXPLORER_STATUS="sufficient"; EXPLORER_NEXT_ACTION="use the source-impact-map classifications for the next governed decision"; explorer_runtime_emit retrieval.stopped "cycle-$cycle" stopped "reason=sufficient" ""; break
      fi
      EXPLORER_GAPS="${EXPLORER_GAPS}${EXPLORER_GAPS:+$'\n'}no new repository-local evidence can refine the question"
      EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|existing evidence|none|none|partial|no meaningful refinement|stop"
      EXPLORER_STATUS="insufficient-evidence"; EXPLORER_NEXT_ACTION="supply a file, symbol, or integration contract"; explorer_runtime_emit retrieval.stopped "cycle-$cycle" stopped "reason=no-refinement" ""; break
    fi
    while IFS='|' read -r file reason; do
      [ -f "$project/$file" ] || continue
      EXPLORER_EVIDENCE="${EXPLORER_EVIDENCE}${EXPLORER_EVIDENCE:+$'\n'}$file|$reason|repository-local"
      explorer_runtime_emit evidence.requested "$file" requested "reason=$(explorer_normalize "$reason")" "$file"
      explorer_runtime_emit evidence.accepted "$file" accepted "reason=$(explorer_normalize "$reason")" "$file"
      case "$file" in .mana/global/*|*generated*|*vendor*|*security*|*shared*) EXPLORER_INSPECT="${EXPLORER_INSPECT}${EXPLORER_INSPECT:+$'\n'}$file";; *test*|*spec*|*contract*|*schema*|*changelog*|*src/*) EXPLORER_PROBABLY_MODIFY="${EXPLORER_PROBABLY_MODIFY}${EXPLORER_PROBABLY_MODIFY:+$'\n'}$file";; *) EXPLORER_INSPECT="${EXPLORER_INSPECT}${EXPLORER_INSPECT:+$'\n'}$file";; esac
    done <<EOF
$files
EOF
    if [ "$cycle" -eq 1 ] && printf '%s' "$normalized" | grep -Eqi 'contract|integration|kafka|api|database|liquibase|architecture' && [ -f "$project/.mana/global/integration-map.md" ]; then
      EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|repository matches|Service Context|$(printf '%s' "$files" | cut -d'|' -f1 | tr '\n' ',')|partial|integration context requested|refine"
      cycle=$((cycle + 1)); continue
    fi
    if [ "$cycle" -eq 2 ] && printf '%s' "$normalized" | grep -Eqi 'contract|integration|kafka|api|database|liquibase|architecture' && { [ -f "$project/.mana/global/architecture.md" ] || [ -f "$project/.mana/global/engineering-guards.md" ]; }; then
      EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|targeted context|architecture and guard context|$(printf '%s' "$files" | cut -d'|' -f1 | tr '\n' ',')|partial|governance context requested|refine"
      cycle=$((cycle + 1)); continue
    fi
    if [ "$cycle" -eq 1 ] && printf '%s' "$normalized" | grep -Eqi 'contract|integration|kafka|api' && [ ! -f "$project/.mana/global/integration-map.md" ]; then
      EXPLORER_GAPS="${EXPLORER_GAPS}${EXPLORER_GAPS:+$'\n'}missing integration contract or .mana/global/integration-map.md"
      EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|repository matches|integration contract|$(printf '%s' "$files" | cut -d'|' -f1 | tr '\n' ',')|partial|missing integration contract|stop"
      EXPLORER_STATUS="partial"; EXPLORER_NEXT_ACTION="request the missing integration contract from the accountable owner"; explorer_runtime_emit evidence.gap integration-map missing "reason=missing-contract" ".mana/global/integration-map.md"; explorer_runtime_emit retrieval.stopped "cycle-$cycle" stopped "reason=missing-contract" ""; break
    fi
    EXPLORER_CYCLES="${EXPLORER_CYCLES}${EXPLORER_CYCLES:+$'\n'}$cycle|$question|repository matches|targeted terms|$(printf '%s' "$files" | cut -d'|' -f1 | tr '\n' ',')|sufficient|none|stop"
    EXPLORER_STATUS="sufficient"; EXPLORER_NEXT_ACTION="use the source-impact-map classifications for the next governed decision"; explorer_runtime_emit retrieval.stopped "cycle-$cycle" stopped "reason=sufficient" ""; break
  done
  EXPLORER_PROBABLY_MODIFY="$(printf '%s\n' "$EXPLORER_PROBABLY_MODIFY" | sed '/^$/d' | sort -u)"
  EXPLORER_INSPECT="$(printf '%s\n' "$EXPLORER_INSPECT" | sed '/^$/d' | sort -u)"
  EXPLORER_DO_NOT_TOUCH="$(printf '%s\n' "$EXPLORER_DO_NOT_TOUCH" | sed '/^$/d' | sort -u)"
  [ -n "$EXPLORER_EVIDENCE" ] || { EXPLORER_STATUS="insufficient-evidence"; EXPLORER_NEXT_ACTION="provide a symbol, file path, or missing integration contract"; }
}
