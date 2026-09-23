#!/usr/bin/env bash
set -u

if [ "${MANA_PROVIDER_USAGE_SCENARIO:-}" = argv ]; then
  : "${MANA_PROVIDER_ARG_CAPTURE:?}"
  { printf '%s\n' "$#"; printf '%s\n' "$@"; } > "$MANA_PROVIDER_ARG_CAPTURE"
  exit 0
fi

final=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output-last-message) final="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

case "${MANA_PROVIDER_USAGE_SCENARIO:-complete}" in
  complete)
    printf '%s\n' 'human final message' > "$final"
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":120,"cached_input_tokens":30,"uncached_input_tokens":90,"output_tokens":25,"reasoning_tokens":7}}'
    printf '%s\n' '{"type":"item.completed","item":{"type":"function_call","arguments":"PAYLOAD-MUST-NOT-LEAK-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}}'
    ;;
  missing)
    printf '%s\n' 'human final message' > "$final"
    printf '%s\n' '{"type":"turn.completed"}'
    ;;
  malformed)
    printf '%s\n' 'human final message' > "$final"
    printf '%s\n' '{not-json'
    ;;
  interrupted)
    printf '%s\n' 'human final message' > "$final"
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":5}}'
    exit 130
    ;;
  failure)
    printf '%s\n' 'partial final message' > "$final"
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":8,"output_tokens":2}}'
    exit 17
    ;;
  float)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":1.5}}'
    ;;
  negative)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":-1}}'
    ;;
  numeric-string)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":"123"}}'
    ;;
  null)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":null}}'
    ;;
  large-valid)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":9007199254740991}}'
    ;;
  large-invalid)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":9007199254740992}}'
    ;;
  wait-for-signal)
    printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":5}}'
    : "${MANA_PROVIDER_SIGNAL_READY:?}"
    : "${MANA_PROVIDER_SIGNAL_DELIVERED:?}"
    trap 'printf "%s\\n" TERM > "$MANA_PROVIDER_SIGNAL_DELIVERED"; exit 143' TERM
    : > "$MANA_PROVIDER_SIGNAL_READY"
    while :; do sleep 1; done
    ;;
esac
