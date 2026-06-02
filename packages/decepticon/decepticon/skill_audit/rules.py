"""Composed validation rules.

Each rule corresponds to one entry in the violation report. The CLI
prints rules with their stable string ID so authors can grep for fixes.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from decepticon.skill_audit.aliases import resolve_subdomain
from decepticon.skill_audit.canonical import load_canonical_subdomains
from decepticon.skill_audit.frontmatter import (
    FrontmatterParseError,
    parse_frontmatter,
)
from decepticon.skill_audit.mitre import classify_mitre_id, coerce_mitre_list
from decepticon.skill_audit.path_kind import is_offensive_path

_REQUIRED_TOP_LEVEL = ("name", "description")
_REQUIRED_METADATA = ("subdomain", "when_to_use")


class RuleId(enum.Enum):
    """Stable identifier for each validation rule."""

    PARSE_ERROR = "R-parse-error"
    MISSING_REQUIRED = "R-missing-required"
    BAD_SUBDOMAIN = "R-bad-subdomain"
    BAD_MITRE_FORMAT = "R-bad-mitre-format"
    NO_ATTRIBUTION = "R-no-attribution"
    DUPLICATE_NAME = "R-duplicate-name"


@dataclass(frozen=True)
class Violation:
    """A single failed rule against one SKILL.md file."""

    path: str
    rule_id: RuleId
    detail: str


def validate_skill_file(path: str, text: str) -> list[Violation]:
    """Run every rule against a single SKILL.md and return all violations."""
    try:
        meta, _body = parse_frontmatter(text)
    except FrontmatterParseError as exc:
        return [Violation(path, RuleId.PARSE_ERROR, str(exc))]

    violations: list[Violation] = []
    violations.extend(_check_required(path, meta))
    violations.extend(_check_subdomain(path, meta))
    violations.extend(_check_mitre(path, meta))
    violations.extend(_check_attribution(path, meta))
    return violations


def _check_required(path: str, meta: dict[str, Any]) -> list[Violation]:
    out: list[Violation] = []
    for key in _REQUIRED_TOP_LEVEL:
        if not _truthy_string(meta.get(key)):
            out.append(
                Violation(
                    path,
                    RuleId.MISSING_REQUIRED,
                    f"top-level field {key!r} is missing or empty",
                )
            )
    metadata = meta.get("metadata") or {}
    if not isinstance(metadata, dict):
        out.append(
            Violation(
                path,
                RuleId.MISSING_REQUIRED,
                "metadata block must be a YAML mapping",
            )
        )
        return out
    for key in _REQUIRED_METADATA:
        if not _truthy_string(metadata.get(key)):
            out.append(
                Violation(
                    path,
                    RuleId.MISSING_REQUIRED,
                    f"metadata.{key} is missing or empty",
                )
            )
    return out


def _check_subdomain(path: str, meta: dict[str, Any]) -> list[Violation]:
    metadata = meta.get("metadata") or {}
    raw = metadata.get("subdomain") if isinstance(metadata, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return []  # already reported by R-missing-required
    canonical = resolve_subdomain(raw)
    if canonical not in load_canonical_subdomains():
        return [
            Violation(
                path,
                RuleId.BAD_SUBDOMAIN,
                f"subdomain {raw!r} is not canonical and not an alias",
            )
        ]
    return []


def _check_mitre(path: str, meta: dict[str, Any]) -> list[Violation]:
    metadata = meta.get("metadata") or {}
    raw = metadata.get("mitre_attack") if isinstance(metadata, dict) else None
    entries = coerce_mitre_list(raw)
    out: list[Violation] = []
    for entry in entries:
        if classify_mitre_id(entry) is None:
            out.append(
                Violation(
                    path,
                    RuleId.BAD_MITRE_FORMAT,
                    f"mitre_attack entry {entry!r} matches no accepted format",
                )
            )
    return out


def _check_attribution(path: str, meta: dict[str, Any]) -> list[Violation]:
    if not is_offensive_path(path):
        return []
    metadata = meta.get("metadata") or {}
    if not isinstance(metadata, dict):
        return []
    has_mitre = bool(coerce_mitre_list(metadata.get("mitre_attack")))
    has_aatmf = bool(coerce_mitre_list(metadata.get("aatmf_tactic")))
    has_upstream = _truthy_string(metadata.get("upstream_ref"))
    if has_mitre or has_aatmf or has_upstream:
        return []
    return [
        Violation(
            path,
            RuleId.NO_ATTRIBUTION,
            "offensive skill has no mitre_attack, aatmf_tactic, or upstream_ref",
        )
    ]


def _truthy_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
