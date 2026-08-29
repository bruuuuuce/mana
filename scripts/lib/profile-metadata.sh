#!/usr/bin/env bash
# Shared, read-only accessors for the simple profile YAML structure.

mana_profile_skills() {
  awk '
    /^skills:/ { active=1; next }
    active && /^- / { sub(/^- /, ""); print; next }
    active && /^  - / { sub(/^  - /, ""); print; next }
    active && /^[^[:space:]-]/ { active=0 }
  ' "$1"
}

# Report only lexical presence here. Full shape validation belongs to the
# authoritative Python compiler; importantly, a malformed present key is never
# reported as absent and therefore cannot enter legacy fallback.
mana_profile_skill_activation_state() {
  awk '
    /^[[:space:]]*skill_activation[[:space:]]*:/ {
      count++
      if ($0 == "skill_activation:") valid++
    }
    END {
      if (count == 0) print "absent"
      else if (count == 1 && valid == 1) print "present"
      else print "malformed"
    }
  ' "$1"
}

mana_profile_has_skill_activation() {
  [ "$(mana_profile_skill_activation_state "$1")" != absent ]
}

# Baseline skills are active before host/classifier signals are evaluated.
mana_profile_baseline_skills() {
  awk '
    /^skill_activation:[[:space:]]*$/ { in_activation=1; next }
    in_activation && /^[^[:space:]]/ { exit }
    in_activation && /^  baseline:[[:space:]]*$/ { in_baseline=1; next }
    in_baseline && /^  [a-z_][A-Za-z0-9_-]*:[[:space:]]*$/ { exit }
    in_baseline && /^[[:space:]]*-[[:space:]]+/ {
      line=$0
      sub(/^[[:space:]]*-[[:space:]]+/, "", line)
      print line
    }
  ' "$1"
}

# Emit the conditional activation graph as signal|skill records. The compact
# record is intended for host-side compilation; it never contains skill bodies.
mana_profile_conditional_activations() {
  awk '
    /^skill_activation:[[:space:]]*$/ { in_activation=1; next }
    in_activation && /^[^[:space:]]/ { exit }
    in_activation && /^  conditional:[[:space:]]*$/ { in_conditional=1; next }
    in_conditional && /^  [a-z_][A-Za-z0-9_-]*:[[:space:]]*$/ { exit }
    in_conditional && /^    [A-Za-z0-9_-]+:[[:space:]]*[A-Za-z0-9_-]+[[:space:]]*$/ {
      line=$0
      sub(/^[[:space:]]*/, "", line)
      signal=line
      sub(/:.*/, "", signal)
      skill=line
      sub(/^[^:]*:[[:space:]]*/, "", skill)
      print signal "|" skill
    }
  ' "$1"
}

mana_profile_skill_for_signal() {
  mana_profile_conditional_activations "$1" | awk -F'|' -v signal="$2" '$1 == signal { print $2; exit }'
}

mana_profile_signals_for_skill() {
  mana_profile_conditional_activations "$1" | awk -F'|' -v skill="$2" '$2 == skill { print $1 }'
}

# Initial activation is baseline-only for declarative profiles. The legacy
# fallback preserves the historical all-candidates behavior and is surfaced as
# a warning by callers instead of silently changing old profile semantics.
mana_profile_initial_active_skills() {
  if mana_profile_has_skill_activation "$1"; then
    mana_profile_baseline_skills "$1"
  else
    mana_profile_skills "$1"
  fi
}

# Read one lightweight generated-index record without exposing the complete
# skill catalog to a model prompt.
mana_skill_index_metadata() {
  awk -v target="$2" '
    $1 == "-" && $2 == "id:" {
      if (found) { print path "|" risk "|" tier "|" mode "|" group; active=0; exit }
      active=($3 == target); found=active; next
    }
    active && $1 == "path:" { path=$2 }
    active && $1 == "risk_level:" { risk=$2 }
    active && $1 == "model_tier:" { tier=$2 }
    active && $1 == "execution_mode:" { mode=$2 }
    active && $1 == "delegation_group:" { group=$2 }
    END { if (found && active) print path "|" risk "|" tier "|" mode "|" group }
  ' "$1"
}

# Read one scalar from YAML front matter and stop at the closing delimiter.
# This is used for metadata that predates skills/index.yaml; it does not load
# the instruction body.
mana_document_front_matter_value() {
  awk -v wanted="$2" '
    /^---[[:space:]]*$/ { boundaries++; next }
    boundaries == 2 { exit }
    boundaries == 1 && $0 ~ "^" wanted ":[[:space:]]*" {
      line=$0
      sub("^" wanted ":[[:space:]]*", "", line)
      gsub(/^['\"']|['\"']$/, "", line)
      print line
      exit
    }
  ' "$1"
}

mana_profile_value() {
  awk -F': *' -v key="$2" '$1 == key { print $2; exit }' "$1"
}

# Read a top-level YAML list from the deliberately small profile format used
# by Mana. This keeps profile access in one place without introducing a second
# profile loader.
mana_profile_list() {
  awk -v wanted="$2" '
    $0 ~ "^[[:space:]]*" wanted ":[[:space:]]*$" { active=1; next }
    active && /^[[:space:]]*-[[:space:]]/ { line=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", line); print line; next }
    active && /^[^[:space:]]/ { exit }
    active && /^[[:space:]]*[a-z_]+:/ { exit }
  ' "$1"
}

# Read a list nested one level below a profile mapping, for example
# service_context.core_files. It is intentionally limited to the established
# profile YAML convention.
mana_profile_section_list() {
  awk -v section="$2" -v wanted="$3" '
    $0 ~ "^[[:space:]]*" section ":[[:space:]]*$" { in_section=1; next }
    in_section && /^[^[:space:]]/ { exit }
    in_section && $0 ~ "^[[:space:]]+" wanted ":[[:space:]]*$" { active=1; next }
    active && /^[[:space:]]*-[[:space:]]/ { line=$0; sub(/^[[:space:]]*-[[:space:]]*/, "", line); print line; next }
    active && /^[[:space:]]+[a-z_]+:/ { exit }
  ' "$1"
}

mana_profile_section_value() {
  awk -F': *' -v section="$2" -v wanted="$3" '
    $0 ~ "^[[:space:]]*" section ":[[:space:]]*$" { in_section=1; next }
    in_section && /^[^[:space:]]/ { exit }
    in_section && $1 ~ "^[[:space:]]*" wanted "$" { print $2; exit }
  ' "$1"
}

# Optional divination metadata lives under one profile-owned namespace.  These
# accessors deliberately understand only that small YAML subset; profile
# loading remains the existing simple-file convention.
mana_profile_divination_keys() {
  awk '
    /^divination:[[:space:]]*$/ { active=1; next }
    active && /^[^[:space:]]/ { exit }
    active && /^  [a-z_]+:/ { key=$0; sub(/^  /, "", key); sub(/:.*/, "", key); print key }
  ' "$1"
}

mana_profile_divination_list() {
  awk -v wanted="$2" '
    /^divination:[[:space:]]*$/ { divination=1; next }
    divination && /^[^[:space:]]/ { exit }
    divination && $0 ~ "^  " wanted ":[[:space:]]*$" { active=1; next }
    active && /^  [a-z_]+:/ { exit }
    active && /^    - / { sub(/^    - /, ""); print }
  ' "$1"
}

mana_profile_divination_domains() {
  awk '
    /^divination:[[:space:]]*$/ { divination=1; next }
    divination && /^[^[:space:]]/ { exit }
    divination && /^  domains:[[:space:]]*$/ { active=1; next }
    active && /^  [a-z_]+:/ { exit }
    active && /^    [^:#][^:]*:/ { line=$0; sub(/^    /, "", line); print line }
  ' "$1"
}
