"""LangChain @tool wrappers for the Active Directory package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from langchain_core.tools import tool

from decepticon.tools.ad.adcs import analyze_adcs_templates
from decepticon.tools.ad.bloodhound import ingest_bloodhound_zip, merge_bloodhound_json
from decepticon.tools.ad.dcsync import dcsync_candidates
from decepticon.tools.ad.delegation import analyze_delegation
from decepticon.tools.ad.gpo import analyze_gpo_abuse
from decepticon.tools.ad.kerberos import classify_hashcat_hash, parse_ticket
from decepticon.tools.ad.shadow_creds import analyze_shadow_credentials
from decepticon.tools.research._state import _load, _save


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def bh_ingest_zip(path: str) -> str:
    """Merge a BloodHound collector ZIP into the KnowledgeGraph."""
    graph, kg_path = _load()
    try:
        stats = ingest_bloodhound_zip(path, graph)
    except (OSError, BadZipFile) as exc:
        return _json({"error": str(exc)})
    _save(graph, kg_path)
    return _json({"import": stats.to_dict(), "stats": graph.stats()})


@tool
def bh_ingest_json(path: str, type_hint: str = "") -> str:
    """Merge a single BloodHound JSON file into the KnowledgeGraph."""
    graph, kg_path = _load()
    try:
        data = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _json({"error": str(exc)})
    try:
        stats = merge_bloodhound_json(data, graph, type_hint=type_hint or None)
    except (ValueError, json.JSONDecodeError) as exc:
        return _json({"error": str(exc)})
    _save(graph, kg_path)
    return _json({"import": stats.to_dict(), "stats": graph.stats()})


@tool
def dcsync_check() -> str:
    """List principals with DCSync rights from the current KnowledgeGraph.

    Run after ``bh_ingest_*``.
    """
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
    """Audit a Certipy find --json output for ESC1-ESC8 template weaknesses."""
    try:
        data = json.loads(certipy_json)
    except json.JSONDecodeError as e:
        return _json({"error": f"certipy output must be JSON: {e}"})
    findings = analyze_adcs_templates(data)
    return _json([f.to_dict() for f in findings])


@tool
def delegation_audit() -> str:
    """Analyze delegation configurations in the knowledge graph.

    Identifies constrained delegation, unconstrained delegation, and
    resource-based constrained delegation (RBCD) attack paths.
    """
    graph, path = _load()
    findings = analyze_delegation(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


@tool
def gpo_audit() -> str:
    """Analyze GPO-based attack paths in the knowledge graph.

    Identifies GPOs with weak ACLs that allow lateral movement or
    persistence via Group Policy modification.
    """
    graph, path = _load()
    findings = analyze_gpo_abuse(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


@tool
def shadow_creds_audit() -> str:
    """Detect Shadow Credentials attack paths in the knowledge graph.

    Identifies principals with write access to msDS-KeyCredentialLink
    on target accounts.
    """
    graph, path = _load()
    findings = analyze_shadow_credentials(graph)
    _save(graph, path)
    return _json({"findings": [f.to_dict() for f in findings], "count": len(findings)})


AD_TOOLS = [
    bh_ingest_zip,
    bh_ingest_json,
    dcsync_check,
    kerberos_classify,
    adcs_audit,
    delegation_audit,
    gpo_audit,
    shadow_creds_audit,
]
