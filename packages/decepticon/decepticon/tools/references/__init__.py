"""External knowledge reference integration.

Cataloges curated third-party security research resources the agents
can reach for, and bundles a compact offline payload library so the
most common attack payloads are available even without network.

Resources catalogued:

- `hackerone-reports`      — real disclosed HackerOne bug reports
- `PayloadsAllTheThings`   — canonical payload library for every vuln class
- `the-book-of-secret-knowledge` — pentest cheat-sheet catalogue
- `pentagi`                — reference multi-agent pentest platform
- `PentestGPT`             — pentest research LLM agent
- `RedTeam-Tools`          — curated red-team tooling index
- `trickest/cve`           — continuously updated CVE PoC database
- `Penetration_Testing_POC` — PoC database for recent CVEs
- `AllAboutBugBounty`      — bug bounty writeups + methodology corpus

Each entry has (url, category, use_cases) metadata so the reference
tool can suggest the right resource for the current finding.
"""

from __future__ import annotations

from decepticon.tools.references.catalog import (
    REFERENCES,
    ReferenceEntry,
    references_by_category,
    references_for_topic,
)
from decepticon.tools.references.fetch import ReferenceCache, ensure_cached, search_cache
from decepticon.tools.references.payloads import (
    BUNDLED_PAYLOADS,
    PayloadBundle,
    payloads_by_class,
    search_payloads,
)

__all__ = [
    "BUNDLED_PAYLOADS",
    "PayloadBundle",
    "REFERENCES",
    "ReferenceCache",
    "ReferenceEntry",
    "ensure_cached",
    "payloads_by_class",
    "references_by_category",
    "references_for_topic",
    "search_cache",
    "search_payloads",
]
