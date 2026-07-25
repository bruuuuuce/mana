#!/usr/bin/env bash
# Read-only deterministic recommendation engine for `mana divination`.

divination_normalize() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' ' ' | sed 's/^ *//; s/ *$//; s/  */ /g'
}
divination_contains_word() { case " $1 " in *" $2 "*) return 0 ;; *) return 1 ;; esac; }
divination_skill_field() { awk -v key="$2" '$0 == "---" { n++; next } n == 2 { exit } n == 1 && index($0,key ":") == 1 { v=substr($0,length(key)+2); sub(/^[[:space:]]+/,"",v); gsub(/^"|"$/, "", v); print v; exit }' "$1"; }
divination_reason() { # code, points, detail; comma is deliberately disallowed by metadata validation
  DIVINATION_REASON_BUFFER="${DIVINATION_REASON_BUFFER}${DIVINATION_REASON_BUFFER:+,}$1@$2@$3"
  [ "$2" -ge 0 ] && DIVINATION_POSITIVE_BUFFER="${DIVINATION_POSITIVE_BUFFER}${DIVINATION_POSITIVE_BUFFER:+, }$1: $3" || DIVINATION_NEGATIVE_BUFFER="${DIVINATION_NEGATIVE_BUFFER}${DIVINATION_NEGATIVE_BUFFER:+, }$1: $3"
}
divination_strength_points() { case "$1" in strong) echo 25;; medium) echo 15;; weak) echo 8;; *) return 1;; esac; }
divination_context_id() { printf '%s' "$1" | sed 's/\.md$//' | tr '-' ' ' | tr -cs '[:alnum:]' ' ' | sed 's/^ *//; s/ *$//; s/  */ /g'; }

divination_context_file() {
  local config="$1" wanted; wanted="$(divination_context_id "$2")"
  awk -F'\t' '{print $4}' "$config" | tr ',' '\n' | while IFS= read -r file; do
    [ "$(divination_context_id "$file")" = "$wanted" ] && { printf '%s\n' "$file"; break; }
  done
}
divination_domain_known() { awk -F'\t' -v domain="$2" '$1 == domain { found=1 } END { exit !found }' "$1"; }
divination_repository_has_domain() {
  local project="$1" domain="$2"
  case "$domain" in
    contract) [ -f "$project/asyncapi.yaml" ] || [ -f "$project/asyncapi.yml" ] || grep -RIl -m 1 --exclude-dir=.git --include='pom.xml' --include='*.gradle*' 'kafka\|messaging' "$project" >/dev/null 2>&1 ;;
    database|liquibase) [ -f "$project/liquibase.properties" ] || [ -d "$project/db/changelog" ] || grep -RIl -m 1 --exclude-dir=.git --include='pom.xml' --include='*.gradle*' 'liquibase\|oracle' "$project" >/dev/null 2>&1 ;;
    testing) [ -d "$project/tests" ] || [ -d "$project/test" ] || [ -f "$project/playwright.config.ts" ] ;;
    architecture) [ -f "$project/ARCHITECTURE.md" ] || [ -f "$project/docs/architecture.md" ] ;;
    *) return 1 ;;
  esac
}

divination_validate_metadata() {
  DIVINATION_ERROR=""; local root="$1" config="$1/config/divination-domains.tsv" profile skill name key term normalized seen domains domain strength conflict context file
  [ -f "$config" ] || { DIVINATION_ERROR="divination domain configuration is missing: $config"; return 1; }
  for profile in "$root"/profiles/*.yaml; do
    [ -f "$profile" ] || continue
    name="$(mana_profile_value "$profile" name)"
    [ -n "$name" ] || { DIVINATION_ERROR="profile metadata is invalid: $profile is missing name"; return 1; }
    [ -n "$(mana_profile_value "$profile" trigger)" ] || { DIVINATION_ERROR="profile metadata is invalid: $profile is missing trigger"; return 1; }
    skill="$(mana_profile_skills "$profile")"; [ -n "$skill" ] || { DIVINATION_ERROR="profile metadata is invalid: $profile is missing skills"; return 1; }
    while IFS= read -r skill; do [ -z "$skill" ] || [ -f "$root/skills/$skill/SKILL.md" ] || { DIVINATION_ERROR="profile metadata is invalid: $profile references missing skill $skill"; return 1; }; done <<EOF
$skill
EOF
    for key in $(mana_profile_divination_keys "$profile"); do
      case "$key" in intents|domains|positive_signals|negative_signals|required_context|conflicts_with) ;; *) DIVINATION_ERROR="divination metadata is invalid: $profile contains unsupported or governance-overriding key $key"; return 1;; esac
    done
    seen=" "
    while IFS= read -r term; do
      [ -z "$term" ] && continue; normalized="$(divination_normalize "$term")"
      [ -n "$normalized" ] || { DIVINATION_ERROR="divination metadata is invalid: $profile has an empty intent term"; return 1; }
      case " $seen " in *" |$normalized| "*) DIVINATION_ERROR="divination metadata is invalid: $profile has duplicate normalized intent term: $term"; return 1;; esac
      seen="$seen|$normalized|"
    done <<EOF
$(mana_profile_divination_list "$profile" intents)
EOF
    while IFS=: read -r domain strength; do
      [ -z "$domain" ] && continue
      domain="$(divination_normalize "$domain" | tr ' ' '-')"; strength="$(printf '%s' "$strength" | sed 's/^ *//; s/ *$//')"
      divination_domain_known "$config" "$domain" || { DIVINATION_ERROR="divination metadata is invalid: $profile references unknown domain $domain"; return 1; }
      divination_strength_points "$strength" >/dev/null || { DIVINATION_ERROR="divination metadata is invalid: $profile has unsupported domain strength $strength"; return 1; }
    done <<EOF
$(mana_profile_divination_domains "$profile")
EOF
    for context in $(mana_profile_divination_list "$profile" required_context); do
      file="$(divination_context_file "$config" "$context")"; [ -n "$file" ] || { DIVINATION_ERROR="divination metadata is invalid: $profile requires context with no known mapping: $context"; return 1; }
    done
    for conflict in $(mana_profile_divination_list "$profile" conflicts_with); do
      [ "$conflict" != "$name" ] || { DIVINATION_ERROR="divination metadata is invalid: $profile conflicts with itself"; return 1; }
      [ -f "$root/profiles/$conflict.yaml" ] || { DIVINATION_ERROR="divination metadata is invalid: $profile conflicts with unknown profile $conflict"; return 1; }
    done
    for term in $(mana_profile_divination_list "$profile" positive_signals); do
      normalized="$(divination_normalize "$term")"; for negative in $(mana_profile_divination_list "$profile" negative_signals); do [ "$normalized" != "$(divination_normalize "$negative")" ] || { DIVINATION_ERROR="divination metadata is invalid: $profile declares contradictory positive and negative signal: $term"; return 1; }; done
    done
  done
}

divination_profile_explicit_domain_matches() {
  local profile="$1" domains="$2" domain strength
    while IFS=: read -r domain strength; do
      [ -z "$domain" ] && continue
      domain="$(divination_normalize "$domain" | tr ' ' '-')"
    printf '%s\n' "$domains" | grep -Eq "^$domain\|detected\|" && return 0
  done <<EOF
$(mana_profile_divination_domains "$profile")
EOF
  return 1
}

# Public engine API. It fills DIVINATION_* globals and performs only reads.
divination_recommend() {
  local root="$1" project="$2" raw_intent="$3" config line domain aliases needed context risk alias normalized_alias negative matched
  local profile name trigger skills skill score selected_skills state points term context_file conflict conflict_profile
  DIVINATION_ERROR=""; DIVINATION_INTENT="$raw_intent"; DIVINATION_STATUS=""; DIVINATION_PROFILE=""; DIVINATION_PROFILE_FINGERPRINT=""; DIVINATION_CONFIDENCE="insufficient-evidence"
  DIVINATION_DOMAINS=""; DIVINATION_MISSING=""; DIVINATION_CANDIDATES=""; DIVINATION_SKILLS=""; DIVINATION_ROUTING=""; DIVINATION_GATES=""; DIVINATION_IGNORED=""; DIVINATION_NORMALIZED="$(divination_normalize "$raw_intent")"
  [ -n "$DIVINATION_NORMALIZED" ] || { DIVINATION_ERROR="the intent is empty; provide a delivery intent as an argument or through standard input"; return 2; }
  [ -d "$root/profiles" ] || { DIVINATION_ERROR="Mana is not initialized: profiles directory is missing: $root/profiles"; return 2; }
  divination_validate_metadata "$root" || return 2; config="$root/config/divination-domains.tsv"
  while IFS=$'\t' read -r domain aliases needed context risk; do
    case "$domain" in ''|'#'*) continue;; esac; negative=0; matched=false
    IFS=','; for alias in $aliases; do normalized_alias="$(divination_normalize "$alias")"; divination_contains_word "$DIVINATION_NORMALIZED" "$normalized_alias" || continue; matched=true; if divination_contains_word "$DIVINATION_NORMALIZED" "no $normalized_alias" || divination_contains_word "$DIVINATION_NORMALIZED" "without $normalized_alias" || divination_contains_word "$DIVINATION_NORMALIZED" "avoid $normalized_alias"; then negative=1; fi; break; done; unset IFS
    [ "$matched" = true ] || continue
    [ "$negative" -eq 1 ] && state=conflicting || state=detected
    DIVINATION_DOMAINS="${DIVINATION_DOMAINS}${DIVINATION_DOMAINS:+$'\n'}$domain|$state|$risk|$context"
  done < "$config"
  [ -n "$DIVINATION_DOMAINS" ] || { DIVINATION_STATUS="insufficient-evidence"; DIVINATION_ERROR="no meaningful recommendation can be made; name a delivery domain such as API, Kafka, database, Liquibase, test, or architecture"; return 1; }
  for profile in "$root"/profiles/*.yaml; do
    [ -f "$profile" ] || continue; name="$(mana_profile_value "$profile" name)"; trigger="$(mana_profile_value "$profile" trigger)"; skills="$(mana_profile_skills "$profile")"; score=0; selected_skills=""; DIVINATION_REASON_BUFFER=""; DIVINATION_POSITIVE_BUFFER=""; DIVINATION_NEGATIVE_BUFFER=""
    while IFS='|' read -r domain state risk context; do
      line="$(awk -F'\t' -v d="$domain" '$1 == d {print; exit}' "$config")"; needed="$(printf '%s' "$line" | awk -F'\t' '{print $3}')"
      IFS=','; for skill in $needed; do
        if printf '%s\n' "$skills" | grep -Fxq "$skill"; then
          if [ "$state" = detected ]; then score=$((score+20)); divination_reason SKILL_DOMAIN_MATCH 20 "$domain via $skill"; selected_skills="${selected_skills}${selected_skills:+,}$skill"; else score=$((score-12)); divination_reason NEGATIVE_SIGNAL_MATCH -12 "intent excludes $domain"; fi; break
        fi
      done; unset IFS
      if [ "$state" = detected ] && divination_repository_has_domain "$project" "$domain" && [ -n "$selected_skills" ]; then score=$((score+2)); divination_reason STACK_CONTEXT_MATCH 2 "repository stack confirms $domain"; fi
    done <<EOF
$DIVINATION_DOMAINS
EOF
    while IFS=: read -r domain strength; do
      [ -z "$domain" ] && continue
      domain="$(divination_normalize "$domain" | tr ' ' '-')"; strength="$(printf '%s' "$strength" | sed 's/^ *//; s/ *$//')"; points="$(divination_strength_points "$strength")"
      if printf '%s\n' "$DIVINATION_DOMAINS" | grep -Eq "^$domain\|detected\|"; then score=$((score+points)); divination_reason DOMAIN_EXPLICIT_MATCH "$points" "$domain ($strength)"; fi
    done <<EOF
$(mana_profile_divination_domains "$profile")
EOF
    while IFS= read -r term; do [ -z "$term" ] && continue; if divination_contains_word "$DIVINATION_NORMALIZED" "$(divination_normalize "$term")"; then score=$((score+6)); divination_reason POSITIVE_SIGNAL_MATCH 6 "$term"; fi; done <<EOF
$(mana_profile_divination_list "$profile" positive_signals)
EOF
    while IFS= read -r term; do [ -z "$term" ] && continue; if divination_contains_word "$DIVINATION_NORMALIZED" "$(divination_normalize "$term")"; then score=$((score-16)); divination_reason NEGATIVE_SIGNAL_MATCH -16 "$term"; fi; done <<EOF
$(mana_profile_divination_list "$profile" negative_signals)
EOF
    normalized_alias="$(divination_normalize "$trigger" | tr '_' ' ')"; if [ "$normalized_alias" != "during development" ] && divination_contains_word "$DIVINATION_NORMALIZED" "$normalized_alias"; then score=$((score+10)); divination_reason PROFILE_TRIGGER_MATCH 10 "$trigger"; fi
    for context in $(mana_profile_divination_list "$profile" required_context); do context_file="$(divination_context_file "$config" "$context")"; if [ ! -s "$project/.mana/global/$context_file" ]; then score=$((score-8)); divination_reason REQUIRED_CONTEXT_MISSING -8 "$context_file"; DIVINATION_MISSING="${DIVINATION_MISSING}${DIVINATION_MISSING:+$'\n'}$context_file (required by $name)"; fi; done
    for conflict in $(mana_profile_divination_list "$profile" conflicts_with); do conflict_profile="$root/profiles/$conflict.yaml"; if divination_profile_explicit_domain_matches "$conflict_profile" "$DIVINATION_DOMAINS"; then score=$((score-20)); divination_reason PROFILE_CONFLICT -20 "conflicts with $conflict"; fi; done
    DIVINATION_CANDIDATES="${DIVINATION_CANDIDATES}${DIVINATION_CANDIDATES:+$'\n'}$name|$score|$DIVINATION_POSITIVE_BUFFER|$DIVINATION_NEGATIVE_BUFFER|$selected_skills|$DIVINATION_REASON_BUFFER"
  done
  DIVINATION_CANDIDATES="$(printf '%s\n' "$DIVINATION_CANDIDATES" | sort -t'|' -k2,2nr -k1,1)"
  local best second best_name best_score second_score best_skills
  best="$(printf '%s\n' "$DIVINATION_CANDIDATES" | sed -n '1p')"; second="$(printf '%s\n' "$DIVINATION_CANDIDATES" | sed -n '2p')"; best_name="${best%%|*}"; best_score="$(printf '%s' "$best" | cut -d'|' -f2)"; best_skills="$(printf '%s' "$best" | cut -d'|' -f5)"; second_score="$(printf '%s' "$second" | cut -d'|' -f2)"
  [ "$best_score" -ge 20 ] || { DIVINATION_STATUS="insufficient-evidence"; DIVINATION_ERROR="no profile has enough matching evidence; add the affected technology or delivery phase"; return 1; }
  if [ -n "$second" ] && [ "$best_score" = "$second_score" ]; then DIVINATION_STATUS=ambiguous; DIVINATION_CONFIDENCE=ambiguous; else DIVINATION_STATUS=recommended; DIVINATION_PROFILE="$best_name"; DIVINATION_PROFILE_FINGERPRINT="$(cksum < "$root/profiles/$best_name.yaml" | awk '{print $1 "-" $2}')"; [ "$best_score" -ge 40 ] && DIVINATION_CONFIDENCE=high || DIVINATION_CONFIDENCE=medium; fi
  DIVINATION_SKILLS="$(printf '%s\n' "$best_skills" | tr ',' '\n' | sed '/^$/d' | sort -u | tr '\n' ',' | sed 's/,$//')"; best_skills="$DIVINATION_SKILLS"
  IFS=','; for skill in $best_skills; do [ -z "$skill" ] && continue; local skill_file="$root/skills/$skill/SKILL.md" tier group owner; tier="$(divination_skill_field "$skill_file" model_tier)"; group="$(divination_skill_field "$skill_file" delegation_group)"; owner="$(divination_skill_field "$skill_file" owner_role)"; DIVINATION_ROUTING="${DIVINATION_ROUTING}${DIVINATION_ROUTING:+$'\n'}$skill|${tier:-economy}|${group:-unspecified}"; [ "$tier" = full ] && DIVINATION_GATES="${DIVINATION_GATES}${DIVINATION_GATES:+$'\n'}$owner"; done; unset IFS
  [ "$(mana_profile_value "$root/profiles/$best_name.yaml" human_approval_requirement)" = true ] && DIVINATION_GATES="${DIVINATION_GATES}${DIVINATION_GATES:+$'\n'}profile owner approval"
  while IFS='|' read -r domain state risk context; do [ "$state" = detected ] || continue; IFS=','; for context_file in $context; do [ -s "$project/.mana/global/$context_file" ] || DIVINATION_MISSING="${DIVINATION_MISSING}${DIVINATION_MISSING:+$'\n'}$context_file (needed for $domain)"; done; unset IFS; done <<EOF
$DIVINATION_DOMAINS
EOF
  DIVINATION_GATES="$(printf '%s\n' "$DIVINATION_GATES" | sed '/^$/d' | sort -u)"; DIVINATION_MISSING="$(printf '%s\n' "$DIVINATION_MISSING" | sed '/^$/d' | sort -u)"; DIVINATION_IGNORED="$(printf '%s\n' "$DIVINATION_NORMALIZED" | tr ' ' '\n' | awk 'length($0)>3 && $0 !~ /^(add|field|using|with|into|from|that|this|change|persist)$/ {print}' | sort -u | tr '\n' ',' | sed 's/,$//')"
}
