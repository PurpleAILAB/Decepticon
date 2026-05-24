"""Active Directory / Windows offensive tooling.

- ``bloodhound`` — import BloodHound JSON dumps into the KnowledgeGraph
                   so the chain planner can walk AD attack paths alongside
                   web/cloud findings.
- ``kerberos``   — parse Kerberos ticket blobs (Base64 .kirbi / hashcat
                   krb5tgs format), classify Kerberoastable users,
                   AS-REP roastable users.
- ``adcs``       — ADCS ESC1-ESC15 template scoring (offline analyser).
- ``dpapi``      — DPAPI blob triage heuristics.
- ``dcsync``     — Indicator checker for DCSync-capable principals.
"""

from __future__ import annotations

from decepticon.tools.ad.adcs import ADCSFinding, analyze_adcs_templates
from decepticon.tools.ad.bloodhound import ingest_bloodhound_zip, merge_bloodhound_json
from decepticon.tools.ad.dcsync import dcsync_candidates
from decepticon.tools.ad.kerberos import KerberosTicket, classify_hashcat_hash, parse_ticket

__all__ = [
    "ADCSFinding",
    "KerberosTicket",
    "analyze_adcs_templates",
    "classify_hashcat_hash",
    "dcsync_candidates",
    "ingest_bloodhound_zip",
    "merge_bloodhound_json",
    "parse_ticket",
]
