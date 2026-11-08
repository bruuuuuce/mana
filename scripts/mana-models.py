#!/usr/bin/env python3
"""Provider model discovery and conservative tier resolution for MANA."""
from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

SCHEMA = "mana.model-resolution/v1"


class CatalogUnavailable(RuntimeError):
    """The provider supports no usable model-list discovery interface."""


def codex_catalog(binary: str) -> tuple[list[dict], str]:
    """Read the Codex App Server model/list catalog without starting a turn."""
    process = subprocess.Popen([binary, "app-server"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               bufsize=0)
    assert process.stdin and process.stdout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    line_buffer = bytearray()
    queued_lines: deque[bytes] = deque()
    responses: dict[int | str, dict] = {}

    def next_payload(deadline: float) -> dict:
        while not queued_lines:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise RuntimeError("Codex App Server model/list timed out")
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError("Codex App Server exited before model/list response")
            line_buffer.extend(chunk)
            while b"\n" in line_buffer:
                line, _, rest = line_buffer.partition(b"\n")
                line_buffer[:] = rest
                if line.strip():
                    queued_lines.append(line)
        try:
            payload = json.loads(queued_lines.popleft())
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex App Server returned malformed protocol data") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Codex App Server returned malformed protocol data")
        return payload

    def request(message: dict, response_id: int | None = None) -> dict | None:
        process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
        process.stdin.flush()
        if response_id is None:
            return None
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            payload = responses.pop(response_id, None) or next_payload(deadline)
            payload_id = payload.get("id")
            if payload_id != response_id:
                if isinstance(payload_id, (int, str)):
                    responses[payload_id] = payload
                continue
            if "error" in payload:
                error = payload["error"]
                code = error.get("code") if isinstance(error, dict) else None
                if code == -32601:
                    raise CatalogUnavailable("Codex App Server does not support model/list")
                if code in (401, 403):
                    raise RuntimeError("Codex model catalog authentication or entitlement was rejected")
                raise RuntimeError("Codex App Server rejected model/list")
            return payload.get("result", {})
        raise RuntimeError("Codex App Server model/list timed out")

    try:
        request({"method": "initialize", "id": 1, "params": {
            "clientInfo": {"name": "mana-models", "title": "MANA model discovery", "version": "1"},
            "capabilities": {"experimentalApi": True}}}, 1)
        request({"method": "initialized", "params": {}})
        data: list[dict] = []
        cursor = None
        for ordinal in range(32):
            params: dict = {"limit": 100, "includeHidden": False}
            if cursor:
                params["cursor"] = cursor
            response = request({"method": "model/list", "id": ordinal + 2, "params": params}, ordinal + 2)
            page = response.get("data")
            if not isinstance(page, list):
                raise RuntimeError("Codex model/list returned malformed catalog")
            data.extend(item for item in page if isinstance(item, dict))
            cursor = response.get("nextCursor")
            if not cursor:
                break
        else:
            raise RuntimeError("Codex model/list exceeded the bounded page count")
        return data, "codex-app-server:model/list"
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def parse_opencode_catalog(output: str) -> list[dict]:
    """Parse the `models --verbose` identity and metadata blocks."""
    clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
    lines = clean.splitlines()
    decoder = json.JSONDecoder()
    result: list[dict] = []
    index = 0
    identity = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")
    while index < len(lines):
        header = lines[index].strip()
        if not identity.fullmatch(header):
            index += 1
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines) or lines[cursor].strip() != "{":
            index += 1
            continue
        block = "\n".join(lines[cursor:])
        try:
            record, consumed = decoder.raw_decode(block)
        except json.JSONDecodeError:
            index += 1
            continue
        if not isinstance(record, dict):
            index = cursor + max(1, block[:consumed].count("\n") + 1)
            continue
        provider_id, model_id = record.get("providerID"), record.get("id")
        if isinstance(provider_id, str) and isinstance(model_id, str) and f"{provider_id}/{model_id}" == header:
            capabilities = record.get("capabilities") if isinstance(record.get("capabilities"), dict) else {}
            variants = record.get("variants") if isinstance(record.get("variants"), dict) else {}
            efforts = sorted({
                value.get("reasoningEffort") for value in variants.values()
                if isinstance(value, dict) and isinstance(value.get("reasoningEffort"), str)
            })
            result.append({"id": header, "model": header, "status": record.get("status"),
                           "capabilities": capabilities, "variants": variants,
                           "supportedReasoningEfforts": [{"reasoningEffort": value} for value in efforts]})
        index = cursor + max(1, block[:consumed].count("\n") + 1)
    return result


def discover(provider: str, fixture: str | None, refresh: bool = False,
             project: str | None = None) -> tuple[list[dict], str, str, str]:
    if fixture:
        path = Path(fixture)
        data = json.loads(path.read_text())
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            raise RuntimeError("fixture catalog must be a JSON array of objects")
        return data, f"fixture:{path.name}", "fixture-cli", "verified"
    if provider == "codex":
        binary = shutil.which(os.environ.get("MANA_CODEX_BIN", "codex"))
        if not binary:
            raise RuntimeError("Codex CLI is not installed")
        try:
            data, source = codex_catalog(binary)
        except CatalogUnavailable:
            version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
            return [], "codex-cli:provider-owned-default", version, "assumed"
        version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
        return data, source, version, "verified"
    if provider == "opencode":
        binary = shutil.which(os.environ.get("MANA_OPENCODE_BIN", "opencode"))
        if not binary:
            raise RuntimeError("OpenCode CLI is not installed")
        command = [binary, "models", "--verbose"]
        if refresh:
            command.append("--refresh")
        proc = subprocess.run(command, text=True, capture_output=True, timeout=20, cwd=project)
        if proc.returncode:
            raise RuntimeError("OpenCode model discovery failed")
        models = parse_opencode_catalog(proc.stdout)
        if not models:
            raise RuntimeError("OpenCode returned no parseable provider/model identities")
        config = subprocess.run([binary, "debug", "config", "--pure"], text=True,
                                capture_output=True, timeout=20, cwd=project)
        if config.returncode:
            raise RuntimeError("OpenCode resolved configuration discovery failed")
        try:
            configured_model = json.loads(config.stdout).get("model")
        except (json.JSONDecodeError, AttributeError):
            configured_model = None
        # Only retain the selected identity. The rest of config output can contain
        # credentials and provider settings, and is never returned or persisted.
        if isinstance(configured_model, str):
            for record in models:
                record["isDefault"] = record["model"] == configured_model
        version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
        return models, "opencode:models --verbose+debug-config:model", version, "verified"
    if provider == "claude":
        binary = shutil.which(os.environ.get("MANA_CLAUDE_BIN", "claude"))
        version = "unknown"
        if binary:
            version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
        # Claude Code documents dynamic family aliases; aliases remain unverified for account entitlement.
        models = [{"id": alias, "model": alias, "alias": True}
                  for alias in ("haiku", "sonnet", "opus")]
        return models, "claude-code:documented-family-alias", version, "assumed"
    if provider == "junie":
        binary = shutil.which(os.environ.get("MANA_JUNIE_BIN", "junie"))
        version = "unknown"
        if binary:
            version = subprocess.run([binary, "--version"], text=True, capture_output=True, timeout=5).stdout.strip()
        # Junie documents a provider-owned Default and dynamic model aliases.
        # These are accepted identities, not entitlement or tier evidence.
        models = [{"id": alias, "model": alias, "alias": True} for alias in (
            "Default", "sonnet", "opus", "fable", "gpt", "gpt-sol",
            "gpt-codex", "gpt-astra", "gpt-luna", "gpt-terra",
            "gemini-pro", "gemini-flash", "grok")]
        locations = []
        if project:
            locations.append(Path(project) / ".junie" / "models")
        junie_home = Path(os.environ.get("JUNIE_HOME", str(Path.home() / ".junie")))
        locations.append(junie_home / "models")
        for directory in locations:
            try:
                files = sorted(directory.glob("*.json"))
            except OSError:
                continue
            for profile in files[:128]:
                # Read only the public model identifier. Never include profile
                # contents, which may contain API keys or authorization headers.
                try:
                    data = json.loads(profile.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
                    model_id = f"custom:{profile.stem}"
                    models.append({"id": model_id, "model": model_id, "custom": True})
        return models, "junie:documented-default-aliases+custom-model-profiles", version, "assumed"
    raise RuntimeError("unsupported provider")


def select(provider: str, tier: str, effort: str | None, override: str | None,
           models: list[dict], source: str, version: str, confidence: str) -> dict:
    selected = override
    selected_variant = None
    status = "unknown"
    compatible = "unknown"
    reason = ""
    fallback = None
    if provider == "junie":
        found = next((m for m in models if override in (m.get("id"), m.get("model"))), None) if override else None
        if override and not found:
            selected, status, compatible = None, "unavailable", "incompatible"
            reason = "explicit Junie model is absent from documented aliases and discovered custom profiles"
        elif tier == "full":
            selected = override
            status, compatible = "blocked", "unknown"
            reason = "Junie exposes no noninteractive capability/entitlement evidence for full-tier selection"
        elif override:
            status, compatible = "unknown", "compatible"
            reason = "Junie alias or custom profile is recognized; runtime availability and entitlement are not exposed noninteractively"
        else:
            selected = "Default"
            status, compatible = "unknown", "compatible"
            reason = "Junie Default is a documented provider-owned dynamic model; entitlement is checked at invocation"
        confidence = "assumed"
    elif provider == "claude":
        if override:
            found = next((m for m in models if override in (m.get("id"), m.get("model"))), None)
            if effort:
                selected, status, compatible = override, "blocked", "incompatible"
                reason = "Claude Code adapter cannot apply the requested reasoning effort"
            elif tier == "full":
                selected, status, compatible = override, "unknown", "unknown"
                reason = "explicit Claude pin is preserved, but alias/model identity does not prove full-tier suitability"
            elif found:
                selected, status, compatible = override, "unknown", "compatible"
                reason = "documented Claude family alias; entitlement remains unverified"
            else:
                selected, status, compatible = override, "unknown", "unknown"
                reason = "explicit Claude model pin preserved; no noninteractive catalog verifies availability"
        else:
            selected = {"economy": "haiku", "standard": "sonnet", "full": "opus"}[tier]
            status = "unknown"
            compatible = "unknown" if tier == "full" else "compatible"
            reason = "documented dynamic Claude family alias; entitlement is unverified"
            if tier == "full":
                reason = "Claude family alias does not verify sufficient full-tier capability"
        confidence = "assumed"
    elif provider == "opencode":
        requested_model = override
        requested_variant = None
        if override and "#" in override:
            requested_model, requested_variant = override.rsplit("#", 1)
        candidates = [m for m in models if m.get("model") == requested_model] if override else [
            m for m in models if m.get("isDefault") is True and m.get("status") == "active"
        ]
        candidate = candidates[0] if candidates else None
        if override and models and not candidate:
            selected, status, compatible = None, "unavailable", "incompatible"
            reason = "explicit OpenCode model is absent from active project catalog; substitution forbidden"
        elif not candidate:
            selected, status, compatible = None, "blocked", "unknown"
            reason = "OpenCode exposes no active project/provider default"
        else:
            selected = candidate["model"]
            variants = candidate.get("variants", {})
            if requested_variant:
                if requested_variant not in variants:
                    selected, status, compatible = None, "blocked", "incompatible"
                    reason = "explicit OpenCode variant is absent from this model's catalog"
                else:
                    selected_variant = requested_variant
            elif effort:
                matching = [name for name, metadata in variants.items()
                            if isinstance(metadata, dict) and metadata.get("reasoningEffort") == effort]
                if matching:
                    selected_variant = matching[0]
                else:
                    status, compatible = "blocked", "incompatible"
                    reason = "OpenCode model does not advertise a variant for the requested reasoning effort"
            if status != "blocked":
                status = "available"
                compatible = "unknown" if tier == "full" else "compatible"
                reason = "active project/provider default and selected variant verified in the OpenCode catalog"
            if requested_variant and effort:
                metadata = variants.get(requested_variant, {})
                if not isinstance(metadata, dict) or metadata.get("reasoningEffort") != effort:
                    status, compatible = "blocked", "incompatible"
                    reason = "explicit OpenCode variant does not provide the requested reasoning effort"
    elif override:
        found = next((m for m in models if override in (m.get("id"), m.get("model"))), None)
        if models and found is None:
            selected, status, compatible = None, "unavailable", "incompatible"
            reason = "explicit model override is absent from provider discovery; substitution forbidden"
        else:
            status = "unknown" if not models else "available"
            supported = [item.get("reasoningEffort") for item in (found or {}).get("supportedReasoningEfforts", [])]
            # An exact user pin proves the requested identity, not the provider's
            # capability class. High-risk callers must still honor unknown.
            if effort and supported and effort not in supported:
                compatible = "incompatible"
                status = "blocked"
                reason = "explicit model does not advertise the requested reasoning effort; substitution forbidden"
            elif effort and not supported:
                compatible = "unknown"
                status = "unknown"
                reason = "explicit model is listed but reasoning-effort support is not advertised"
            else:
                # Provider metadata describes provider features, not MANA's
                # semantic risk tier. Catalog membership or a reasoning label
                # cannot establish full-tier suitability.
                compatible = "unknown" if not models or tier == "full" else "compatible"
                reason = "explicit user model override"
    elif models:
        if provider == "codex":
            candidates = [m for m in models if not m.get("hidden", False)]
            if effort:
                candidates = [m for m in candidates if effort in [x.get("reasoningEffort") for x in m.get("supportedReasoningEfforts", [])]]
            # Only a provider-declared default can be selected automatically.
            # Its provider specialty is not evidence of MANA full-tier suitability.
            if tier == "full":
                candidates = [m for m in candidates if m.get("isDefault")]
                reason = "provider default identified; full-tier suitability remains unverified"
            else:
                candidates = [m for m in candidates if m.get("isDefault")]
                reason = "provider-declared default model"
            if candidates:
                selected = candidates[0].get("model") or candidates[0].get("id")
                status = "available"
                effort_supported = not effort or effort in [x.get("reasoningEffort") for x in candidates[0].get("supportedReasoningEfforts", [])]
                compatible = "unknown" if tier == "full" else ("compatible" if effort_supported else "incompatible")
                confidence = "verified"
            else:
                status, compatible = "blocked", "unknown"
                reason = "no provider-declared model satisfies requested tier and effort; refusing downgrade"
    else:
        status, compatible = "unknown", "unknown"
        reason = "provider catalog unavailable; no verified selection policy applies"
        if provider == "codex" and source == "codex-cli:provider-owned-default" and not effort:
            selected = None
            compatible = "compatible"
            reason = "Codex CLI provider-owned default selected without a model ID because App Server model/list is unavailable"
            confidence = "assumed"
    if not selected and status == "unknown":
        if provider == "codex" and source == "codex-cli:provider-owned-default" and compatible == "compatible":
            fallback = "model ID unavailable; Codex will resolve its provider-owned default at invocation"
        else:
            fallback = "discovery cannot establish a safe model for the requested tier"
    elif tier == "full" and compatible != "compatible":
        fallback = "provider discovery does not establish full-tier capability; escalation must block"
    selected_record = next((m for m in models if selected in (m.get("id"), m.get("model"))), None)
    supported_efforts = sorted({item.get("reasoningEffort") for item in
                                (selected_record or {}).get("supportedReasoningEfforts", [])
                                if isinstance(item, dict) and isinstance(item.get("reasoningEffort"), str)})
    return {"schemaVersion": SCHEMA, "provider": provider, "executionSupport": "unsupported" if provider == "junie" else "supported",
            "requestedTier": tier,
            "reasoningEffort": effort, "explicitOverride": override, "selectedModel": selected,
            "selectedVariant": selected_variant,
            "supportedReasoningEfforts": supported_efforts,
            "discoverySource": source, "providerVersion": version, "confidence": confidence,
            "availability": status, "invocationCompatibility": compatible,
            "selectionReason": reason, "fallbackReason": fallback,
            "costPolicy": "no cross-provider fallback; no increase to existing cost ceiling"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("doctor", nargs="?", choices=["doctor"])
    parser.add_argument("--provider", required=True, choices=["codex", "claude", "opencode", "junie"])
    parser.add_argument("--tier", default="standard", choices=["economy", "standard", "full"])
    parser.add_argument("--effort")
    parser.add_argument("--model", help="explicit model pin; never silently substituted")
    parser.add_argument("--fixture", help="local deterministic provider catalog fixture")
    parser.add_argument("--project", help="project context for project-scoped provider discovery")
    parser.add_argument("--refresh", action="store_true", help="request a fresh provider catalog where supported")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    model_env = {
        "codex": "MANA_CODEX_MODEL",
        "claude": "MANA_CLAUDE_MODEL",
        "opencode": "MANA_OPENCODE_MODEL",
        "junie": "MANA_JUNIE_MODEL",
    }[args.provider]
    effort_env = {
        "codex": "MANA_CODEX_REASONING_EFFORT",
        "claude": "MANA_CLAUDE_REASONING_EFFORT",
        "opencode": "MANA_OPENCODE_REASONING_EFFORT",
        "junie": "JUNIE_EFFORT",
    }[args.provider]
    if args.model is None:
        args.model = os.environ.get(model_env) or (os.environ.get("JUNIE_MODEL") if args.provider == "junie" else None)
    if args.effort is None:
        args.effort = os.environ.get(effort_env)
    try:
        models, source, version, confidence = discover(args.provider, args.fixture, args.refresh, args.project)
        result = select(args.provider, args.tier, args.effort, args.model, models, source, version, confidence)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result = {"schemaVersion": SCHEMA, "provider": args.provider,
                  "executionSupport": "unsupported" if args.provider == "junie" else "supported",
                  "requestedTier": args.tier,
                  "reasoningEffort": args.effort, "explicitOverride": args.model, "selectedModel": None,
                  "selectedVariant": None,
                  "supportedReasoningEfforts": [],
                  "discoverySource": "unavailable", "providerVersion": "unknown", "confidence": "unknown",
                  "availability": "blocked", "invocationCompatibility": "unknown",
                  "selectionReason": "discovery failed safely", "fallbackReason": str(exc),
                  "costPolicy": "no cross-provider fallback; no increase to existing cost ceiling"}
    print(json.dumps(result, indent=2 if args.json else None, sort_keys=True))
    explicitly_pinned_unknown_tier = (
        args.model is not None and args.tier != "full" and not args.effort
        and result["selectedModel"] == args.model
        and result["invocationCompatibility"] == "unknown"
    )
    return 0 if (
        result["availability"] in ("available", "unknown")
        and result["invocationCompatibility"] == "compatible"
    ) or explicitly_pinned_unknown_tier else 2


if __name__ == "__main__":
    raise SystemExit(main())
