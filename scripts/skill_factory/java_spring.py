"""The sole production adapter: curated Java/Spring contract plus Maven evidence."""

import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from .contracts import FactoryError

FUTURE = [
    "transactional-method-identification",
    "spring-propagation",
    "reused-independent-nested-transactions",
    "transaction-boundaries",
    "sequence-diagram-overlapping-regions",
    "static-uncertainty-reporting",
]


class JavaSpringAdapter:
    skill_id = "java-spring-transaction-analysis"
    request = "transaction-analysis"
    evidence_names = frozenset({"pom.xml"})
    evidence_suffixes = frozenset({".java"})
    template = (
        Path(__file__).resolve().parents[2]
        / "templates/skill-factory/java-spring-transaction-analysis.md"
    )

    def evidence(self, files: dict[str, bytes]) -> list[dict]:
        result = []
        for relative, raw in sorted(files.items()):
            if Path(relative).name != "pom.xml":
                continue
            # No DTDs/entities, parent resolution, profiles, plugins or build execution.
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise FactoryError(f"DTD/entity declaration forbidden: {relative}")
            try:
                pom = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise FactoryError(f"malformed Maven descriptor: {relative}") from exc
            if pom.tag not in {"project", "{http://maven.apache.org/POM/4.0.0}project"}:
                raise FactoryError(f"unsupported Maven root: {relative}")
            ns = (
                "{http://maven.apache.org/POM/4.0.0}" if pom.tag.startswith("{") else ""
            )
            dependencies = []
            for dep in pom.findall(f"{ns}dependencies/{ns}dependency"):
                group = (dep.findtext(f"{ns}groupId") or "").strip()
                artifact = (dep.findtext(f"{ns}artifactId") or "").strip()
                scope = (dep.findtext(f"{ns}scope") or "compile").strip()
                if scope not in {"compile", "runtime", "provided"}:
                    continue
                if (
                    group == "org.springframework" and artifact.startswith("spring-")
                ) or (
                    group == "org.springframework.boot"
                    and artifact.startswith("spring-boot-")
                ):
                    if not all(c.isalnum() or c in "-." for c in artifact):
                        continue
                    dependencies.append(f"{group}:{artifact}")
            source_prefix = (Path(relative).parent / "src/main/java").as_posix() + "/"
            sources = [
                p
                for p, data in sorted(files.items())
                if p.startswith(source_prefix) and p.endswith(".java") and data.strip()
            ]
            if dependencies and sources:
                result.append(
                    {
                        "path": relative,
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "kind": "maven-direct-dependency",
                        "declarations": sorted(set(dependencies)),
                    }
                )
                source = sources[0]
                result.append(
                    {
                        "path": source,
                        "sha256": hashlib.sha256(files[source]).hexdigest(),
                        "kind": "java-source",
                    }
                )
        if not result:
            raise FactoryError(
                "unsupported or unproven technology: need a direct Spring dependency and Java source in the same conventional Maven module"
            )
        return result

    def specialize(self, files: dict[str, bytes]) -> dict:
        facts = self.evidence(files)
        return {
            "supportedTechnologies": ["java", "spring", "maven"],
            "evidence": facts,
            "technologyClaim": "declared dependency and source presence only; resolved versions and runtime use unknown",
            "offeredCapabilities": ["reviewable-future-analysis-contract"],
            "futureCapabilities": [
                {"id": item, "status": "not_implemented"} for item in FUTURE
            ],
            "usableEvidence": [
                "java-source",
                "maven-direct-dependency",
                "explicit-project-configuration",
                "approved-runtime-evidence",
            ],
            "applicability": [
                "explicit transaction-analysis request",
                "Java source and direct Spring dependency in the same Maven module",
                "human approval and implemented analyzers required before future analysis",
            ],
            "requiredTools": [
                {"id": "read_files", "status": "framework_declared"},
                {"id": "code_search", "status": "framework_declared"},
                {"id": "transaction-analyzer", "status": "not_implemented"},
            ],
            "knowledgeReferences": [
                "docs/policies/verification-execution-policy.md",
                "docs/standards/agent-skill-output-standard.md",
                "templates/skill-factory/java-spring-transaction-analysis.md",
            ],
            "limits": [
                "No transaction analysis or diagram generation",
                "No dependency resolution or runtime claims",
                "No Gradle, inherited-only dependencies, profiles or nonstandard source roots",
                "No promotion, registration, approval recording or execution API",
            ],
            "verificationCriteria": [
                "recompute source evidence hashes",
                "validate Mana skill metadata",
                "reject changed candidate content",
                "require pending approval and generated untrusted non-executable state",
                "require future capabilities to remain not_implemented",
            ],
        }
