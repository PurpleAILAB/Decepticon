"""LangChain @tool wrappers for the Active Directory package.

Deprecation notice (ADR-0005, 2026-06-05).  The in-house BloodHound
ingest + ADCS post-process tools below (``bh_ingest_zip``,
``bh_ingest_json``, ``adcs_post_process``, ``dcsync_check``,
``delegation_audit``, ``gpo_audit``, ``shadow_creds_audit``,
``adcs_audit``) are deprecated in favour of the BHCE-backed
``bhce_*`` surface in :mod:`decepticon.tools.ad.bh_tools`.  They emit
``DeprecationWarning`` on every invocation, remain functional for
one minor cycle, then move to ``decepticon.compat``, then are
removed.  ``kerberos_classify`` stays — it parses local hash /
ticket blobs with no BHCE equivalent.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from langchain_core.tools import tool

from decepticon.tools.ad.adcs import analyze_adcs_templates
from decepticon.tools.ad.adcs_post import synthesise_adcs_post as _synthesise_adcs_post
from decepticon.tools.ad.bh_tools import BHCE_TOOLS
from decepticon.tools.ad.bloodhound import (
    ingest_bloodhound_zip as _ingest_bloodhound_zip_impl,
)
from decepticon.tools.ad.bloodhound import (
    merge_bloodhound_json as _merge_bloodhound_json_impl,
)
from decepticon.tools.ad.dcsync import dcsync_candidates
from decepticon.tools.ad.delegation import analyze_delegation
from decepticon.tools.ad.gpo import analyze_gpo_abuse
from decepticon.tools.ad.kerberos import classify_hashcat_hash, parse_ticket
from decepticon.tools.ad.shadow_creds import analyze_shadow_credentials
from decepticon.tools.research._engagement_scope import _LEGACY_ENGAGEMENT_LABEL
from decepticon.tools.research._state import _load, _save
from decepticon_core.utils.engagement_scope import get_active_engagement

_DEPRECATION_MESSAGE = (
    "{name} is deprecated under ADR-0005; use the BHCE-backed bhce_* "
    "tools (bhce_status / bhce_cypher / bhce_ingest_zip) instead. "
    "This tool will be removed one minor cycle after the cutover."
)


def _warn_deprecated(name: str) -> None:
    warnings.warn(
        _DEPRECATION_MESSAGE.format(name=name),
        DeprecationWarning,
        stacklevel=3,
    )


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _resolve_engagement() -> str:
    """Engagement label for BloodHound ingest writes.

    Falls back to the shared ``_LEGACY_ENGAGEMENT_LABEL`` when the
    ``EngagementContextMiddleware`` contextvar is unset — matches the
    behaviour of the legacy ``_state`` shim used by the read-mostly AD
    analysis tools below (``dcsync_check`` / ``delegation_audit`` /
    ``gpo_audit`` / ``shadow_creds_audit``).
    """
    return get_active_engagement() or _LEGACY_ENGAGEMENT_LABEL


@tool
def bh_ingest_zip(path: str) -> str:
    """Deprecated. Use ``bhce_ingest_zip`` instead.

    Legacy in-house BloodHound ZIP ingest into KGStore. The new
    ``bhce_ingest_zip`` tool drives BHCE's official 3-step
    file-upload + analysis pipeline instead, and BHCE derives every
    ESC* / DCSync / GoldenCert edge for us.
    """
    _warn_deprecated("bh_ingest_zip")
    engagement = _resolve_engagement()
    try:
        stats = _ingest_bloodhound_zip_impl(path, engagement=engagement)
    except (OSError, BadZipFile) as exc:
        return _json({"error": str(exc)})
    return _json({"import": stats.to_dict()})


@tool
def bh_ingest_json(path: str, type_hint: str = "") -> str:
    """Deprecated. Pack the JSON into a ZIP and call ``bhce_ingest_zip``.

    BHCE's file-upload accepts JSON directly, but our agent surface
    uniformly funnels through the ZIP path so ingest semantics stay
    one-shape per call.
    """
    _warn_deprecated("bh_ingest_json")
    engagement = _resolve_engagement()
    try:
        data = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _json({"error": str(exc)})
    try:
        stats = _merge_bloodhound_json_impl(
            data, engagement=engagement, type_hint=type_hint or None
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return _json({"error": str(exc)})
    return _json({"import": stats.to_dict()})


@tool
def dcsync_check() -> str:
    """Deprecated. Use ``bhce_cypher`` with the DCSync starter query.

    Reference query (lives in the ``bloodhound-bhce`` skill):
    ``MATCH (n)-[:DCSync]->(d:Domain) RETURN n.name, labels(n), d.name``
    """
    _warn_deprecated("dcsync_check")
    graph, _ = _load()
    try:
        hits = dcsync_candidates(graph)
    except Exception as exc:
        return _json({"error": str(exc)})
    return _json(
        {
            "count": len(hits),
            "candidates": [
                {"id": node_id, "label": label, "target_domain": domain}
                for node_id, label, domain in hits
            ],
        }
    )


@tool
def kerberos_classify(hash_or_ticket: str) -> str:
    """Classify a Kerberos hash or .kirbi ticket and recommend a hashcat mode.

    Accepts ``$krb5tgs$...``, ``$krb5asrep$...``, and base64 .kirbi blobs.
    """
    try:
        if hash_or_ticket.startswith("$krb5"):
            t = classify_hashcat_hash(hash_or_ticket)
        else:
            t = parse_ticket(hash_or_ticket)
    except Exception as exc:
        return _json({"error": str(exc)})
    return _json(t.to_dict())


@tool
def adcs_audit(certipy_json: str) -> str:
    """Deprecated. Prefer ``bhce_cypher`` over BHCE-ingested ADCS data.

    Certipy JSON parsing remains available for runs where BHCE wasn't
    used, but BHCE's PostProcessedRelationships covers ESC1-13 +
    GoldenCert + TrustedForNTAuth more comprehensively than this
    offline analyser.
    """
    _warn_deprecated("adcs_audit")
    try:
        data = json.loads(certipy_json)
    except json.JSONDecodeError as e:
        return _json({"error": f"certipy output must be JSON: {e}"})
    findings = analyze_adcs_templates(data)
    return _json([f.to_dict() for f in findings])


@tool
def delegation_audit() -> str:
    """Deprecated. Use ``bhce_cypher`` for delegation paths.

    Reference: ``MATCH (n)-[:AllowedToDelegate|AllowedToAct*1..]->(t)
    RETURN n.name, labels(n), t.name`` covers constrained,
    unconstrained, and RBCD.
    """
    _warn_deprecated("delegation_audit")
    graph, path = _load()
    findings = analyze_delegation(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


@tool
def gpo_audit() -> str:
    """Deprecated. Use ``bhce_cypher`` for GPO paths.

    Reference: ``MATCH (n)-[:GenericAll|WriteDacl|WriteOwner]->(g:GPO)
    MATCH (g)-[:GPLink]->(t) RETURN n.name, g.name, t.name``.
    """
    _warn_deprecated("gpo_audit")
    graph, path = _load()
    findings = analyze_gpo_abuse(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


@tool
def shadow_creds_audit() -> str:
    """Deprecated. Use ``bhce_cypher`` with the AddKeyCredentialLink edge.

    Reference: ``MATCH (n)-[:AddKeyCredentialLink]->(t)
    RETURN n.name, t.name, labels(t)``.
    """
    _warn_deprecated("shadow_creds_audit")
    graph, path = _load()
    findings = analyze_shadow_credentials(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


@tool
def adcs_post_process() -> str:
    """Deprecated. BHCE derives all ADCS edges itself.

    The in-house port covered a subset of BHCE's
    ``PostProcessedRelationships`` (DCSync, GoldenCert, TrustedForNTAuth);
    BHCE v9.2.2 ships the full ESC1-13 + CoerceAndRelay* family. The
    new ``bhce_ingest_zip`` waits for BHCE-side analysis to complete
    before returning, so no separate post-process call is needed.
    """
    _warn_deprecated("adcs_post_process")
    engagement = _resolve_engagement()
    stats = _synthesise_adcs_post(engagement=engagement)
    return _json({"synthesised": stats.to_dict()})


_LEGACY_AD_TOOLS = [
    bh_ingest_zip,
    bh_ingest_json,
    dcsync_check,
    kerberos_classify,
    adcs_audit,
    adcs_post_process,
    delegation_audit,
    gpo_audit,
    shadow_creds_audit,
]

# Public agent toolbox: legacy tools first (one minor cycle of
# overlap per ADR-0005), then the BHCE-backed surface that supersedes
# everything except kerberos_classify.  ``kerberos_classify`` stays
# because BHCE has no equivalent local hash/ticket parser.
AD_TOOLS = _LEGACY_AD_TOOLS + BHCE_TOOLS
