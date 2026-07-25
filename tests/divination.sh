#!/usr/bin/env bash
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-divination.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
project="$tmp/project"
mkdir -p "$project/.mana/global"
printf 'architecture\n' > "$project/.mana/global/architecture.md"
printf 'integration\n' > "$project/.mana/global/integration-map.md"
printf 'database\n' > "$project/.mana/global/database-policy.md"
printf 'keep\n' > "$project/.mana/sentinel"

fail() { echo "FAIL: $*" >&2; exit 1; }
run() { "$root/scripts/divination.sh" --project-root "$project" "$@"; }

out="$(run 'Add a field to a Kafka contract and persist it in Oracle using Liquibase')"
printf '%s\n' "$out" | grep -Fq 'profile: architecture-review' || fail 'clear recommendation'
printf '%s\n' "$out" | tail -n 1 | grep -Fxq 'No spell has been cast.' || fail 'read-only confirmation'

. "$root/scripts/lib/profile-metadata.sh"
. "$root/scripts/lib/divination.sh"
divination_recommend "$root" "$project" 'KAFKA-contract, persistence!' || fail 'normalization result'
[ "$DIVINATION_NORMALIZED" = 'kafka contract persistence' ] || fail 'normalization'
divination_recommend "$root" "$project" 'Kafka contract without database persistence' || true
printf '%s\n' "$DIVINATION_DOMAINS" | grep -Fq 'database|conflicting' || fail 'negative signal'

before="$(find "$project/.mana" -type f -exec shasum {} \; | sort)"
one="$(run 'Kafka contract and Liquibase migration' --json)"
two="$(run 'Kafka contract and Liquibase migration' --json)"
[ "$one" = "$two" ] || fail 'stable JSON output'
printf '%s' "$one" | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const x=JSON.parse(s);if(!x.readOnly||!x.candidates.length||x.recommendedProfile!=="architecture-review")process.exit(1)})' || fail 'JSON structure'
after="$(find "$project/.mana" -type f -exec shasum {} \; | sort)"
[ "$before" = "$after" ] || fail 'divination wrote .mana'

missing="$tmp/missing"; mkdir -p "$missing"
missing_out="$($root/scripts/divination.sh --project-root "$missing" 'Kafka contract' 2>&1)" || fail 'missing context should be reported'
printf '%s\n' "$missing_out" | grep -Fq 'Missing evidence:' || fail 'missing Service Context'

fixture="$tmp/fixture"
mkdir -p "$fixture/profiles" "$fixture/skills/liquibase-production-risk" "$fixture/config"
cp "$root/skills/liquibase-production-risk/SKILL.md" "$fixture/skills/liquibase-production-risk/SKILL.md"
cp "$root/config/divination-domains.tsv" "$fixture/config/divination-domains.tsv"
for name in alpha beta; do
  printf 'name: %s\ntrigger: review\nskills:\n- liquibase-production-risk\nhuman_approval_requirement: false\n' "$name" > "$fixture/profiles/$name.yaml"
done
divination_recommend "$fixture" "$project" 'Liquibase migration' || true
[ "$DIVINATION_STATUS" = ambiguous ] || fail 'ambiguous recommendation'
printf '%s\n' "$DIVINATION_CANDIDATES" | head -n 2 | cut -d'|' -f1 | tr '\n' ' ' | grep -Fxq 'alpha beta ' || fail 'tie ordering'

printf 'name: broken\nskills:\n- absent-skill\n' > "$fixture/profiles/broken.yaml"
if divination_recommend "$fixture" "$project" 'Liquibase migration'; then fail 'invalid profile metadata accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'profile metadata is invalid' || fail 'invalid profile diagnostic'
rm "$fixture/profiles/broken.yaml"

# Profiles without the optional block keep the original mapped-skill behaviour.
divination_recommend "$fixture" "$project" 'Liquibase migration' || true
[ "$DIVINATION_STATUS" = ambiguous ] || fail 'profiles without divination metadata are not backward compatible'

meta="$tmp/meta-fixture"
mkdir -p "$meta/profiles" "$meta/skills/liquibase-production-risk" "$meta/config"
cp "$root/skills/liquibase-production-risk/SKILL.md" "$meta/skills/liquibase-production-risk/SKILL.md"
cp "$root/config/divination-domains.tsv" "$meta/config/divination-domains.tsv"
printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    liquibase: strong' '  positive_signals:' '    - oracle' '  required_context:' '    - database-policy' > "$meta/profiles/explicit.yaml"
printf '%s\n' 'name: plain' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' > "$meta/profiles/plain.yaml"
divination_recommend "$meta" "$project" 'Oracle Liquibase migration' || fail 'explicit metadata recommendation'
[ "$DIVINATION_PROFILE" = explicit ] || fail 'explicit domain match did not improve ranking'
printf '%s\n' "$DIVINATION_CANDIDATES" | head -n 1 | grep -Fq 'DOMAIN_EXPLICIT_MATCH@25@liquibase (strong)' || fail 'explicit domain reason code'

missing_context="$tmp/no-context"; mkdir -p "$missing_context/.mana/global"
divination_recommend "$meta" "$missing_context" 'Liquibase migration' || fail 'required context penalty recommendation'
printf '%s\n' "$DIVINATION_CANDIDATES" | head -n 1 | grep -Fq 'REQUIRED_CONTEXT_MISSING@-8@database-policy.md' || fail 'required context penalty reason'

printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    liquibase: strong' '  negative_signals:' '    - legacy migration' > "$meta/profiles/explicit.yaml"
divination_recommend "$meta" "$project" 'Legacy migration using Liquibase' || fail 'negative signal recommendation'
printf '%s\n' "$DIVINATION_CANDIDATES" | grep '^explicit|' | grep -Fq 'NEGATIVE_SIGNAL_MATCH@-16@legacy migration' || fail 'negative signal reason'

printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    liquibase: strong' '  conflicts_with:' '    - plain' > "$meta/profiles/explicit.yaml"
printf '%s\n' 'name: plain' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    liquibase: strong' > "$meta/profiles/plain.yaml"
divination_recommend "$meta" "$project" 'Liquibase migration' || fail 'conflict resolution recommendation'
[ "$DIVINATION_PROFILE" = plain ] || fail 'profile conflict did not resolve to non-conflicting candidate'
printf '%s\n' "$DIVINATION_CANDIDATES" | grep '^explicit|' | grep -Fq 'PROFILE_CONFLICT@-20@conflicts with plain' || fail 'profile conflict reason'

printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    unknown-alias: strong' > "$meta/profiles/explicit.yaml"
if divination_validate_metadata "$meta"; then fail 'unknown domain accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'unknown domain' || fail 'unknown domain diagnostic'
printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  domains:' '    liquibase: maximum' > "$meta/profiles/explicit.yaml"
if divination_validate_metadata "$meta"; then fail 'unsupported domain strength accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'unsupported domain strength' || fail 'domain strength diagnostic'
printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  intents:' '    - Contract-change' '    - contract change' > "$meta/profiles/explicit.yaml"
if divination_validate_metadata "$meta"; then fail 'duplicate normalized intent accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'duplicate normalized intent' || fail 'duplicate intent diagnostic'
printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  conflicts_with:' '    - unknown-profile' > "$meta/profiles/explicit.yaml"
if divination_validate_metadata "$meta"; then fail 'unknown conflicting profile accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'unknown profile' || fail 'unknown profile diagnostic'
printf '%s\n' 'name: explicit' 'trigger: review' 'skills:' '- liquibase-production-risk' 'human_approval_requirement: false' 'divination:' '  positive_signals:' '    - kafka' '  negative_signals:' '    - Kafka' > "$meta/profiles/explicit.yaml"
if divination_validate_metadata "$meta"; then fail 'contradictory signals accepted'; fi
printf '%s\n' "$DIVINATION_ERROR" | grep -Fq 'contradictory positive and negative' || fail 'contradictory signal diagnostic'

explained="$(run 'Add a field to a Kafka contract and persist it in Oracle using Liquibase' --explain)"
printf '%s\n' "$explained" | grep -Fq 'DOMAIN_EXPLICIT_MATCH' || fail 'explain reason codes'

if run 'make it better' >/dev/null 2>&1; then fail 'insufficient evidence accepted'; fi
echo 'Divination tests passed'
