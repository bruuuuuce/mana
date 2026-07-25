#!/usr/bin/env bash
# Small JSON boundary for Mana shell commands. jq is required because JSON is
# accepted from disk; do not replace this with regular-expression parsing.

mana_json_require() {
  command -v jq >/dev/null 2>&1 || { echo "ERROR: jq is required to read governed JSON (install jq for macOS or Linux)" >&2; return 127; }
}

mana_json_escape() { mana_json_require || return; jq -Rn --arg value "$1" '$value'; }
mana_json_strings() { mana_json_require || return; jq -r "$2[] | strings" "$1"; }
mana_json_value() { mana_json_require || return; jq -er "$2" "$1"; }
mana_json_valid_object() { mana_json_require || return; jq -e 'type == "object"' "$1" >/dev/null; }
mana_json_array() {
  mana_json_require || return
  # stdin: one value per line. Sort and deduplicate before serializing.
  LC_ALL=C sort -u | jq -Rsc 'split("\n") | map(select(length > 0))'
}
