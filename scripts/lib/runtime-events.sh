#!/usr/bin/env bash
# Repository-local, privacy-preserving runtime event publisher.  Callers pass
# only operational metadata; this module deliberately has no prompt or tool
# payload API.

MANA_RUNTIME_SCHEMA_VERSION="1"
MANA_RUNTIME_ROOT=""
MANA_RUNTIME_SESSION_ID=""
MANA_RUNTIME_EXECUTION_ID=""
MANA_RUNTIME_PROFILE_ID=""
MANA_RUNTIME_SEQUENCE=0
MANA_RUNTIME_WARNING=""
MANA_RUNTIME_STARTED_AT=""

runtime_json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r/\\r/g; s/\n/\\n/g'; }

runtime_init() {
  # $1 project root, $2 profile id. The caller chooses when an execution has
  # crossed the execution boundary; dry runs must never call this function.
  local project_root="$1" profile_id="$2" stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  MANA_RUNTIME_ROOT="$project_root/.mana/runtime"
  MANA_RUNTIME_PROFILE_ID="$profile_id"
  MANA_RUNTIME_SESSION_ID="session-${stamp}-$$"
  MANA_RUNTIME_EXECUTION_ID="execution-${stamp}-$$"
  MANA_RUNTIME_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  MANA_RUNTIME_SEQUENCE=0
  if ! mkdir -p "$MANA_RUNTIME_ROOT/sessions" "$MANA_RUNTIME_ROOT/events" "$MANA_RUNTIME_ROOT/snapshots" "$MANA_RUNTIME_ROOT/metrics"; then
    MANA_RUNTIME_WARNING="runtime event storage unavailable: $MANA_RUNTIME_ROOT"
    return 1
  fi
  printf '{"schemaVersion":"%s","sessionId":"%s","executionId":"%s","profileId":"%s","startedAt":"%s","status":"running"}\n' \
    "$MANA_RUNTIME_SCHEMA_VERSION" "$(runtime_json_escape "$MANA_RUNTIME_SESSION_ID")" "$(runtime_json_escape "$MANA_RUNTIME_EXECUTION_ID")" "$(runtime_json_escape "$profile_id")" "$MANA_RUNTIME_STARTED_AT" \
    > "$MANA_RUNTIME_ROOT/sessions/$MANA_RUNTIME_SESSION_ID.json" || { MANA_RUNTIME_WARNING="runtime session snapshot could not be written"; return 1; }
}

runtime_redacted() {
  # Never serialize secrets even if a future caller accidentally supplies one.
  case "${1,,}" in *token*|*secret*|*password*|*credential*|*authorization*|*bearer*) printf '[REDACTED]' ;; *) printf '%s' "$1" ;; esac
}

runtime_attributes_json() {
  # Attributes are a deliberately narrow k=v list, not arbitrary JSON.
  local attrs="${1:-}" item key value safe_key safe_value first=true
  printf '{'
  for item in $attrs; do
    key="${item%%=*}"; value="${item#*=}"
    [ "$key" != "$item" ] || continue
    safe_key="$(runtime_redacted "$key")"
    safe_value="$(runtime_redacted "$value")"
    if [ "$safe_key" = '[REDACTED]' ] || [ "$safe_value" = '[REDACTED]' ]; then value='[REDACTED]'; fi
    "$first" || printf ','; first=false
    printf '"%s":"%s"' "$(runtime_json_escape "$key")" "$(runtime_json_escape "$value")"
  done
  printf '}'
}

runtime_evidence_json() {
  local references="${1:-}" value first=true
  printf '['
  for value in $references; do
    "$first" || printf ','; first=false
    printf '"%s"' "$(runtime_json_escape "$value")"
  done
  printf ']'
}

runtime_emit() {
  # $1 type $2 component type $3 component id $4 status $5 attributes $6 evidence refs $7 critical(true|false)
  local event_type="$1" component_type="$2" component_id="$3" status="$4" attrs="${5:-}" refs="${6:-}" critical="${7:-false}"
  local lock="$MANA_RUNTIME_ROOT/events/.${MANA_RUNTIME_EXECUTION_ID}.lock" sequence_file="$MANA_RUNTIME_ROOT/events/.${MANA_RUNTIME_EXECUTION_ID}.sequence" attempts=0 event_id line stored_sequence
  if [ -z "$MANA_RUNTIME_ROOT" ] || [ ! -d "$MANA_RUNTIME_ROOT/events" ]; then MANA_RUNTIME_WARNING="runtime event storage is not initialized"; [ "$critical" = true ] && return 1 || return 0; fi
  while ! mkdir "$lock" 2>/dev/null; do
    attempts=$((attempts + 1)); [ "$attempts" -lt 80 ] || { MANA_RUNTIME_WARNING="runtime event lock unavailable"; [ "$critical" = true ] && return 1 || return 0; }
    sleep 0.025
  done
  stored_sequence="$(sed -n '1p' "$sequence_file" 2>/dev/null || true)"
  case "$stored_sequence" in *[!0-9]*|'') stored_sequence=0;; esac
  MANA_RUNTIME_SEQUENCE=$((stored_sequence + 1))
  printf '%s\n' "$MANA_RUNTIME_SEQUENCE" > "$sequence_file" || { rmdir "$lock" 2>/dev/null || true; MANA_RUNTIME_WARNING="runtime event sequence write failed"; [ "$critical" = true ] && return 1 || return 0; }
  event_id="${MANA_RUNTIME_EXECUTION_ID}-$(printf '%06d' "$MANA_RUNTIME_SEQUENCE")"
  line="{\"eventId\":\"$event_id\",\"schemaVersion\":\"$MANA_RUNTIME_SCHEMA_VERSION\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"sessionId\":\"$MANA_RUNTIME_SESSION_ID\",\"executionId\":\"$MANA_RUNTIME_EXECUTION_ID\",\"profileId\":\"$(runtime_json_escape "$MANA_RUNTIME_PROFILE_ID")\",\"eventType\":\"$(runtime_json_escape "$event_type")\",\"componentType\":\"$(runtime_json_escape "$component_type")\",\"componentId\":\"$(runtime_json_escape "$component_id")\",\"status\":\"$(runtime_json_escape "$status")\",\"attributes\":$(runtime_attributes_json "$attrs"),\"evidenceReferences\":$(runtime_evidence_json "$refs")}"
  if ! printf '%s\n' "$line" >> "$MANA_RUNTIME_ROOT/events/$MANA_RUNTIME_EXECUTION_ID.jsonl"; then
    rmdir "$lock" 2>/dev/null || true; MANA_RUNTIME_WARNING="runtime event write failed"; [ "$critical" = true ] && return 1 || return 0
  fi
  rmdir "$lock" 2>/dev/null || true
}

runtime_finish() {
  # $1 completed|failed. Snapshot rewrite is atomic enough for local readers.
  local status="$1" tmp="$MANA_RUNTIME_ROOT/sessions/.${MANA_RUNTIME_SESSION_ID}.tmp"
  [ -n "$MANA_RUNTIME_ROOT" ] || return 0
  printf '{"schemaVersion":"%s","sessionId":"%s","executionId":"%s","profileId":"%s","startedAt":"%s","finishedAt":"%s","status":"%s"}\n' \
    "$MANA_RUNTIME_SCHEMA_VERSION" "$MANA_RUNTIME_SESSION_ID" "$MANA_RUNTIME_EXECUTION_ID" "$(runtime_json_escape "$MANA_RUNTIME_PROFILE_ID")" "$MANA_RUNTIME_STARTED_AT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$status" > "$tmp" && mv "$tmp" "$MANA_RUNTIME_ROOT/sessions/$MANA_RUNTIME_SESSION_ID.json" || MANA_RUNTIME_WARNING="runtime session snapshot update failed"
}
