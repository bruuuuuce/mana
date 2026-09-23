#!/usr/bin/env python3
"""Fixed local fixture consumer: production exposes no framework selector."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ctx09c_test_consumer", REPO / "scripts/lib/context-shadow-consumer.py")
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)
try:
    status, output, _ = consumer.consume(sys.stdin.buffer.read(consumer.shared.MAX_BYTES + 1), "v2",
        Path(sys.argv[1]), framework_root=REPO / "tests/fixtures/context-runtime/ctx06a-framework")
except (consumer.privacy.PrivacyError, consumer.shared.Error, consumer.pipeline.runtime.ContractError):
    print("ERROR: canonical shadow consumer rejected", file=sys.stderr)
    raise SystemExit(2)
sys.stdout.buffer.write(output)
raise SystemExit(status)
