#!/usr/bin/env python3
"""Shared CTX-09C admission guard. Exact legacy delivery is excluded."""
import json
import os
import re

PRIVATE_MARKER = re.compile(
    r"(?i)ctx09c[-_ ][a-z0-9_-]*(?:canary|secret)|"
    r"(?:prompt|source|credential|cookie|token|environment|response|reasoning|"
    r"provider[-_ ]?stderr|stderr|diff|evidence)[-_ ]?(?:canary|secret|raw)|"
    r"authorization\s*[:=]|bearer\s+|(?:api[-_ ]?key|password|cookie|access[-_ ]?token)\s*[:=]|"
    r"-----BEGIN .*PRIVATE KEY|diff --git|@@ [-+]\d")
PRIVATE_KEYS = {"environment", "env", "credential", "credentials", "authorization", "cookie",
                "cookies", "token", "accesstoken", "prompt", "response", "rawresponse", "reasoning",
                "rawreasoning", "providerstderr", "stderr", "rawsource", "sourceraw", "fulldiff",
                "rawevidence", "raw", "transcript"}


class PrivacyError(ValueError):
    def __init__(self):
        super().__init__("shadow privacy validation rejected")


def validate(value):
    """Screen all strings/keys before checkpoint, result or projection publication.

    Ambient values are never copied into the rejection. Fixed host transport
    controls and common shell bookkeeping are not semantic environment data.
    """
    ignored = {"PATH", "PWD", "OLDPWD", "HOME", "TMPDIR", "SHELL", "USER", "LOGNAME",
               "LANG", "LC_ALL", "TZ", "SHLVL", "_", "PYTHONDONTWRITEBYTECODE",
               "CTX06C_FIXTURE_ROOT", "CTX06C_STATE_DIR", "CTX06C_SCENARIO", "CTX06C_CAPABILITY_SET",
               "CTX09_ACTION", "CTX09_ARGV_CAPTURE", "CTX09C_R2A_PROJECTION_PATH",
               "CTX09C_R2A_EARLY_PROJECTION_PATH", "CTX09C_R2A_MERGE_PATH",
               "CTX09C_R2B_STDOUT", "CTX09C_R2B_STDERR", "CTX09C_R2B_COUNT", "CTX09C_R2B_EXIT",
               "CTX09C_R2C_OUTPUT", "CTX09C_R2C_EXIT", "MANA_CTX09C_FAULT",
               "MANA_CTX09C_FAULT_POINTS", "MANA_CTX09C_FAULT_STAGE"}
    secrets = [item for name, item in os.environ.items()
               if name not in ignored
               and len(item) >= 4 and item.lower() not in {"true", "false", "none", "null"}]

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z]", "", key.lower())
                if normalized in PRIVATE_KEYS:
                    raise PrivacyError()
                visit(key)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if PRIVATE_MARKER.search(item) or any(secret in item for secret in secrets):
                raise PrivacyError()
    visit(value)
    # Also screen serialized escapes so a nested encoded string cannot bypass
    # the same guard used for provider bytes.
    if PRIVATE_MARKER.search(json.dumps(value, ensure_ascii=False)):
        raise PrivacyError()
