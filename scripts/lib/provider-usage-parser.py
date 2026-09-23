#!/usr/bin/env python3
"""Numeric-only CTX-01 parser; raw trace bytes never leave this process."""
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("mana_usage_contracts", HERE / "context-runtime.py")
assert spec is not None and spec.loader is not None
runtime = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime
spec.loader.exec_module(runtime)
ALIASES = {
    "input": ("input_tokens", "inputTokens", "input"),
    "cachedInput": ("cached_input_tokens", "cachedInputTokens", "cached_input", "cachedInput"),
    "uncachedInput": ("uncached_input_tokens", "uncachedInputTokens", "uncached_input", "uncachedInput"),
    "output": ("output_tokens", "outputTokens", "output"),
    "reasoning": ("reasoning_tokens", "reasoningTokens", "reasoning"),
}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def parse_trace(path: Path) -> dict:
    totals = {key: 0 for key in ALIASES}
    complete = {key: True for key in ALIASES}
    counts = {key: None for key in ("turns", "toolCalls", "workers", "compactions")}
    errors, usage_events = 0, 0
    # Temporary traces are host-generated private files. The FD boundary
    # rejects special files/symlinks and does not emit parser diagnostics.
    payload = runtime.safe_read_bytes(path)
    for line in payload.splitlines():
        try:
            event = json.loads(line, parse_float=Decimal, object_pairs_hook=unique_pairs)
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
            for key in ("turns", "toolCalls", "workers"):
                if counts[key] is None:
                    counts[key] = 0
            kind = event.get("type", event.get("event"))
            if kind == "turn.completed": counts["turns"] += 1
            item = event.get("item")
            if kind == "tool.completed" or (kind == "item.completed" and isinstance(item, dict) and item.get("type") in {"function_call", "tool_call", "command_execution"}):
                counts["toolCalls"] += 1
            if kind in {"agent.completed", "worker.completed"}: counts["workers"] += 1
            if kind in {"compaction.completed", "context.compacted"}: counts["compactions"] = (counts["compactions"] or 0) + 1
            usage = event.get("usage")
            if usage is None:
                continue
            if not isinstance(usage, dict):
                raise ValueError("invalid usage object")
            record = {}
            for key, names in ALIASES.items():
                reported = [usage[name] for name in names if name in usage]
                if len(reported) > 1 and any(value != reported[0] for value in reported[1:]):
                    raise ValueError("conflicting usage aliases")
                if any(not isinstance(value, int) or isinstance(value, bool) for value in reported):
                    raise ValueError("invalid usage integer")
                record[key] = reported[0] if reported else None
            if runtime.usage_totals_status(record) == "invalid":
                raise ValueError("incoherent usage")
            if all(value is None for value in record.values()):
                continue
            usage_events += 1
            for key, value in record.items():
                if value is None:
                    complete[key] = False
                else:
                    totals[key] += value
                    if totals[key] > runtime.USAGE_MAX_INTEGER:
                        raise ValueError("usage overflow")
        except (ValueError, TypeError, KeyError):
            errors += 1
    totals = {key: value if usage_events and complete[key] and not errors else None for key, value in totals.items()}
    status = runtime.usage_totals_status(totals, errors)
    return {"totals": totals, **counts, "parseErrors": errors, "usageStatus": "unavailable" if status == "invalid" else status}


if __name__ == "__main__":
    try:
        print(json.dumps(parse_trace(Path(sys.argv[1])), sort_keys=True))
    except (OSError, runtime.ContractError):
        print(json.dumps({"totals": {key: None for key in ALIASES}, "turns": None, "toolCalls": None, "workers": None, "compactions": None, "parseErrors": 1, "usageStatus": "unavailable"}))
