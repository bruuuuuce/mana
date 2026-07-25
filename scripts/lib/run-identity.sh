#!/usr/bin/env bash
# Portable, test-injectable identities for persisted eval/report artifacts.
mana_digest_file() { cksum < "$1" | awk '{printf "%s-%s", $1, $2}'; }
mana_digest_paths() { local root="$1"; shift; { for p in "$@"; do [ -f "$root/$p" ] && printf '%s|%s\n' "$p" "$(mana_digest_file "$root/$p")"; done; } | LC_ALL=C sort | cksum | awk '{printf "%s-%s", $1, $2}'; }
mana_project_revision() { git -C "$1" rev-parse --short HEAD 2>/dev/null || printf workspace; }
mana_project_dirty() { [ -n "$(git -C "$1" status --porcelain 2>/dev/null || true)" ] && printf true || printf false; }
mana_run_id() { if [ -n "${MANA_TEST_RUN_ID:-}" ]; then printf '%s' "$MANA_TEST_RUN_ID"; else printf 'run-%s-%s-%s' "$(date -u +%Y%m%dT%H%M%SZ)" "$$" "${RANDOM:-0}"; fi; }
mana_generated_at() { [ -n "${MANA_TEST_GENERATED_AT:-}" ] && printf '%s' "$MANA_TEST_GENERATED_AT" || date -u +%Y-%m-%dT%H:%M:%SZ; }
