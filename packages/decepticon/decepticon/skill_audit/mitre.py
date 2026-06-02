"""MITRE ATT&CK / ATLAS ID format validation.

Phase 1a only loads ATT&CK Enterprise into the graph, but the corpus
contains IDs from three additional namespaces (Mobile, ICS, ATLAS) that
must be preserved as raw frontmatter for later promotion. The classifier
distinguishes accepted formats from junk so the validator can emit one
of:

- ``R-bad-mitre-format`` (truly malformed — fail)
- accepted, will become an IMPLEMENTS edge in Phase 1a (Enterprise/Mobile)
- accepted, will be preserved as ``mitre_attack_raw`` only (ICS/ATLAS)
"""

from __future__ import annotations

import enum
import re
from typing import Any

# Enterprise and Mobile share namespace (T1xxx). Distinguishing them
# requires the actual STIX bundle and is the Phase 1a importer's job;
# the validator only checks format.
_ENT_OR_MOBILE_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_ICS_RE = re.compile(r"^T0\d{3}(?:\.\d{3})?$")
_ATLAS_RE = re.compile(r"^AML\.T\d{4}(?:\.\d{3})?$")


class MitreMatrix(enum.Enum):
    """Which matrix an ID belongs to (format-level classification)."""

    ENTERPRISE_OR_MOBILE = "enterprise_or_mobile"
    ICS = "ics"
    ATLAS = "atlas"


def classify_mitre_id(raw: str) -> MitreMatrix | None:
    """Return the matrix of a MITRE ID, or ``None`` if the format is invalid."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    # ICS namespace is more specific than Enterprise — check first to
    # avoid the more permissive T1xxx regex matching T0xxx.
    if _ICS_RE.match(candidate):
        return MitreMatrix.ICS
    if _ENT_OR_MOBILE_RE.match(candidate):
        return MitreMatrix.ENTERPRISE_OR_MOBILE
    if _ATLAS_RE.match(candidate):
        return MitreMatrix.ATLAS
    return None


def coerce_mitre_list(raw: Any) -> list[str]:
    """Normalize a frontmatter mitre_attack value into a list of strings.

    Accepts a YAML list, a comma-separated string, or ``None``.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        return [token.strip() for token in raw.split(",") if token.strip()]
    return [str(raw).strip()] if str(raw).strip() else []
