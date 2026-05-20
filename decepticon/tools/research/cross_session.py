"""EvoGraph — cross-session memory bootstrap layer over Neo4jStore.

Decepticon's existing Neo4jStore (``decepticon.tools.research.neo4j_store``)
holds the *current* engagement's attack graph. But the database persists
across runs — every engagement's nodes/edges accumulate in the same
Neo4j instance.

This module adds:

1. **Engagement-scoped namespacing.** A first-class ``Engagement`` node
   tagging all current-session nodes via an ``IN_ENGAGEMENT`` edge.
2. **End-of-engagement memorialization.** ``commit_engagement_memory()``
   distills the engagement's terminal findings + attack paths into an
   ``EngagementMemory`` summary node — a compact prose + structured
   record that future engagements can read.
3. **Cross-engagement similarity bootstrap.** On engagement startup,
   ``bootstrap_from_prior()`` retrieves prior ``EngagementMemory``
   records that match the current target/scope/bug-class, then exposes
   them to the orchestrator as a "we've seen this before" prompt
   addition.

This implements the EvoGraph concept (lessons-learned memory layer over
the attack graph) referenced in PR-E of the original roadmap. It does
NOT replace the active-engagement graph — that lives in Neo4jStore +
graph.py as before.

Design choices:

- **No new schema migration needed.** ``Engagement`` and
  ``EngagementMemory`` are added to ``NodeKind`` as PascalCase labels;
  Neo4jStore creates them transparently.
- **Idempotent constraint registration.** ``ensure_evograph_schema()``
  adds two new uniqueness constraints (engagement_slug, memory_key) to
  the existing ensure_schema flow.
- **Graceful degradation.** If Neo4j isn't reachable, all functions
  return empty results — engagements still run, just without bootstrap.
- **No model calls.** Memory summarization is structural (counts,
  bug-class tally, top techniques). LLM-based prose summarization is a
  separate concern for the orchestrator's report agent.

Public API (importable from ``decepticon.tools.research.cross_session``):

- ``register_engagement(slug, target, started_at=None)`` — call at engagement start
- ``tag_node_to_engagement(node_key, kind, engagement_slug)`` — call on each upsert
- ``commit_engagement_memory(engagement_slug)`` — call at engagement end
- ``bootstrap_from_prior(target_hint, top_k=5)`` — call at engagement start
- ``find_similar_findings(bug_class, target_kind=None, limit=10)`` — runtime helper
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from decepticon.tools.research._state import get_store
from decepticon.tools.research.neo4j_store import Neo4jUnavailableError

logger = logging.getLogger(__name__)


# ── Data shapes ───────────────────────────────────────────────────────


@dataclass
class EngagementMemory:
    """Distilled record of a completed engagement.

    Compact enough to fit a handful in a system prompt; rich enough to
    bootstrap a similar future engagement.
    """

    slug: str
    target: str
    started_at: str
    ended_at: str
    total_findings: int = 0
    validated_findings: int = 0
    shipped_findings: int = 0
    top_bug_classes: list[tuple[str, int]] = field(default_factory=list)
    top_techniques: list[str] = field(default_factory=list)
    crown_jewels_reached: list[str] = field(default_factory=list)
    notable_attack_paths: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "target": self.target,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_findings": self.total_findings,
            "validated_findings": self.validated_findings,
            "shipped_findings": self.shipped_findings,
            "top_bug_classes": self.top_bug_classes,
            "top_techniques": self.top_techniques,
            "crown_jewels_reached": self.crown_jewels_reached,
            "notable_attack_paths": self.notable_attack_paths,
            "note": self.note,
        }


# ── Schema bootstrap ──────────────────────────────────────────────────


_EVOGRAPH_CONSTRAINTS = [
    "CREATE CONSTRAINT engagement_slug IF NOT EXISTS FOR (e:Engagement) REQUIRE e.slug IS UNIQUE",
    (
        "CREATE CONSTRAINT engagement_memory_key IF NOT EXISTS"
        " FOR (m:EngagementMemory) REQUIRE m.slug IS UNIQUE"
    ),
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_evograph_schema() -> bool:
    """Idempotent — adds Engagement/EngagementMemory uniqueness constraints.

    Returns True on success, False if Neo4j unavailable.
    """
    try:
        store = get_store()
    except Neo4jUnavailableError:
        logger.info("evograph: Neo4j unavailable, skipping schema bootstrap")
        return False
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            for stmt in _EVOGRAPH_CONSTRAINTS:
                session.run(stmt)
        return True
    except Exception as exc:  # pragma: no cover
        logger.warning(f"evograph schema bootstrap failed: {exc}")
        return False


# ── Engagement registration ───────────────────────────────────────────


def register_engagement(
    slug: str,
    target: str,
    *,
    started_at: str | None = None,
    scope: str | None = None,
) -> bool:
    """Create the Engagement anchor node. Idempotent."""
    try:
        store = get_store()
    except Neo4jUnavailableError:
        return False
    ts = started_at or _utc_now_iso()
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            session.run(
                """
                MERGE (e:Engagement {slug: $slug})
                ON CREATE SET e.target = $target,
                              e.started_at = $started_at,
                              e.scope = $scope
                ON MATCH SET  e.last_seen_at = $started_at
                """,
                slug=slug,
                target=target,
                started_at=ts,
                scope=scope or "",
            )
        return True
    except Exception as exc:
        logger.warning(f"register_engagement({slug}) failed: {exc}")
        return False


def tag_node_to_engagement(
    *,
    node_key: str,
    kind: str,
    engagement_slug: str,
    key_property: str = "key",
) -> bool:
    """Link an existing graph node to the engagement.

    Args:
        node_key: identifying value of the node
        kind: Neo4j label (e.g. "Finding", "Vulnerability")
        engagement_slug: the Engagement.slug to attach to
        key_property: which property on the node is unique. Default
            "key"; some kinds use "ip"/"cve_id"/"fqdn"/etc.
    """
    try:
        store = get_store()
    except Neo4jUnavailableError:
        return False
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            session.run(
                f"""
                MATCH (e:Engagement {{slug: $slug}})
                MATCH (n:`{kind}` {{`{key_property}`: $node_key}})
                MERGE (n)-[:IN_ENGAGEMENT]->(e)
                """,
                slug=engagement_slug,
                node_key=node_key,
            )
        return True
    except Exception as exc:
        logger.debug(f"tag_node_to_engagement skipped: {exc}")
        return False


# ── End-of-engagement memory commit ───────────────────────────────────


def commit_engagement_memory(
    engagement_slug: str,
    *,
    note: str = "",
) -> EngagementMemory | None:
    """Distill engagement into an EngagementMemory node.

    Counts findings by bug_class/status, collects top techniques + crown
    jewels reached, writes a compact memory node future engagements can
    query.

    Returns the in-memory ``EngagementMemory`` dataclass for caller use,
    or None if Neo4j unavailable.
    """
    try:
        store = get_store()
    except Neo4jUnavailableError:
        return None

    ended = _utc_now_iso()
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            # Pull engagement metadata
            rec = session.run(
                "MATCH (e:Engagement {slug:$slug}) RETURN e.target AS target, e.started_at AS started_at",
                slug=engagement_slug,
            ).single()
            if rec is None:
                return None
            target = rec["target"] or "unknown"
            started_at = rec["started_at"] or ended

            # Findings tally
            tally = session.run(
                """
                MATCH (f:Finding)-[:IN_ENGAGEMENT]->(:Engagement {slug:$slug})
                RETURN coalesce(f.status,'unknown') AS status,
                       coalesce(f.bug_class,'unknown') AS bug_class
                """,
                slug=engagement_slug,
            ).data()
            total = len(tally)
            validated = sum(1 for r in tally if r["status"] in ("validated", "shipped"))
            shipped = sum(1 for r in tally if r["status"] == "shipped")
            bc_counts: dict[str, int] = {}
            for r in tally:
                bc_counts[r["bug_class"]] = bc_counts.get(r["bug_class"], 0) + 1
            top_bcs = sorted(bc_counts.items(), key=lambda kv: -kv[1])[:5]

            # Techniques
            techs = session.run(
                """
                MATCH (t:Technique)-[:IN_ENGAGEMENT]->(:Engagement {slug:$slug})
                RETURN coalesce(t.label, t.technique_id) AS label
                ORDER BY label LIMIT 10
                """,
                slug=engagement_slug,
            )
            top_techs = [r["label"] for r in techs if r["label"]]

            # Crown jewels reached (any CrownJewel node tagged)
            cjs = session.run(
                """
                MATCH (c:CrownJewel)-[:IN_ENGAGEMENT]->(:Engagement {slug:$slug})
                RETURN coalesce(c.label, c.key) AS label
                """,
                slug=engagement_slug,
            )
            cjs_reached = [r["label"] for r in cjs if r["label"]]

            # Attack paths (titles only)
            aps = session.run(
                """
                MATCH (ap:AttackPath)-[:IN_ENGAGEMENT]->(:Engagement {slug:$slug})
                RETURN coalesce(ap.label, ap.key) AS label
                LIMIT 5
                """,
                slug=engagement_slug,
            )
            notable_aps = [r["label"] for r in aps if r["label"]]

            memory = EngagementMemory(
                slug=engagement_slug,
                target=target,
                started_at=started_at,
                ended_at=ended,
                total_findings=total,
                validated_findings=validated,
                shipped_findings=shipped,
                top_bug_classes=top_bcs,
                top_techniques=top_techs,
                crown_jewels_reached=cjs_reached,
                notable_attack_paths=notable_aps,
                note=note,
            )

            # Write EngagementMemory node
            session.run(
                """
                MERGE (m:EngagementMemory {slug:$slug})
                SET m.target=$target,
                    m.started_at=$started_at,
                    m.ended_at=$ended_at,
                    m.total_findings=$total_findings,
                    m.validated_findings=$validated_findings,
                    m.shipped_findings=$shipped_findings,
                    m.top_bug_classes=$top_bug_classes_json,
                    m.top_techniques=$top_techniques,
                    m.crown_jewels=$crown_jewels,
                    m.notable_attack_paths=$notable_attack_paths,
                    m.note=$note
                """,
                slug=memory.slug,
                target=memory.target,
                started_at=memory.started_at,
                ended_at=memory.ended_at,
                total_findings=memory.total_findings,
                validated_findings=memory.validated_findings,
                shipped_findings=memory.shipped_findings,
                # Neo4j doesn't store nested arrays well — flatten to "class:count" strings
                top_bug_classes_json=[f"{bc}:{n}" for bc, n in memory.top_bug_classes],
                top_techniques=memory.top_techniques,
                crown_jewels=memory.crown_jewels_reached,
                notable_attack_paths=memory.notable_attack_paths,
                note=memory.note,
            )
            # Link memory back to its engagement
            session.run(
                """
                MATCH (e:Engagement {slug:$slug})
                MATCH (m:EngagementMemory {slug:$slug})
                MERGE (m)-[:SUMMARIZES]->(e)
                """,
                slug=engagement_slug,
            )
            return memory
    except Exception as exc:
        logger.warning(f"commit_engagement_memory({engagement_slug}) failed: {exc}")
        return None


# ── Startup bootstrap queries ─────────────────────────────────────────


def bootstrap_from_prior(
    *,
    target_hint: str,
    top_k: int = 5,
) -> list[EngagementMemory]:
    """Find prior EngagementMemory records relevant to a new engagement.

    Matching is currently substring-based on target field. Future
    enhancement: embed targets + use vector similarity.

    Returns up to ``top_k`` memories ordered by recency (newest first).
    """
    try:
        store = get_store()
    except Neo4jUnavailableError:
        return []
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            res = session.run(
                """
                MATCH (m:EngagementMemory)
                WHERE toLower(m.target) CONTAINS toLower($hint)
                RETURN m
                ORDER BY m.ended_at DESC
                LIMIT $top_k
                """,
                hint=target_hint,
                top_k=top_k,
            )
            out: list[EngagementMemory] = []
            for r in res:
                m = r["m"]
                out.append(
                    EngagementMemory(
                        slug=m["slug"],
                        target=m.get("target", ""),
                        started_at=m.get("started_at", ""),
                        ended_at=m.get("ended_at", ""),
                        total_findings=int(m.get("total_findings") or 0),
                        validated_findings=int(m.get("validated_findings") or 0),
                        shipped_findings=int(m.get("shipped_findings") or 0),
                        top_bug_classes=[
                            (bc.split(":")[0], int(bc.split(":")[1]))
                            for bc in (m.get("top_bug_classes") or [])
                            if ":" in bc
                        ],
                        top_techniques=list(m.get("top_techniques") or []),
                        crown_jewels_reached=list(m.get("crown_jewels") or []),
                        notable_attack_paths=list(m.get("notable_attack_paths") or []),
                        note=m.get("note", ""),
                    )
                )
            return out
    except Exception as exc:
        logger.debug(f"bootstrap_from_prior({target_hint!r}) returned []: {exc}")
        return []


def find_similar_findings(
    *,
    bug_class: str,
    target_kind: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Surface prior findings of the same bug class.

    Use in mid-engagement when the agent identifies a vuln class — fetch
    similar prior findings + their resolution path so the agent can ride
    the same playbook.

    Returns list of dicts with ``{vuln_id, target, status, summary,
    engagement_slug, ended_at}``.
    """
    try:
        store = get_store()
    except Neo4jUnavailableError:
        return []
    try:
        with store._driver.session(database=store._database) as session:  # type: ignore[attr-defined]
            res = session.run(
                """
                MATCH (f:Finding)-[:IN_ENGAGEMENT]->(e:Engagement)
                WHERE f.bug_class = $bug_class
                  AND ($target_kind IS NULL OR f.target_kind = $target_kind)
                RETURN f.key AS vuln_id,
                       e.target AS target,
                       e.slug AS engagement_slug,
                       coalesce(f.status,'unknown') AS status,
                       coalesce(f.summary, f.title, '') AS summary,
                       e.last_seen_at AS ended_at
                ORDER BY e.last_seen_at DESC
                LIMIT $limit
                """,
                bug_class=bug_class,
                target_kind=target_kind,
                limit=limit,
            )
            return [dict(r) for r in res]
    except Exception as exc:
        logger.debug(f"find_similar_findings({bug_class!r}) returned []: {exc}")
        return []


# ── System-prompt formatter ───────────────────────────────────────────


def format_bootstrap_for_prompt(memories: list[EngagementMemory]) -> str:
    """Render a list of prior-engagement memories for inclusion in the
    orchestrator's system prompt.

    Returns a concise XML-tagged block. Empty string if no memories.
    """
    if not memories:
        return ""
    lines = ["<EVOGRAPH_PRIOR_ENGAGEMENTS>"]
    lines.append(f"  count={len(memories)} (target-similar, most-recent-first)")
    for m in memories:
        bug_classes = ", ".join(f"{bc}({n})" for bc, n in m.top_bug_classes[:3])
        techs = ", ".join(m.top_techniques[:3])
        lines.extend([
            f"  <engagement slug={m.slug!r} target={m.target!r} ended={m.ended_at!r}>",
            f"    findings: total={m.total_findings} validated={m.validated_findings} shipped={m.shipped_findings}",
            f"    top_bug_classes: {bug_classes or '(none)'}",
            f"    top_techniques: {techs or '(none)'}",
        ])
        if m.crown_jewels_reached:
            lines.append(f"    crown_jewels_reached: {', '.join(m.crown_jewels_reached[:3])}")
        if m.note:
            lines.append(f"    note: {m.note}")
        lines.append("  </engagement>")
    lines.append("</EVOGRAPH_PRIOR_ENGAGEMENTS>")
    return "\n".join(lines)


__all__ = [
    "EngagementMemory",
    "ensure_evograph_schema",
    "register_engagement",
    "tag_node_to_engagement",
    "commit_engagement_memory",
    "bootstrap_from_prior",
    "find_similar_findings",
    "format_bootstrap_for_prompt",
]
