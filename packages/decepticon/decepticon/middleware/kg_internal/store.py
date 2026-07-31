"""KGStore — engagement-scoped Neo4j wrapper for the KG middleware.

Replaces the broken ``decepticon.tools.research._state.graph_transaction``
pattern with per-operation ``session.execute_write`` / ``execute_read``
calls. Each public method takes ``engagement`` as a mandatory keyword
so the contextvar-based scoping that the legacy
``decepticon_core.utils.engagement_scope`` exposed is no longer load-
bearing for KG writes — the middleware passes the label explicitly.

Provenance fields injected automatically on every observation
(Cartography ``update_tag`` + Graphiti ``source_episode_id`` pattern):

  - ``engagement``       — multi-tenant scope label
  - ``firstseen``        — Unix timestamp on first MERGE (ON CREATE)
  - ``lastupdated``      — Unix timestamp on every touch
  - ``created_by``       — agent role string (e.g. "analyst")
  - ``source_episode_id``— LangChain tool_call_id of the tool turn

The Cypher path uses ``session.execute_write``/``execute_read`` so the
driver retries ``Neo.TransientError.Transaction.DeadlockDetected``
automatically — no Python-level lock needed.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from decepticon_core.utils.engagement_scope import is_valid_engagement_label
from decepticon_core.utils.logging import get_logger

log = get_logger("kg.store")


# Labels must be a closed alphanumeric vocabulary (closed in NodeKind /
# EdgeKind enums) so the dynamic interpolation in MERGE statements is
# safe. Defense in depth: also enforce the regex here in case the
# caller bypassed the Pydantic types. Node labels are PascalCase by
# convention (Host, Service, CrownJewel); relationship types are
# UPPER_CASE (HOSTS, HAS_VULN, EXPLOITS).
_SAFE_LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]{0,63}$")
_SAFE_REL_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class KGStoreUnavailableError(RuntimeError):
    """The Neo4j backend is configured but cannot be reached."""


class KGStoreConfigError(RuntimeError):
    """Required environment variables are missing or malformed."""


@dataclass(slots=True)
class KGStoreConfig:
    """Connection config — pulled from env in production, injected in tests."""

    uri: str
    user: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> KGStoreConfig:
        uri = os.environ.get("DECEPTICON_NEO4J_URI", "").strip()
        user = os.environ.get("DECEPTICON_NEO4J_USER", "").strip()
        password = os.environ.get("DECEPTICON_NEO4J_PASSWORD", "").strip()
        database = os.environ.get("DECEPTICON_NEO4J_DATABASE", "neo4j").strip() or "neo4j"

        missing: list[str] = []
        if not uri:
            missing.append("DECEPTICON_NEO4J_URI")
        if not user:
            missing.append("DECEPTICON_NEO4J_USER")
        if not password:
            missing.append("DECEPTICON_NEO4J_PASSWORD")
        if missing:
            raise KGStoreConfigError("KGStore missing required env vars: " + ", ".join(missing))

        return cls(uri=uri, user=user, password=password, database=database)


def _safe_label(kind: str) -> str:
    """Validate and return a Cypher-safe node label.

    Raises ``ValueError`` if ``kind`` is not a closed-vocabulary
    PascalCase identifier. Used in dynamic MERGE interpolation where
    parameterization is impossible (Cypher does not parameterize
    labels).
    """
    if not isinstance(kind, str) or not _SAFE_LABEL_RE.match(kind):
        raise ValueError(f"invalid node label {kind!r}; must match [A-Za-z][A-Za-z0-9]{{0,63}}")
    return kind


def _safe_rel_type(kind: str) -> str:
    """Validate and return a Cypher-safe relationship type."""
    if not isinstance(kind, str) or not _SAFE_REL_TYPE_RE.match(kind):
        raise ValueError(f"invalid edge type {kind!r}; must match [A-Z][A-Z0-9_]{{0,63}}")
    return kind


def _flatten_props(props: dict[str, Any]) -> dict[str, Any]:
    """Coerce arbitrary props into Neo4j-compatible scalar/list values.

    Primitives and primitive-list values pass through. Nested dicts or
    lists of dicts are JSON-serialised so they survive round-trip
    without losing structure but stop participating in index lookups.
    """
    out: dict[str, Any] = {}
    for key, value in props.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, list) and all(
            isinstance(item, (str, int, float, bool)) for item in value
        ):
            out[key] = value
        else:
            try:
                out[key] = json.dumps(value, default=str)
            except (TypeError, ValueError):
                out[key] = str(value)
    return out


class KGStore:
    """Engagement-scoped Neo4j wrapper. Implements AttackGraphProtocol.

    Construct via ``KGStore.from_env()`` in production; pass a
    ``KGStoreConfig`` plus an optional driver in tests.
    """

    def __init__(
        self,
        config: KGStoreConfig,
        *,
        driver: Any = None,
    ) -> None:
        if driver is None:
            # Lazy import so test code can construct a KGStore against a
            # fake driver without pulling in the real neo4j package.
            import neo4j

            try:
                driver = neo4j.GraphDatabase.driver(config.uri, auth=(config.user, config.password))
            except Exception as exc:
                raise KGStoreUnavailableError(
                    f"failed to open Neo4j driver at {config.uri}: {exc}"
                ) from exc
        self._driver = driver
        self._database = config.database

    @classmethod
    def from_env(cls) -> KGStore:
        return cls(KGStoreConfig.from_env())

    def close(self) -> None:
        try:
            self._driver.close()
        except Exception as exc:
            log.debug("KGStore driver close raised (swallowed): %s", exc)

    # ── Engagement scope safety ────────────────────────────────────────

    @staticmethod
    def _check_engagement(engagement: str) -> None:
        if not isinstance(engagement, str) or not engagement:
            raise ValueError("KGStore methods require a non-empty engagement label")
        if not is_valid_engagement_label(engagement):
            raise ValueError(
                f"invalid engagement label {engagement!r}; "
                "must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}"
            )

    # ── Generic Cypher execution ───────────────────────────────────────

    @staticmethod
    def _check_scoped_cypher(cypher: str, engagement: str) -> None:
        # Schema migrations legitimately contain DDL without a row-level scope.
        # Every runtime graph operation must bind the trusted partition into the
        # statement itself; merely validating an unused keyword is not isolation.
        if engagement != "schema" and "$engagement" not in cypher:
            raise ValueError("Neo4j query rejected: missing $engagement scope")

    def execute_read(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        engagement: str,
    ) -> list[dict[str, Any]]:
        """Run a read transaction. ``engagement`` must be injected into
        the Cypher by the caller — this method enforces that the scope
        label is set, that the statement actually binds ``$engagement``,
        and that the caller's params cannot replace that value."""
        self._check_engagement(engagement)
        self._check_scoped_cypher(cypher, engagement)
        # The method argument is authoritative. A legacy/raw caller cannot
        # replace it by smuggling a second value in ``params``.
        scoped_params = {**(params or {}), "engagement": engagement}
        with self._driver.session(database=self._database) as session:
            return session.execute_read(
                lambda tx: [dict(record) for record in tx.run(cypher, **scoped_params)]
            )

    def execute_write(
        self,
        cypher: str,
        params: dict[str, Any] | None = None,
        *,
        engagement: str,
    ) -> list[dict[str, Any]]:
        """Run a write transaction. Driver retries deadlock errors."""
        self._check_engagement(engagement)
        self._check_scoped_cypher(cypher, engagement)
        scoped_params = {**(params or {}), "engagement": engagement}
        with self._driver.session(database=self._database) as session:
            return session.execute_write(
                lambda tx: [dict(record) for record in tx.run(cypher, **scoped_params)]
            )

    # ── AttackGraphProtocol implementation ─────────────────────────────

    def revision(self, *, engagement: str) -> str:
        """Opaque token. Changes when any node's ``lastupdated`` advances
        for this engagement."""
        self._check_engagement(engagement)
        cypher = (
            "MATCH (n) WHERE n.engagement = $engagement "
            "RETURN coalesce(max(n.lastupdated), 0) AS rev"
        )
        rows = self.execute_read(cypher, {"engagement": engagement}, engagement=engagement)
        rev_val = rows[0]["rev"] if rows else 0
        return f"rev-{engagement}-{int(rev_val)}"

    def snapshot(self, *, engagement: str):
        """Build an EngagementSnapshot for ``cart.diff_snapshots`` consumption.

        Lazy-imported to avoid a circular: ``cart.py`` imports from
        ``decepticon.runtime``, which the middleware does not need to
        pull in just to construct a snapshot.
        """
        from decepticon.runtime.cart import EngagementSnapshot, SnapshotNodeKey, _hash_snapshot

        self._check_engagement(engagement)

        node_cypher = (
            "MATCH (n) WHERE n.engagement = $engagement "
            "RETURN labels(n) AS labels, n.label AS label, n.key AS key, "
            "       coalesce(n.props_json, '{}') AS props_json"
        )
        edge_cypher = (
            "MATCH (s)-[r]->(d) "
            "WHERE s.engagement = $engagement AND d.engagement = $engagement "
            "  AND r.engagement = $engagement "
            "RETURN s.key AS src_key, d.key AS dst_key, type(r) AS kind, "
            "       labels(s) AS src_labels, labels(d) AS dst_labels, "
            "       s.label AS src_label, d.label AS dst_label, "
            "       coalesce(r.props_json, '{}') AS props_json"
        )

        nodes: dict[SnapshotNodeKey, dict[str, Any]] = {}
        edges: dict[tuple[SnapshotNodeKey, SnapshotNodeKey, str], dict[str, Any]] = {}
        key_to_snk: dict[str, SnapshotNodeKey] = {}

        params: dict[str, Any] = {"engagement": engagement}
        with self._driver.session(database=self._database) as session:
            for record in session.execute_read(lambda tx: list(tx.run(node_cypher, **params))):
                labels = [str(label) for label in record["labels"] if label]
                if not labels:
                    continue
                primary_kind = labels[0].lower()
                label_value = str(record["label"] or "")
                snk = SnapshotNodeKey(kind=primary_kind, label=label_value)
                key = str(record["key"] or "")
                if key:
                    key_to_snk[key] = snk
                try:
                    props = json.loads(record["props_json"])
                except (TypeError, ValueError):
                    props = {}
                nodes[snk] = props if isinstance(props, dict) else {}

            for record in session.execute_read(lambda tx: list(tx.run(edge_cypher, **params))):
                src_key = str(record["src_key"] or "")
                dst_key = str(record["dst_key"] or "")
                rel_kind = str(record["kind"] or "").lower()
                src = key_to_snk.get(src_key)
                dst = key_to_snk.get(dst_key)
                if src is None or dst is None or not rel_kind:
                    continue
                try:
                    props = json.loads(record["props_json"])
                except (TypeError, ValueError):
                    props = {}
                edges[(src, dst, rel_kind)] = props if isinstance(props, dict) else {}

        return EngagementSnapshot(
            snapshot_id=_hash_snapshot(nodes, edges),
            captured_at=time.time(),
            nodes=nodes,
            edges=edges,
        )

    # ── Observation recording (kg_record tool backend) ─────────────────

    def record_observations(
        self,
        observations: Iterable[dict[str, Any]],
        *,
        engagement: str,
        created_by: str,
        source_episode_id: str,
    ) -> dict[str, Any]:
        """Atomic batch write of node + outgoing-edge observations.

        Every node and edge gets provenance auto-injected
        (engagement, firstseen, lastupdated, created_by,
        source_episode_id). All observations land in a single
        transaction — partial failure rolls back the batch.

        Returns ``{"created": N, "merged": M, "edges": E,
        "revision": "..."}``.
        """
        self._check_engagement(engagement)
        if not isinstance(created_by, str) or not created_by:
            raise ValueError("created_by must be a non-empty string (agent role)")
        if not isinstance(source_episode_id, str) or not source_episode_id:
            raise ValueError("source_episode_id must be a non-empty string (tool_call_id)")

        obs_list = [o for o in observations if isinstance(o, dict)]
        if not obs_list:
            return {
                "created": 0,
                "merged": 0,
                "edges": 0,
                "revision": self.revision(engagement=engagement),
            }

        update_tag = int(time.time())
        node_rows: list[dict[str, Any]] = []
        edge_rows: list[dict[str, Any]] = []

        for obs in obs_list:
            kind = _safe_label(obs.get("kind", ""))
            key = obs.get("key")
            if not isinstance(key, str) or not key:
                raise ValueError(
                    f"observation kind={kind!r} missing mandatory 'key' (deterministic dedup)"
                )
            label = str(obs.get("label") or key)
            raw_props = obs.get("props")
            props = _flatten_props(dict(raw_props) if isinstance(raw_props, dict) else {})
            # Reserve provenance fields — operator-supplied values are
            # silently discarded so the agent cannot forge provenance.
            for reserved in (
                "engagement",
                "firstseen",
                "lastupdated",
                "created_by",
                "source_episode_id",
            ):
                props.pop(reserved, None)

            node_rows.append(
                {
                    "kind": kind,
                    "key": key,
                    "label": label,
                    "props": props,
                }
            )

            for edge in obs.get("edges_out") or []:
                if not isinstance(edge, dict):
                    continue
                to_key = edge.get("to_key")
                rel_kind = edge.get("kind")
                if not isinstance(to_key, str) or not to_key:
                    continue
                # Fail-fast: silently dropping edges here hides data
                # loss (the IngestState stats counter already counted
                # this edge before observation handoff). ``_safe_rel_type``
                # raises ``ValueError`` for any rel kind that doesn't
                # match the closed UPPER_SNAKE_CASE vocabulary; surfacing
                # it abort the whole batch and tells the caller exactly
                # which kind needs to be added to ``EdgeKind`` or
                # remapped at the ingest layer.
                rel_type = _safe_rel_type(rel_kind or "")
                try:
                    weight = float(edge.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
                edge_props_raw = edge.get("props")
                edge_props = _flatten_props(
                    dict(edge_props_raw) if isinstance(edge_props_raw, dict) else {}
                )
                for reserved in (
                    "engagement",
                    "firstseen",
                    "lastupdated",
                    "created_by",
                    "source_episode_id",
                    "weight",
                ):
                    edge_props.pop(reserved, None)
                edge_rows.append(
                    {
                        "src_key": key,
                        "dst_key": to_key,
                        "kind": rel_type,
                        "weight": weight,
                        "props": edge_props,
                    }
                )

        # Group node rows by label so we can MERGE under the right
        # label (Cypher doesn't parameterize labels). For each label
        # batch one UNWIND-MERGE. Same for edges grouped by rel type.
        nodes_by_label: dict[str, list[dict[str, Any]]] = {}
        for row in node_rows:
            nodes_by_label.setdefault(row["kind"], []).append(row)
        edges_by_type: dict[str, list[dict[str, Any]]] = {}
        for row in edge_rows:
            edges_by_type.setdefault(row["kind"], []).append(row)

        created = 0
        merged = 0
        edges_written = 0

        def _do_writes(tx: Any) -> tuple[int, int, int]:
            local_created = 0
            local_merged = 0
            local_edges = 0
            for label, rows in nodes_by_label.items():
                node_query = (
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label} {{key: row.key, engagement: $engagement}}) "
                    "ON CREATE SET n.firstseen = $now, n._jc = true "
                    "ON MATCH SET n._jc = false "
                    "SET n.label = row.label, "
                    "    n.lastupdated = $now, "
                    "    n.created_by = $created_by, "
                    "    n.source_episode_id = $source_episode_id, "
                    "    n += row.props "
                    "WITH n, n._jc AS just_created "
                    "REMOVE n._jc "
                    "RETURN sum(CASE WHEN just_created THEN 1 ELSE 0 END) AS created, "
                    "       sum(CASE WHEN just_created THEN 0 ELSE 1 END) AS merged"
                )
                for record in tx.run(
                    node_query,
                    rows=rows,
                    engagement=engagement,
                    now=update_tag,
                    created_by=created_by,
                    source_episode_id=source_episode_id,
                ):
                    local_created += int(record["created"] or 0)
                    local_merged += int(record["merged"] or 0)
            for rel_type, rows in edges_by_type.items():
                edge_query = (
                    "UNWIND $rows AS row "
                    "MATCH (s {key: row.src_key, engagement: $engagement}) "
                    "MATCH (d {key: row.dst_key, engagement: $engagement}) "
                    f"MERGE (s)-[r:{rel_type}]->(d) "
                    # ``r.engagement`` is mandatory: engagement-scoped
                    # reads filter every edge via ``WHERE r.engagement
                    # = $engagement``. Without it the edge survives the
                    # write but is invisible to every read path
                    # (``snapshot`` / ``revision`` / ``query``). The
                    # mistake was silent because V001 / V002 only
                    # constrain node uniqueness, not edge properties.
                    "ON CREATE SET r.firstseen = $now, r.engagement = $engagement "
                    "SET r.lastupdated = $now, "
                    "    r.engagement = $engagement, "
                    "    r.created_by = $created_by, "
                    "    r.source_episode_id = $source_episode_id, "
                    "    r.weight = row.weight, "
                    "    r += row.props "
                    "RETURN count(r) AS written"
                )
                for record in tx.run(
                    edge_query,
                    rows=rows,
                    engagement=engagement,
                    now=update_tag,
                    created_by=created_by,
                    source_episode_id=source_episode_id,
                ):
                    local_edges += int(record["written"] or 0)
            return local_created, local_merged, local_edges

        with self._driver.session(database=self._database) as session:
            created, merged, edges_written = session.execute_write(_do_writes)

        return {
            "created": created,
            "merged": merged,
            "edges": edges_written,
            "revision": f"rev-{engagement}-{update_tag}",
        }

    # ── Stale-node cleanup (Cartography update_tag pattern) ────────────

    def delete_stale(self, *, engagement: str, before_unix: int) -> int:
        """Detach-delete nodes in ``engagement`` whose ``lastupdated``
        precedes ``before_unix``. Returns the number deleted.

        Bounded by ``LIMIT 1000`` per call so a single sweep can't
        block the engagement on a runaway. Callers loop if they need
        to drain more.
        """
        self._check_engagement(engagement)
        if not isinstance(before_unix, int):
            raise ValueError("before_unix must be an int Unix timestamp")
        cypher = (
            "MATCH (n) WHERE n.engagement = $engagement AND n.lastupdated < $cutoff "
            "WITH n LIMIT 1000 "
            "DETACH DELETE n "
            "RETURN count(n) AS deleted"
        )
        rows = self.execute_write(
            cypher,
            {"engagement": engagement, "cutoff": before_unix},
            engagement=engagement,
        )
        return int(rows[0]["deleted"] or 0) if rows else 0
