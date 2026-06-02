"""Canonical subdomain list — loaded from a packaged YAML asset.

The list is the source of truth for ``metadata.subdomain`` values. The
alias map (``aliases.py``) translates legacy forms into a canonical
value; the canonical loader is intentionally the only path that knows
which values are accepted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import yaml

SUBDOMAIN_LIST_PATH: Final[Path] = Path(__file__).with_name("subdomains.yaml")


def load_canonical_subdomains() -> frozenset[str]:
    """Return the canonical subdomain set.

    Reads the packaged ``subdomains.yaml`` once per call (no caching: the
    list is small and this function is called at validator startup, not
    per-skill).
    """
    raw = yaml.safe_load(SUBDOMAIN_LIST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "canonical" not in raw:
        raise ValueError(
            f"{SUBDOMAIN_LIST_PATH} must be a YAML mapping with a top-level 'canonical' key"
        )
    entries = raw["canonical"]
    if not isinstance(entries, list):
        raise ValueError(f"{SUBDOMAIN_LIST_PATH}: 'canonical' must be a list of strings")
    return frozenset(str(entry) for entry in entries)
