#!/usr/bin/env bash
if [ "${MANA_PROVIDER_USAGE_SCENARIO:-}" = argv ]; then
  : "${MANA_PROVIDER_ARG_CAPTURE:?}"
  { printf '%s\n' "$#"; printf '%s\n' "$@"; } > "$MANA_PROVIDER_ARG_CAPTURE"
  exit 0
fi
printf '%s\n' 'provider final message without structured usage'
