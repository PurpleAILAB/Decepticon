"""Subdomain alias resolution.

This is intentionally a small, explicit map. It absorbs corpus drift
without granting authors permission to invent new spellings — anything
not in this map is treated as the author's own value and validated
against the canonical list directly.
"""

from __future__ import annotations

from typing import Final

# Alias → canonical. Keep this minimal and reviewed.
SUBDOMAIN_ALIASES: Final[dict[str, str]] = {
    "reverser": "reverse-engineering",
    "re": "reverse-engineering",
    "contracts": "smart-contracts",
    "cloud-native": "cloud",
    "ad": "active-directory",
    # Abbreviations and spelling variants.
    "phish": "phishing",
    "ics": "ics-ot",
    "c2": "command-and-control",
    "post-exploitation": "post-exploit",
    "supplychain": "supply-chain",
    # Web-exploitation sub-categories collapsed into the parent phase.
    "api": "web-exploitation",
    "injection": "web-exploitation",
    "client-side": "web-exploitation",
    "authentication": "web-exploitation",
    "authorization": "web-exploitation",
    "redirect": "web-exploitation",
    "cache": "web-exploitation",
    # Specialized values aliased to the closest canonical phase.
    "infrastructure": "command-and-control",
    "cryptanalysis": "credential-access",
    "verification": "analyst",
    "deconfliction": "orchestration",
}


def resolve_subdomain(raw: str) -> str:
    """Translate a possibly-aliased subdomain into its canonical form.

    Case-insensitive. Unknown values pass through unchanged so the
    validator can flag them with a precise error.
    """
    key = raw.strip().lower()
    return SUBDOMAIN_ALIASES.get(key, key)
