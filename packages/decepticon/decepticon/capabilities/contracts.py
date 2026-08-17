"""Machine-checkable contracts for specialized research capabilities.

A skill remains the operator-facing procedure.  A capability contract adds the
parts that must be testable by automation: permitted environment, tools,
evidence, verification, negative control, and evaluation surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from decepticon.skill_audit.frontmatter import FrontmatterParseError, parse_frontmatter


class CapabilityLane(StrEnum):
    """Specialist lanes with separate evidence and lab requirements."""

    WEB = "web"
    WEB3 = "web3"
    REVERSE_ENGINEERING = "reverse-engineering"
    ACTIVE_DIRECTORY = "active-directory"
    WINDOWS_INTERNALS = "windows-internals"
    GAME_SECURITY = "game-security"


class ScopeClass(StrEnum):
    """Only environments suitable for authorized research are contractable."""

    AUTHORIZED_TARGET = "authorized-target"
    ISOLATED_LAB = "isolated-lab"


class CapabilityContract(BaseModel):
    """Required operational invariants for one specialist skill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lane: CapabilityLane
    scope: ScopeClass
    environment: list[str] = Field(min_length=1)
    required_tools: list[str] = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    verification: str = Field(min_length=1)
    negative_control: str = Field(min_length=1)
    scorecard: list[str] = Field(min_length=1)
    benchmark: str | None = None

    @field_validator("environment", "required_tools", "evidence", "scorecard")
    @classmethod
    def _require_unique_nonempty_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
        if len(cleaned) != len(values):
            raise ValueError("entries must be non-empty strings")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("entries must be unique")
        return cleaned


@dataclass(frozen=True)
class ContractIssue:
    """A contract parse error attached to the owning skill file."""

    path: str
    detail: str


@dataclass(frozen=True)
class DiscoveredContract:
    """A validated contract and the skill that declares it."""

    path: Path
    skill_name: str
    contract: CapabilityContract


def validate_contract_metadata(metadata: Any) -> list[str]:
    """Return schema violations for an optional ``capability_contract`` block."""
    if not isinstance(metadata, dict) or "capability_contract" not in metadata:
        return []
    raw_contract = metadata["capability_contract"]
    if not isinstance(raw_contract, dict):
        return ["metadata.capability_contract must be a YAML mapping"]
    try:
        CapabilityContract.model_validate(raw_contract)
    except ValidationError as exc:
        return [
            "metadata.capability_contract."
            + ".".join(str(part) for part in error["loc"])
            + ": "
            + error["msg"]
            for error in exc.errors()
        ]
    return []


def discover_contracts(skills_root: Path) -> tuple[list[DiscoveredContract], list[ContractIssue]]:
    """Load every declared capability contract under ``skills_root``.

    Legacy skills without a contract remain loadable.  A skill that opts into a
    contract is validated strictly, allowing incremental migration without a
    second unsupported metadata convention.
    """
    contracts: list[DiscoveredContract] = []
    issues: list[ContractIssue] = []
    for skill_path in sorted(skills_root.rglob("SKILL.md")):
        try:
            frontmatter, _ = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
        except FrontmatterParseError as exc:
            issues.append(ContractIssue(str(skill_path), str(exc)))
            continue
        metadata = frontmatter.get("metadata")
        details = validate_contract_metadata(metadata)
        for detail in details:
            issues.append(ContractIssue(str(skill_path), detail))
        if details or not isinstance(metadata, dict) or "capability_contract" not in metadata:
            continue
        contract = CapabilityContract.model_validate(metadata["capability_contract"])
        contracts.append(
            DiscoveredContract(
                path=skill_path,
                skill_name=str(frontmatter.get("name", "")).strip(),
                contract=contract,
            )
        )
    return contracts, issues
