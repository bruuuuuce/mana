"""Minimal independent regression: an absent holder is UNKNOWN, not no-cycle.

Run from any directory. Exit 1 means the reviewed defect is reproduced.
Only in-memory copies of the versioned A/C sidecars are changed.
"""

import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_factory.transactions.wait_dependencies import build_report  # noqa: E402
from skill_factory.transactions.wait_validation import validate_report  # noqa: E402


def main():
    results = []
    for case in ("A", "C"):
        base = ROOT / "docs/examples/transaction-01-t02-s02" / case
        sidecar = json.loads((base / "scenario.json").read_bytes())
        raw = {
            item["id"]: (base / "inputs" / (item["id"] + ".json")).read_bytes()
            for item in sidecar["inputs"]
        }
        # The only mutation: omit the cut's acquisition/retention hypotheses.
        sidecar["cuts"][0]["holdings"] = []
        report = build_report(raw, sidecar)
        accepted = validate_report(report, raw)
        actual = report["assessment"]["result"]
        results.append(
            {
                "case": case,
                "mutation": "cuts[0].holdings = []",
                "expected": "UNKNOWN",
                "actual": actual,
                "status": "PASS" if actual == "UNKNOWN" else "FAIL",
                "validatorAccepted": accepted,
                "coverage": report["coverage"]["status"],
                "globalRiskAbsence": report["coverage"]["globalRiskAbsence"],
                "unknowns": report["unknowns"],
                "assessment": report["assessment"],
                "dbEdges": len(report["databaseGraph"]["edges"]),
                "appEdges": len(report["applicationGraph"]["edges"]),
            }
        )
    print(json.dumps(results, indent=2))
    return int(any(result["status"] == "FAIL" for result in results))


if __name__ == "__main__":
    sys.exit(main())
