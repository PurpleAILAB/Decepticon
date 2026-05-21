"""Offline MITRE ATT&CK catalog — models, ID normalization, bundled loader.

The catalog is a pruned, pre-flattened view of ATT&CK Enterprise bundled as
JSON inside this package (``data/attack_enterprise.json``). It is loaded via
``importlib.resources`` with zero network access. Regenerate the bundled
dataset with ``scripts/build_attack_dataset.py``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel, Field, model_validator

# ── ID normalization ─────────────────────────────────────────────────────

_TECHNIQUE_RE = re.compile(r"^T\d{4}(\.\d{3})?$")
_TACTIC_RE = re.compile(r"^TA\d{4}$")

_DATA_FILE = "data/attack_enterprise.json"


def normalize(raw: str | None) -> str | None:
    """Canonicalize a single ATT&CK ID token.

    Accepts technique IDs (``T1190``, ``T1558.003``) and tactic IDs
    (``TA0003``) in any case, with surrounding whitespace. Returns the
    canonical upper-case form, or ``None`` if the token is not a
    syntactically valid ATT&CK ID.
    """
    if not isinstance(raw, str):
        return None
    token = raw.strip().upper()
    if not token:
        return None
    if _TECHNIQUE_RE.match(token) or _TACTIC_RE.match(token):
        return token
    return None


def parse_ids(value: object) -> list[str]:
    """Normalize an ATT&CK ID field (a list or comma/space string) to a
    deduplicated list of canonical IDs. Invalid tokens are dropped.

    Used for skill frontmatter ``mitre_attack`` and node ``mitre`` props.
    """
    raw: list[str]
    if isinstance(value, list):
        raw = [str(v) for v in value]
    elif isinstance(value, str):
        raw = value.replace(",", " ").split()
    else:
        raw = []
    out: list[str] = []
    for token in raw:
        norm = normalize(token)
        if norm is not None and norm not in out:
            out.append(norm)
    return out


def is_technique_id(token: str) -> bool:
    """True if ``token`` is a canonical technique or sub-technique ID."""
    return bool(_TECHNIQUE_RE.match(token))


def is_tactic_id(token: str) -> bool:
    """True if ``token`` is a canonical tactic ID."""
    return bool(_TACTIC_RE.match(token))


# ── Models ───────────────────────────────────────────────────────────────


class AttackTactic(BaseModel):
    """A MITRE ATT&CK tactic (the "why" — an adversary's tactical goal)."""

    id: str = Field(description="Tactic ID, e.g. TA0043")
    name: str = Field(description="Display name, e.g. Reconnaissance")
    shortname: str = Field(
        description="ATT&CK x-mitre-shortname, e.g. reconnaissance — referenced by techniques"
    )
    description: str = ""


class AttackTechnique(BaseModel):
    """A MITRE ATT&CK technique or sub-technique (the "how")."""

    id: str = Field(description="Technique ID, e.g. T1190 or T1558.003")
    name: str
    tactics: list[str] = Field(
        default_factory=list, description="Tactic shortnames this technique belongs to"
    )
    description: str = ""
    is_subtechnique: bool = False
    parent: str | None = Field(
        default=None, description="Parent technique ID for sub-techniques, e.g. T1558"
    )
    url: str = ""


class AttackCatalog(BaseModel):
    """A complete, indexed ATT&CK catalog loaded from the bundled dataset."""

    version: str
    tactics: list[AttackTactic] = Field(default_factory=list)
    techniques: list[AttackTechnique] = Field(default_factory=list)

    @model_validator(mode="after")
    def _build_indexes(self) -> AttackCatalog:
        by_id: dict[str, AttackTechnique] = {}
        for tech in self.techniques:
            if tech.id in by_id:
                raise ValueError(f"duplicate technique ID in catalog: {tech.id}")
            by_id[tech.id] = tech
        tactic_by_id: dict[str, AttackTactic] = {}
        tactic_by_shortname: dict[str, AttackTactic] = {}
        for tac in self.tactics:
            tactic_by_id[tac.id] = tac
            tactic_by_shortname[tac.shortname] = tac
        # Private indexes — not part of the serialized model.
        object.__setattr__(self, "_by_id", by_id)
        object.__setattr__(self, "_tactic_by_id", tactic_by_id)
        object.__setattr__(self, "_tactic_by_shortname", tactic_by_shortname)
        return self

    def technique(self, technique_id: str) -> AttackTechnique | None:
        """Look up a technique by ID (input is normalized first)."""
        norm = normalize(technique_id)
        if norm is None:
            return None
        return self._by_id.get(norm)  # type: ignore[attr-defined]

    def tactic(self, tactic_id: str) -> AttackTactic | None:
        """Look up a tactic by ID (input is normalized first)."""
        norm = normalize(tactic_id)
        if norm is None:
            return None
        return self._tactic_by_id.get(norm)  # type: ignore[attr-defined]

    def tactic_by_shortname(self, shortname: str) -> AttackTactic | None:
        """Look up a tactic by its ATT&CK shortname (e.g. ``initial-access``)."""
        return self._tactic_by_shortname.get(shortname)  # type: ignore[attr-defined]

    def tactic_ids_for(self, technique_id: str) -> list[str]:
        """Return the sorted tactic IDs a technique belongs to (empty if unknown)."""
        tech = self.technique(technique_id)
        if tech is None:
            return []
        ids: set[str] = set()
        for shortname in tech.tactics:
            tac = self.tactic_by_shortname(shortname)
            if tac is not None:
                ids.add(tac.id)
        return sorted(ids)


# ── Parsing / loading ────────────────────────────────────────────────────


def parse_catalog(data: dict) -> AttackCatalog:
    """Build an :class:`AttackCatalog` from a raw dataset dict.

    Raises ``ValueError`` (via Pydantic) on malformed data or duplicate
    technique IDs.
    """
    return AttackCatalog.model_validate(data)


@lru_cache(maxsize=1)
def load_attack_catalog() -> AttackCatalog:
    """Load the bundled ATT&CK Enterprise catalog (cached, offline)."""
    raw = resources.files("decepticon.tools.research.attack").joinpath(_DATA_FILE)
    data = json.loads(raw.read_text(encoding="utf-8"))
    return parse_catalog(data)


__all__ = [
    "AttackCatalog",
    "AttackTactic",
    "AttackTechnique",
    "is_tactic_id",
    "is_technique_id",
    "load_attack_catalog",
    "normalize",
    "parse_catalog",
    "parse_ids",
]
