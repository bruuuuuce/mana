"""Minimal trusted adapter boundary; adapters never own output or trust state."""

from pathlib import Path
from typing import Protocol


class FactoryError(ValueError):
    pass


DOMAIN_FIELDS = frozenset(
    {
        "supportedTechnologies",
        "evidence",
        "technologyClaim",
        "offeredCapabilities",
        "futureCapabilities",
        "usableEvidence",
        "applicability",
        "requiredTools",
        "knowledgeReferences",
        "limits",
        "verificationCriteria",
    }
)


class SkillAdapter(Protocol):
    skill_id: str
    request: str
    template: Path
    evidence_names: frozenset[str]
    evidence_suffixes: frozenset[str]

    def specialize(self, files: dict[str, bytes]) -> dict:
        """Return exactly DOMAIN_FIELDS, including applicability evidence or a rejection."""
        ...
