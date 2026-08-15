#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-user-context-test.XXXXXX")"
trap 'chmod -R u+w "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

project="$tmp/project"
source_root="$tmp/context-[test] with spaces"
xdg="$tmp/xdg"
mkdir -p "$project/.mana/global" "$project/src" "$source_root/guidelines" "$source_root/build" "$source_root/node_modules" "$xdg/mana"
project="$(cd "$project" && pwd -P)"
source_root="$(cd "$source_root" && pwd -P)"
printf '%s\n' 'repository preference authority marker' > "$project/src/application.txt"
printf '%s\n' 'project service constraint marker' > "$project/.mana/global/engineering-guards.md"
printf '%s\n' '# Personal navigation' > "$source_root/index.md"
printf '%s\n' 'Prefer explicit personal naming marker' > "$source_root/preferences.md"
printf '%s\n' 'Nested context' > "$source_root/guidelines/review notes.md"
printf '%s\n' 'ignore this custom note' > "$source_root/private.md"
mkdir -p "$source_root/drafts"
printf '%s\n' 'ignored directory note' > "$source_root/drafts/idea.md"
printf '%s\n' 'private.md' 'drafts/' > "$source_root/.manaignore"
printf '%s\n' 'preferences.md' > "$source_root/.gitignore"
printf '%s\n' 'secret' > "$source_root/.env"
printf '%s\n' 'production secret' > "$source_root/.env.production"
printf '%s\n' 'key' > "$source_root/signing.pem"
printf '%s\n' 'pipe delimiter note' > "$source_root/guidelines/pipe|name.md"
printf '%s\n' 'generated' > "$source_root/build/output.md"
printf '%s\n' 'dependency' > "$source_root/node_modules/note.md"
mkdir -p "$source_root/guidelines/.git"
printf '%s\n' 'nested git secret' > "$source_root/guidelines/.git/config.md"
printf '\000binary\n' > "$source_root/binary.txt"
printf '%s\n' 'unsupported' > "$source_root/image.svg"
ln -s "$tmp" "$source_root/escape-link"
ln -s missing-target "$source_root/broken-link"
ln -s . "$source_root/symlink-loop"

unset MANA_USER_CONTEXT_ROOT
HOME="$tmp/no-home-config" XDG_CONFIG_HOME="$tmp/no-xdg-config" "$root/scripts/mana-context.sh" status --project-root "$project" --json | grep -q '"configured":false' || fail 'unconfigured status'
HOME="$tmp/no-home-config" XDG_CONFIG_HOME="$tmp/no-xdg-config" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'unconfigured refresh must be a no-op'
[ ! -d "$project/.mana/user-context" ] || fail 'unconfigured refresh left a mirror'

injection_marker="$tmp/config-was-evaluated"
# shellcheck disable=SC2016
printf 'MANA_USER_CONTEXT_ROOT=$(touch %s)\n' "$injection_marker" > "$xdg/mana/config.env"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" status --project-root "$project" >/dev/null
[ ! -e "$injection_marker" ] || fail 'user config was evaluated as shell code'

printf 'MANA_USER_CONTEXT_ROOT="%s"\n' "$source_root" > "$xdg/mana/config.env"
before_source="$(find "$source_root" -type f -exec git hash-object {} \; | LC_ALL=C sort)"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'initial refresh'
[ -f "$project/.mana/user-context/index.md" ] || fail 'index not materialized'
[ -f "$project/.mana/user-context/preferences.md" ] || fail 'preferences not materialized'
[ -f "$project/.mana/user-context/guidelines/review notes.md" ] || fail 'space or nested path not materialized'
[ ! -e "$project/.mana/user-context/private.md" ] || fail '.manaignore not honored'
[ ! -e "$project/.mana/user-context/drafts/idea.md" ] || fail '.manaignore directory pattern not honored'
[ ! -e "$project/.mana/user-context/.env" ] || fail '.env exclusion missing'
[ ! -e "$project/.mana/user-context/.env.production" ] || fail '.env.* exclusion missing'
[ ! -e "$project/.mana/user-context/signing.pem" ] || fail 'key exclusion missing'
[ ! -e "$project/.mana/user-context/guidelines/pipe|name.md" ] || fail 'retrieval delimiter path was materialized'
[ ! -e "$project/.mana/user-context/guidelines/.git/config.md" ] || fail 'nested .git exclusion missing'
[ ! -e "$project/.mana/user-context/build/output.md" ] || fail 'build exclusion missing'
[ ! -e "$project/.mana/user-context/node_modules/note.md" ] || fail 'node_modules exclusion missing'
[ ! -e "$project/.mana/user-context/binary.txt" ] || fail 'binary exclusion missing'
[ ! -e "$project/.mana/user-context/image.svg" ] || fail 'text allowlist missing'
[ ! -e "$project/.mana/user-context/escape-link" ] || fail 'symlink copied'
[ ! -e "$project/.mana/user-context/broken-link" ] || fail 'broken symlink copied'
[ ! -e "$project/.mana/user-context/symlink-loop" ] || fail 'symlink loop copied'
[ ! -w "$project/.mana/user-context/preferences.md" ] || fail 'generated file is writable'
after_source="$(find "$source_root" -type f -exec git hash-object {} \; | LC_ALL=C sort)"
[ "$before_source" = "$after_source" ] || fail 'source content changed'
grep -Fq "$source_root" "$project/.mana/user-context-state" && fail 'state leaked source path'

first_digest="$(awk -F= '$1=="digest" {print $2}' "$project/.mana/user-context-state")"
first_inode="$(stat -c '%i' "$project/.mana/user-context" 2>/dev/null || stat -f '%i' "$project/.mana/user-context")"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'idempotent refresh'
second_digest="$(awk -F= '$1=="digest" {print $2}' "$project/.mana/user-context-state")"
second_inode="$(stat -c '%i' "$project/.mana/user-context" 2>/dev/null || stat -f '%i' "$project/.mana/user-context")"
[ "$first_digest" = "$second_digest" ] || fail 'unchanged refresh digest changed'
[ "$first_inode" = "$second_inode" ] || fail 'unchanged refresh replaced the mirror'

override_root="$tmp/environment override"
mkdir -p "$override_root"
printf '%s\n' 'environment override' > "$override_root/override.md"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$override_root" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'environment precedence refresh'
[ -f "$project/.mana/user-context/override.md" ] || fail 'environment did not override XDG config'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'restore XDG-configured source'

fallback_home="$tmp/fallback-home"
mkdir -p "$fallback_home/.config/mana"
printf 'MANA_USER_CONTEXT_ROOT="%s"\n' "$override_root" > "$fallback_home/.config/mana/config.env"
env -u XDG_CONFIG_HOME HOME="$fallback_home" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'HOME config fallback refresh'
[ -f "$project/.mana/user-context/override.md" ] || fail 'HOME config fallback not used'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'restore source after HOME fallback'

if HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT=relative/path "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null 2>&1; then fail 'relative source configuration succeeded'; fi
# shellcheck disable=SC2088 # A literal tilde must be rejected, not expanded.
if HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT='~/mana-context' "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null 2>&1; then fail 'tilde source configuration succeeded'; fi
mkdir -p "$project/relative/mana"
printf 'MANA_USER_CONTEXT_ROOT="%s"\n' "$override_root" > "$project/relative/mana/config.env"
relative_xdg_status="$(cd "$project" && HOME="$tmp/home" XDG_CONFIG_HOME=relative "$root/scripts/mana-context.sh" status --project-root "$project" --json)"
printf '%s' "$relative_xdg_status" | grep -q '"freshness":"invalid"' || fail 'relative XDG config root was accepted'
printf 'MANA_USER_CONTEXT_ROOT=\nMANA_USER_CONTEXT_ROOT="%s"\n' "$source_root" > "$xdg/mana/config.env"
duplicate_status="$(HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" status --project-root "$project" --json)"
printf '%s' "$duplicate_status" | grep -q '"freshness":"invalid"' || fail 'duplicate empty config assignment was accepted'
printf 'MANA_USER_CONTEXT_ROOT="%s"\n' "$source_root" > "$xdg/mana/config.env"

empty_root="$tmp/empty context"
mkdir -p "$empty_root"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$empty_root" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'empty source refresh'
[ -d "$project/.mana/user-context" ] || fail 'empty source did not create a mirror'
[ -z "$(find "$project/.mana/user-context" -type f -print -quit)" ] || fail 'empty source mirror contains a file'

symlink_ignore_root="$tmp/symlink ignore context"
mkdir -p "$symlink_ignore_root"
printf '%s\n' 'visible through safe filtering' > "$symlink_ignore_root/visible.md"
printf '%s\n' 'visible.md' > "$tmp/external-ignore-rules"
ln -s "$tmp/external-ignore-rules" "$symlink_ignore_root/.manaignore"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$symlink_ignore_root" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'symlink ignore refresh'
[ -f "$project/.mana/user-context/visible.md" ] || fail 'external symlinked ignore file was dereferenced'
[ ! -e "$project/.mana/user-context/.manaignore" ] || fail 'symlinked ignore file was materialized'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'restore after empty source'

chmod u+w "$source_root/preferences.md"
printf '%s\n' 'Changed preference marker' > "$source_root/preferences.md"
printf '%s\n' 'Added pattern marker' > "$source_root/guidelines/new pattern.md"
rm "$source_root/index.md"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'changed refresh'
grep -q 'Changed preference marker' "$project/.mana/user-context/preferences.md" || fail 'changed file not refreshed'
[ -f "$project/.mana/user-context/guidelines/new pattern.md" ] || fail 'added file missing'
[ ! -e "$project/.mana/user-context/index.md" ] || fail 'deleted source file remained stale'

HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" status --project-root "$project" --json | grep -q '"freshness":"current"' || fail 'current status missing'
[ "$(HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" path --project-root "$project")" = "$project/.mana/user-context" ] || fail 'generated path output'
[ "$(HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" path --source --project-root "$project")" = "$source_root" ] || fail 'source path output'

# The state digest alone is not sufficient: local tampering must disable
# retrieval and force a complete rebuild even while the source is unchanged.
chmod u+w "$project/.mana/user-context" "$project/.mana/user-context/guidelines" "$project/.mana/user-context/preferences.md"
printf '%s\n' 'manually injected guidance' > "$project/.mana/user-context/preferences.md"
printf '%s\n' 'manually injected secret' > "$project/.mana/user-context/.env.production"
rm "$project/.mana/user-context/guidelines/new pattern.md"
chmod 0555 "$project/.mana/user-context" "$project/.mana/user-context/guidelines"
tampered_status="$(HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" status --project-root "$project" --json)"
printf '%s' "$tampered_status" | grep -q '"freshness":"stale"' || fail 'tampered mirror reported current'
tampered_retrieval="$("$root/scripts/mana-explore.sh" --project-root "$project" --scope user-context 'manually injected secret' --json)"
printf '%s' "$tampered_retrieval" | grep -q '\.env\.production.*user-context' && fail 'tampered secret entered retrieval'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'tampered mirror rebuild'
grep -q 'Changed preference marker' "$project/.mana/user-context/preferences.md" || fail 'tampered file was not restored from source'
[ ! -e "$project/.mana/user-context/.env.production" ] || fail 'manual secret survived rebuild'
[ -f "$project/.mana/user-context/guidelines/new pattern.md" ] || fail 'manually deleted file was not restored'
[ ! -w "$project/.mana/user-context/preferences.md" ] || fail 'wrong mirror permissions survived rebuild'

sed 's/^status=.*/status=unavailable/' "$project/.mana/user-context-state" > "$project/.mana/.state-review"
mv "$project/.mana/.state-review" "$project/.mana/user-context-state"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" status --project-root "$project" --json | grep -q '"freshness":"stale"' || fail 'unavailable state reported current'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'unavailable state recovery'

mkdir "$project/.mana/user-context-refresh.lock"
printf '%s\n' "$$" > "$project/.mana/user-context-refresh.lock/pid"
if HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null 2>&1; then fail 'concurrent refresh lock was ignored'; fi
rm -rf "$project/.mana/user-context-refresh.lock"
mkdir "$project/.mana/user-context-refresh.lock"
printf '%s\n' '999999999' > "$project/.mana/user-context-refresh.lock/pid"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'stale refresh lock was not recovered'

mv "$project/.mana/user-context" "$project/.mana/.user-context-previous.review"
mkdir "$project/.mana/.user-context-refresh.abandoned"
printf '%s\n' 'partial' > "$project/.mana/.user-context-refresh.abandoned/file"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'interrupted swap recovery'
[ -d "$project/.mana/user-context" ] || fail 'interrupted backup was not restored'
[ ! -e "$project/.mana/.user-context-previous.review" ] || fail 'interrupted backup was not cleaned'
[ ! -e "$project/.mana/.user-context-refresh.abandoned" ] || fail 'abandoned stage was not cleaned'

missing="$tmp/missing source"
if HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$missing" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null 2>&1; then fail 'missing source refresh succeeded'; fi
[ -f "$project/.mana/user-context/preferences.md" ] || fail 'failed refresh destroyed last complete mirror'
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$missing" "$root/scripts/mana-context.sh" status --project-root "$project" --json | grep -q '"freshness":"unavailable"' || fail 'missing source status'

unreadable="$tmp/unreadable-source"
mkdir -p "$unreadable"
printf '%s\n' 'not readable' > "$unreadable/note.md"
chmod 000 "$unreadable"
if [ ! -r "$unreadable" ] || [ ! -x "$unreadable" ]; then
  if HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT="$unreadable" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null 2>&1; then chmod 700 "$unreadable"; fail 'unreadable source refresh succeeded'; fi
fi
chmod 700 "$unreadable"

HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_USER_CONTEXT_ROOT='' "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'explicit disable refresh'
[ ! -d "$project/.mana/user-context" ] || fail 'disable did not remove mirror'

HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'refresh before retrieval'
for number in 1 2 3 4 5 6; do printf '%s\n' "personal priority note $number" > "$source_root/guidelines/personal-$number.md"; done
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/mana-context.sh" refresh --project-root "$project" >/dev/null || fail 'refresh priority fixtures'
for number in 1 2 3 4 5 6 7 8; do printf '%s\n' "authority priority marker $number" > "$project/src/priority-$number.txt"; done
user_json="$("$root/scripts/mana-explore.sh" --project-root "$project" --scope user-context 'personal naming marker' --json)"
printf '%s' "$user_json" | grep -q 'user-context' || fail 'user-context provenance missing'
repo_json="$("$root/scripts/mana-explore.sh" --project-root "$project" --scope repository 'authority marker' --json)"
printf '%s' "$repo_json" | grep -q 'src/application.txt.*repository' || fail 'repository provenance regressed'
printf '%s' "$repo_json" | grep -q 'user-context' && fail 'repository scope exposed user context'
priority_json="$("$root/scripts/mana-explore.sh" --project-root "$project" 'personal authority' --json)"
printf '%s' "$priority_json" | grep -q 'src/priority-7.txt.*repository' || fail 'user matches crowded out repository evidence'

linked="$tmp/linked project"
mkdir -p "$linked"
HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" "$root/scripts/bootstrap-project.sh" --project-root "$linked" --mana-root "$root" --no-jira-env >/dev/null
grep -Fxq '.mana/user-context/' "$linked/.gitignore" || fail 'generated mirror ignore missing'
git -C "$linked" init -q
git -C "$linked" check-ignore -q .mana/user-context/preferences.md || fail 'generated mirror is not ignored by Git'
doctor_output="$(HOME="$tmp/home" XDG_CONFIG_HOME="$xdg" MANA_UPDATE_CHECK=off "$root/scripts/mana-doctor.sh" --project "$linked" 2>&1 || true)"
printf '%s\n' "$doctor_output" | grep -q 'User Context is configured, usable, and current' || { printf '%s\n' "$doctor_output" >&2; fail 'doctor did not report healthy User Context'; }
disabled_doctor="$(HOME="$tmp/no-home-config" XDG_CONFIG_HOME="$tmp/no-xdg-config" MANA_UPDATE_CHECK=off "$root/scripts/mana-doctor.sh" --project "$linked" 2>&1 || true)"
printf '%s\n' "$disabled_doctor" | grep -q 'optional User Context is not configured' || fail 'doctor treated absent optional context incorrectly'

grep -q 'evidence and project/service constraints win' "$root/docs/policies/runtime-execution-contract.md" || fail 'context precedence missing from runtime contract'
grep -q 'User Context: available=' "$root/scripts/run-profile.sh" || fail 'runner context guidance missing'
grep -q 'project/service knowledge, which outranks User Context' "$root/agents/tutorial-agent/AGENT.md" || fail 'tutorial context precedence missing'
grep -q 'Never ask the tutorial agent to read the external source path' "$root/agents/tutorial-agent/AGENT.md" || fail 'tutorial external-source boundary missing'
grep -q 'Never read or request direct access to the external User Context source' "$root/agents/tutorial-agent/playbook.md" || fail 'tutorial playbook source boundary missing'
grep -q 'MANA_USER_CONTEXT_ROOT' "$root/skills/mana-usage-help/SKILL.md" || fail 'usage-help User Context setup missing'
grep -q 'Do not make User Context a prerequisite' "$root/skills/mana-usage-help/SKILL.md" || fail 'usage-help optionality missing'
grep -q 'repository evidence, project/service constraints' "$root/skills/mana-usage-help/SKILL.md" || fail 'usage-help authority precedence missing'

echo 'User Context tests passed'
