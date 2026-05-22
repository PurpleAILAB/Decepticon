"""Active Directory / Windows offensive tooling.

- ``bloodhound`` — import BloodHound JSON dumps into the KnowledgeGraph
                   so the chain planner can walk AD attack paths alongside
                   web/cloud findings.
- ``kerberos``   — parse Kerberos ticket blobs (Base64 .kirbi / hashcat
                   krb5tgs format), classify Kerberoastable users,
                   AS-REP roastable users.
- ``adcs``       — ADCS ESC1-ESC15 template scoring (offline analyser).
- ``delegation`` — Delegation attack path analysis (unconstrained, constrained, RBCD).
- ``gpo``        — GPO abuse path analysis.
- ``shadow_creds`` — Shadow Credentials (msDS-KeyCredentialLink) analysis.
- ``dpapi``      — DPAPI blob triage heuristics.
- ``dcsync``     — Indicator checker for DCSync-capable principals.

"""

from __future__ import annotations

from decepticon.tools.ad.adcs import ADCSFinding, analyze_adcs_templates
from decepticon.tools.ad.bloodhound import ingest_bloodhound_zip, merge_bloodhound_json
from decepticon.tools.ad.dcsync import dcsync_candidates
from decepticon.tools.ad.delegation import DelegationFinding, analyze_delegation
from decepticon.tools.ad.gpo import GPOFinding, analyze_gpo_abuse
from decepticon.tools.ad.kerberos import KerberosTicket, classify_hashcat_hash, parse_ticket
from decepticon.tools.ad.shadow_creds import ShadowCredsFinding, analyze_shadow_credentials

__all__ = [
    "ADCSFinding",
    "DelegationFinding",
    "GPOFinding",
    "KerberosTicket",
    "ShadowCredsFinding",
    "analyze_adcs_templates",
    "analyze_delegation",
    "analyze_gpo_abuse",
    "analyze_shadow_credentials",
    "classify_hashcat_hash",
    "dcsync_candidates",
    "ingest_bloodhound_zip",
    "merge_bloodhound_json",
    "parse_ticket",
]
