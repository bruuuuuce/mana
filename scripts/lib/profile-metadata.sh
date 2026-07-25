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
