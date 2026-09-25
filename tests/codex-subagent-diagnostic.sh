#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/mana-codex-diagnostic.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/project/.codex/agents"
cat > "$tmp/bin/codex" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  '--version ') echo 'codex-cli test' ;;
  'features list') printf 'multi_agent stable %s\n' "${TEST_MULTI_AGENT:-true}" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "$tmp/bin/codex"

diagnose() {
  PATH="$tmp/bin:$PATH" TEST_MULTI_AGENT="${TEST_MULTI_AGENT:-true}" \
    "$root/scripts/diagnose-codex-subagent.sh" --project-root "$tmp/project" "${@}"
}

diagnose | grep -Fq 'diagnosis=role_not_found' || { echo 'missing role misclassified' >&2; exit 1; }
printf 'name = "mana_full_specialist"\nmodel = "gpt-6-sol"\n' > "$tmp/project/.codex/agents/mana-full-specialist.toml"
TEST_MULTI_AGENT=false diagnose | grep -Fq 'diagnosis=subagents_disabled' || { echo 'disabled feature misclassified' >&2; exit 1; }
printf '[agents]\nenabled = false\n' > "$tmp/project/.codex/config.toml"
diagnose | grep -Fq 'diagnosis=subagents_disabled' || { echo 'disabled agent config misclassified' >&2; exit 1; }
rm "$tmp/project/.codex/config.toml"
printf 'The model gpt-6-sol was rejected for this account\n' > "$tmp/model-error"
diagnose --spawn-error-file "$tmp/model-error" | grep -Fq 'diagnosis=model_rejected' || { echo 'model rejection misclassified' >&2; exit 1; }
printf 'agent type is currently not available\n' > "$tmp/role-error"
diagnose --spawn-error-file "$tmp/role-error" | grep -Fq 'diagnosis=role_discovery_unconfirmed' || { echo 'ambiguous role error misclassified' >&2; exit 1; }
diagnose | grep -Fq 'diagnosis=ready_for_spawn_verification' || { echo 'ready preflight misclassified' >&2; exit 1; }
mv "$tmp/project/.codex/agents/mana-full-specialist.toml" "$tmp/physical-role.toml"
ln -s "$tmp/physical-role.toml" "$tmp/project/.codex/agents/mana-full-specialist.toml"
diagnose | grep -Fq 'diagnosis=role_discovery_unconfirmed' || { echo 'symlink role misclassified' >&2; exit 1; }
echo 'Codex subagent diagnostic tests passed'
