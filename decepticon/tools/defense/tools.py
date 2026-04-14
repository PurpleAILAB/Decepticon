"""LangChain ``@tool`` wrappers that expose defense capabilities to the defense agent.

These tools cover the full defensive action loop:

- ``defense_read_brief``      — load a DefenseBrief from disk
- ``defense_execute_action``  — run a defensive action via the injected backend
- ``defense_log_action``      — persist a DefenseAction node to the Neo4j KG
- ``defense_verify_status``   — check whether a defense action is still active
- ``defense_generate_brief``  — parse a finding and produce a DefenseBrief on disk

Every tool returns a compact, JSON-serialisable string so it fits the
LangChain tool return contract and keeps LLM token usage low.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.core.logging import get_logger
from decepticon.schemas.defense_brief import (
    DefenseActionResult,
    DefenseActionType,
    DefenseBrief,
    DefenseRecommendation,
)

log = get_logger("defense.tools")

# ── Backend injection (mirrors bash.py / set_sandbox pattern) ─────────────

_backend: Any | None = None


def set_defense_backend(backend: Any) -> None:
    """Inject the shared defense backend instance (called from defender agent setup)."""
    global _backend
    _backend = backend


def get_defense_backend() -> Any | None:
    """Return the current defense backend instance."""
    return _backend


# ── Neo4j helper ─────────────────────────────────────────────────────────


def _get_neo4j() -> Any:
    from decepticon.tools.research.neo4j_store import Neo4jStore

    return Neo4jStore.from_env()


# ── Tool implementations ──────────────────────────────────────────────────


@tool
def defense_read_brief(workspace_path: str) -> str:
    """Read and validate the defense brief for the current engagement.

    Loads ``{workspace_path}/defense-brief.json`` from disk, validates it
    against the DefenseBrief schema, and returns the structured brief as a
    JSON string ready for the defense agent to act on.

    Returns an error JSON object if the file does not exist or fails validation.

    Args:
        workspace_path: Absolute path to the engagement workspace directory
            (e.g. ``/workspace/eng-001``).
    """
    brief_path = Path(workspace_path) / "defense-brief.json"

    if not brief_path.exists():
        return json.dumps(
            {"error": f"defense-brief.json not found at {brief_path}"},
            ensure_ascii=False,
        )

    try:
        raw = brief_path.read_text(encoding="utf-8")
        brief = DefenseBrief.model_validate_json(raw)
        return brief.model_dump_json(indent=None)
    except Exception as exc:
        log.warning("defense_read_brief failed to parse %s: %s", brief_path, exc)
        return json.dumps(
            {"error": f"Failed to parse defense-brief.json: {exc}"}, ensure_ascii=False
        )


@tool
async def defense_execute_action(
    action_type: str,
    target: str,
    parameters: str = "{}",
) -> str:
    """Execute a defensive action on the target via the defense backend.

    Parses ``action_type`` into a ``DefenseActionType`` enum value, builds a
    ``DefenseRecommendation``, and delegates execution to the injected defense
    backend (``backend.execute_action()``).

    Returns a ``DefenseActionResult`` as a JSON string, including ``success``,
    ``message``, and optional ``rollback_command``.

    Args:
        action_type: One of the ``DefenseActionType`` values:
            ``block_port``, ``add_firewall_rule``, ``disable_service``,
            ``restart_service``, ``update_config``, ``kill_process``,
            ``revoke_credential``.
        target: What to act on — port (``tcp/8080``), service name (``sshd``),
            IP/hostname, or credential identifier.
        parameters: JSON object of action-specific parameters
            (e.g. ``{"rule": "DROP", "chain": "INPUT"}``).
    """
    if _backend is None:
        return json.dumps(
            {"error": "Defense backend not initialized. Call set_defense_backend() first."},
            ensure_ascii=False,
        )

    try:
        parsed_type = DefenseActionType(action_type)
    except ValueError:
        valid = [e.value for e in DefenseActionType]
        return json.dumps(
            {"error": f"Unknown action_type '{action_type}'. Valid values: {valid}"},
            ensure_ascii=False,
        )

    try:
        params: dict[str, str] = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"parameters must be valid JSON: {exc}"}, ensure_ascii=False)

    recommendation = DefenseRecommendation(
        action_type=parsed_type,
        target=target,
        parameters=params,
        rationale="Executed via defense_execute_action tool",
    )

    try:
        result: DefenseActionResult = await _backend.execute_action(recommendation)
        return result.model_dump_json(indent=None)
    except Exception as exc:
        log.error("defense_execute_action failed: %s", exc)
        return json.dumps({"error": f"Action execution failed: {exc}"}, ensure_ascii=False)


@tool
def defense_log_action(
    action_type: str,
    target: str,
    success: bool,
    finding_ref: str,
    message: str = "",
) -> str:
    """Record a defensive action in the Neo4j knowledge graph.

    Creates a ``DefenseAction`` node and writes three relationships:

    - ``RESPONDS_TO`` → the ``Finding`` node identified by ``finding_ref``
    - ``MITIGATES``   → any ``Vulnerability`` linked to that finding
    - ``DEFENDS``     → any ``Host`` or ``Service`` in the finding's affected assets

    Returns a confirmation JSON with the created node key and relationship counts.

    Args:
        action_type: One of the ``DefenseActionType`` values (e.g. ``block_port``).
        target: The specific target the action was applied to.
        success: Whether the action completed successfully.
        finding_ref: Finding reference (e.g. ``FIND-001``) — used to look up the
            Finding node and its linked Vulnerability / Host / Service nodes.
        message: Human-readable result message; included in the node properties.
    """
    try:
        parsed_type = DefenseActionType(action_type)
    except ValueError:
        valid = [e.value for e in DefenseActionType]
        return json.dumps(
            {"error": f"Unknown action_type '{action_type}'. Valid values: {valid}"},
            ensure_ascii=False,
        )

    node_key = f"defense-{finding_ref}-{parsed_type.value}-{target}"
    executed_at = datetime.now(timezone.utc).isoformat()

    try:
        store = _get_neo4j()
    except Exception as exc:
        log.warning("defense_log_action: Neo4j unavailable — %s", exc)
        return json.dumps(
            {"error": f"Neo4j unavailable: {exc}"},
            ensure_ascii=False,
        )

    try:
        driver = store._driver
        database = store._database

        with driver.session(database=database) as session:
            # 1. Upsert the DefenseAction node
            session.run(
                """
                MERGE (da:DefenseAction {key: $key})
                SET da.action_type = $action_type,
                    da.target = $target,
                    da.success = $success,
                    da.message = $message,
                    da.executed_at = $executed_at,
                    da.finding_ref = $finding_ref
                """,
                key=node_key,
                action_type=parsed_type.value,
                target=target,
                success=success,
                message=message,
                executed_at=executed_at,
                finding_ref=finding_ref,
            )

            # 2. RESPONDS_TO → Finding
            responds_result = session.run(
                """
                MATCH (f:Finding {key: $finding_ref})
                MATCH (da:DefenseAction {key: $key})
                MERGE (da)-[:RESPONDS_TO]->(f)
                RETURN count(*) AS cnt
                """,
                finding_ref=finding_ref,
                key=node_key,
            )
            responds_count = responds_result.single(strict=False)
            responds_cnt = responds_count["cnt"] if responds_count else 0

            # 3. MITIGATES → Vulnerability nodes linked to the finding
            mitigates_result = session.run(
                """
                MATCH (f:Finding {key: $finding_ref})-[:HAS_VULN|EXPLOITS|AFFECTS*1..2]->(v:Vulnerability)
                MATCH (da:DefenseAction {key: $key})
                MERGE (da)-[:MITIGATES]->(v)
                RETURN count(*) AS cnt
                """,
                finding_ref=finding_ref,
                key=node_key,
            )
            mitigates_record = mitigates_result.single(strict=False)
            mitigates_cnt = mitigates_record["cnt"] if mitigates_record else 0

            # 4. DEFENDS → Host and Service nodes in finding's asset scope
            defends_result = session.run(
                """
                MATCH (f:Finding {key: $finding_ref})-[:AFFECTS|HOSTS*1..2]->(n)
                WHERE n:Host OR n:Service
                MATCH (da:DefenseAction {key: $key})
                MERGE (da)-[:DEFENDS]->(n)
                RETURN count(*) AS cnt
                """,
                finding_ref=finding_ref,
                key=node_key,
            )
            defends_record = defends_result.single(strict=False)
            defends_cnt = defends_record["cnt"] if defends_record else 0

        return json.dumps(
            {
                "status": "logged",
                "node_key": node_key,
                "responds_to": responds_cnt,
                "mitigates": mitigates_cnt,
                "defends": defends_cnt,
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        log.error("defense_log_action Cypher error: %s", exc)
        return json.dumps({"error": f"KG write failed: {exc}"}, ensure_ascii=False)
    finally:
        store.close()


@tool
async def defense_verify_status(action_type: str, target: str) -> str:
    """Check whether a previously applied defensive action is still active.

    Delegates to the injected defense backend (``backend.verify_action()``)
    and returns a JSON object with ``active`` (bool) and ``details`` (str).

    Args:
        action_type: One of the ``DefenseActionType`` values (e.g. ``block_port``).
        target: The specific target to verify (port, service name, IP, etc.).
    """
    if _backend is None:
        return json.dumps(
            {"error": "Defense backend not initialized. Call set_defense_backend() first."},
            ensure_ascii=False,
        )

    try:
        parsed_type = DefenseActionType(action_type)
    except ValueError:
        valid = [e.value for e in DefenseActionType]
        return json.dumps(
            {"error": f"Unknown action_type '{action_type}'. Valid values: {valid}"},
            ensure_ascii=False,
        )

    result = DefenseActionResult(
        action_type=parsed_type,
        target=target,
        success=False,
        message="",
    )

    try:
        verification = await _backend.verify_action(result)
        if isinstance(verification, dict):
            return json.dumps(verification, ensure_ascii=False)
        # Backend may return a DefenseActionResult or similar model
        if hasattr(verification, "model_dump"):
            return json.dumps(
                {"active": verification.success, "details": verification.message},
                ensure_ascii=False,
            )
        return json.dumps(
            {"active": bool(verification), "details": str(verification)}, ensure_ascii=False
        )
    except Exception as exc:
        log.error("defense_verify_status failed: %s", exc)
        return json.dumps({"error": f"Verification failed: {exc}"}, ensure_ascii=False)


@tool
def defense_generate_brief(finding_ref: str, workspace_path: str) -> str:
    """Parse a finding file and generate a DefenseBrief for the defense agent.

    Reads ``{workspace_path}/findings/{finding_ref}.md``, extracts title,
    severity, description, and affected assets, then synthesises a
    ``DefenseBrief`` with recommended defensive actions based on the
    vulnerability type detected in the finding text.

    Writes the brief to ``{workspace_path}/defense-brief.json`` and returns
    it as a JSON string.

    This tool is called by the OFFENSIVE agent after confirming a finding, to
    hand off structured remediation context to the defense agent.

    Args:
        finding_ref: Finding identifier, e.g. ``FIND-001``. Used to locate
            ``{workspace_path}/findings/{finding_ref}.md``.
        workspace_path: Absolute path to the engagement workspace directory.
    """
    findings_path = Path(workspace_path) / "findings" / f"{finding_ref}.md"

    if not findings_path.exists():
        return json.dumps(
            {"error": f"Finding file not found: {findings_path}"},
            ensure_ascii=False,
        )

    try:
        content = findings_path.read_text(encoding="utf-8")
    except OSError as exc:
        return json.dumps({"error": f"Could not read finding: {exc}"}, ensure_ascii=False)

    # ── Parse finding metadata from markdown ─────────────────────────────
    title = _extract_field(content, r"^#\s+(.+)", r"(?i)^##?\s*title[:\s]+(.+)")
    severity = (
        _extract_field(
            content,
            r"(?i)\*\*severity\*\*[:\s]+(\w+)",
            r"(?i)^severity[:\s]+(\w+)",
            r"(?i)\bseverity:\s*(\w+)",
        )
        or "medium"
    )
    description = (
        _extract_field(
            content,
            r"(?i)##\s*description\s*\n([\s\S]+?)(?=\n##|\Z)",
            r"(?i)##\s*summary\s*\n([\s\S]+?)(?=\n##|\Z)",
        )
        or ""
    )
    affected_assets = _extract_assets(content)
    attack_vector = (
        _extract_field(
            content,
            r"(?i)##\s*attack\s+vector\s*\n([\s\S]+?)(?=\n##|\Z)",
            r"(?i)##\s*exploitation\s*\n([\s\S]+?)(?=\n##|\Z)",
        )
        or description[:500]
    )

    recommendations = _infer_recommendations(content, severity)

    brief = DefenseBrief(
        finding_ref=finding_ref,
        finding_title=title or finding_ref,
        severity=severity.lower(),
        attack_vector=attack_vector.strip()[:1000],
        affected_assets=affected_assets,
        recommended_actions=recommendations,
        evidence_summary=_extract_field(
            content,
            r"(?i)##\s*evidence\s*\n([\s\S]+?)(?=\n##|\Z)",
            r"(?i)##\s*proof[- ]of[- ]concept\s*\n([\s\S]+?)(?=\n##|\Z)",
        )
        or "",
    )

    output_path = Path(workspace_path) / "defense-brief.json"
    try:
        output_path.write_text(brief.model_dump_json(indent=2), encoding="utf-8")
        log.info("defense_generate_brief: wrote %s", output_path)
    except OSError as exc:
        return json.dumps(
            {"error": f"Could not write defense-brief.json: {exc}"}, ensure_ascii=False
        )

    return brief.model_dump_json(indent=None)


# ── Parsing helpers (used only by defense_generate_brief) ─────────────────


def _extract_field(text: str, *patterns: str) -> str | None:
    """Try each regex pattern in order; return first non-empty match group 1."""
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _extract_assets(text: str) -> list[str]:
    """Extract IP addresses, hostnames, and port strings from finding text."""
    assets: list[str] = []

    # Explicit "Affected Assets" section
    section_match = re.search(
        r"(?i)##\s*affected\s+assets?\s*\n([\s\S]+?)(?=\n##|\Z)", text, re.MULTILINE
    )
    if section_match:
        section = section_match.group(1)
        for line in section.splitlines():
            line = line.strip().lstrip("-*• ").strip()
            if line:
                assets.append(line)
        if assets:
            return assets

    # Fall back: scan for IPs and hostnames
    for m in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", text):
        val = m.group(0)
        if val not in assets:
            assets.append(val)

    for m in re.finditer(
        r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", text, re.IGNORECASE
    ):
        val = m.group(0)
        if val not in assets and "." in val:
            assets.append(val)

    return assets[:20]


def _infer_recommendations(content: str, severity: str) -> list[DefenseRecommendation]:
    """Heuristically recommend defensive actions based on finding keywords."""
    lower = content.lower()
    recs: list[DefenseRecommendation] = []
    priority = 1

    if any(kw in lower for kw in ("open port", "exposed port", "listening port", "nmap")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.BLOCK_PORT,
                target="tcp/0",
                rationale="Exposed port identified in finding — block unnecessary listener",
                priority=priority,
            )
        )
        priority += 1

    if any(kw in lower for kw in ("firewall", "iptables", "ufw", "network access", "ingress")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.ADD_FIREWALL_RULE,
                target="network",
                rationale="Network-level exposure — add restrictive firewall rule",
                priority=priority,
            )
        )
        priority += 1

    if any(kw in lower for kw in ("service", "daemon", "running process", "unnecessary service")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.DISABLE_SERVICE,
                target="affected-service",
                rationale="Vulnerable service identified — disable or restrict",
                priority=priority,
            )
        )
        priority += 1

    if any(kw in lower for kw in ("misconfiguration", "config", "configuration", "setting")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.UPDATE_CONFIG,
                target="service-config",
                rationale="Misconfiguration identified — harden configuration",
                priority=priority,
            )
        )
        priority += 1

    if any(kw in lower for kw in ("credential", "password", "token", "api key", "secret")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.REVOKE_CREDENTIAL,
                target="compromised-credential",
                rationale="Credential exposure identified — revoke and rotate",
                priority=priority,
            )
        )
        priority += 1

    if any(kw in lower for kw in ("process", "malicious process", "persistence", "backdoor")):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.KILL_PROCESS,
                target="malicious-process",
                rationale="Malicious or persistent process identified — terminate",
                priority=priority,
            )
        )
        priority += 1

    # Always include a service restart as a low-priority fallback for high/critical
    if severity.lower() in ("high", "critical") and not any(
        r.action_type == DefenseActionType.RESTART_SERVICE for r in recs
    ):
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.RESTART_SERVICE,
                target="affected-service",
                rationale="High/critical severity — restart service to clear any active sessions",
                priority=priority,
            )
        )

    # Ensure at least one recommendation exists
    if not recs:
        recs.append(
            DefenseRecommendation(
                action_type=DefenseActionType.UPDATE_CONFIG,
                target="affected-asset",
                rationale="Generic remediation — review and harden configuration",
                priority=1,
            )
        )

    return recs
