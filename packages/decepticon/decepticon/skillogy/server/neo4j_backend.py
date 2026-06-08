"""Neo4j-backed storage for the skillogy service.

Replaces the in-memory ``SkillRegistry`` (deleted in Amendment v0.2.2
along with ``ingest.py`` — there were no live importers left after the
REST app was rewritten). The server opens a Bolt session to the Neo4j
instance that ``skillogy.builder`` populates via ``skills.cypher``.

The wire protocol is the new three-operation surface
(``find_skill`` / ``load_skill`` / ``traverse``) plus
``query_moc_summary`` — see ``server/app.py``.

Read-only enforcement
---------------------
Server-driven Cypher (``run_cypher_read`` RPC, Phase 1b-onwards
``recall``) is the obvious attack surface. The backend enforces three
defenses, layered: ``default_access_mode=READ`` on the Bolt session
(server-side), AST-style keyword denylist applied to the inbound
``query`` string (belt-and-suspenders), and a per-query parameter cap
+ row-count cap so a malformed query can't exhaust the agent context.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# Write-mode Cypher keywords we refuse to forward, even though the
# Neo4j driver session is also opened in READ mode. The check is
# whole-word, case-insensitive, after stripping line comments + string
# literals so a benign body like "// MERGE example" cannot be flagged.
_WRITE_KEYWORDS = (
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH",
    "REMOVE",
    "DROP",
    "LOAD",
    "USING PERIODIC COMMIT",
    "FOREACH",
)


def _path_under_any_prefix(path: str | None, prefixes: list[str]) -> bool:
    """Return True iff ``path`` starts with any of the given prefixes.

    Used to enforce the per-role path-prefix ACL (ADR-0008). An empty
    or missing ``path`` (e.g. a non-``:Skill`` neighbour in a traverse
    result) is treated as "not gated" so the caller can apply the
    label-based skip itself; the empty-prefix list short-circuit lives
    at the call site.
    """
    if not path:
        return False
    return any(path.startswith(p) for p in prefixes)


class CypherWriteRejected(ValueError):
    """Raised when a client query trips the write-keyword denylist."""


_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_RE = re.compile(r"'([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\"")
_WORD_BOUNDARY = r"(?<![A-Za-z_])({kw})(?![A-Za-z_])"


def _strip_noise(query: str) -> str:
    """Drop line comments + string literals before keyword scanning."""
    no_comments = _LINE_COMMENT_RE.sub("", query)
    return _STRING_RE.sub("''", no_comments)


def assert_read_only(query: str) -> None:
    """Raise ``CypherWriteRejected`` if ``query`` contains a write keyword."""
    cleaned = _strip_noise(query)
    for kw in _WRITE_KEYWORDS:
        pattern = _WORD_BOUNDARY.format(kw=re.escape(kw))
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            raise CypherWriteRejected(
                f"Cypher write keyword {kw!r} is not allowed in read-only RPC"
            )


class Neo4jBackend:
    """Thin Bolt wrapper used by the FastAPI / grpcio server.

    Created once at server boot, shared across requests. Holds a single
    driver instance; sessions are short-lived (request-scoped). The
    driver is closed in ``close()`` so unit tests with testcontainers
    can tear it down deterministically.
    """

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str = "neo4j",
        max_rows: int = 200,
    ) -> None:
        try:
            from neo4j import GraphDatabase  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "Skillogy server requires the neo4j driver. Install with: pip install neo4j>=5.24"
            ) from exc
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database
        self._max_rows = max_rows

    def close(self) -> None:
        self._driver.close()

    # ---- bulk cypher ingest (used by service boot to seed the graph) ----

    def bulk_ingest_cypher(self, cypher_text: str) -> int:
        """Execute ``cypher_text`` against Neo4j as a sequence of statements.

        The builder emits ``MERGE``-only statements, each terminated by
        ``;`` at end of line — naive splitting on ``;`` alone fragments
        any statement whose string property contains a semicolon (a
        common case: skill bodies and descriptions). Splitting on
        ``;\\n`` instead respects the emitter's contract and round-trips
        the dump cleanly. Idempotent re-runs are safe. Uses a write
        session because startup ingest is the one path that legitimately
        writes; runtime endpoints use read-only sessions.

        Returns the number of statements executed.
        """
        statements = [s.strip() for s in cypher_text.split(";\n") if s.strip()]
        with self._driver.session(database=self._database) as session:
            for stmt in statements:
                # Strip any trailing ``;`` left by the final-statement
                # edge case (the file ends in ``;`` without a newline).
                session.run(stmt.rstrip(";").rstrip())
        return len(statements)

    # ---- skill ops ----

    def load_skill(
        self,
        path: str,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch one ``:Skill`` node by canonical path. Returns its full
        property dict, or ``None`` if no such skill exists.

        When ``allowed_path_prefixes`` is non-empty, paths not under any
        listed prefix return ``None`` (the same shape the agent sees for
        a genuinely missing skill — ADR-0008). ``None`` / empty list
        preserves the unrestricted behaviour for the standalone library,
        the skillogy CLI, and pytest, where no role context exists.
        """
        if allowed_path_prefixes and not _path_under_any_prefix(path, allowed_path_prefixes):
            return None
        query = "MATCH (s:Skill {path: $path}) RETURN properties(s) AS props"
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            result = session.run(query, path=path).single()
        return None if result is None else dict(result["props"])

    def health(self) -> dict[str, Any]:
        """Return service liveness + a count of :Skill nodes in the graph."""
        query = "MATCH (s:Skill) RETURN count(s) AS skill_count"
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            result = session.run(query).single()
        skill_count = 0 if result is None else int(result["skill_count"])
        return {"status": "ok", "skill_count": skill_count}

    # ---- relationship-aware search (used by find_skill RPC) ----

    def find_skill(
        self,
        *,
        query: str | None = None,
        subdomain: str | None = None,
        mitre_id: str | None = None,
        tag: str | None = None,
        tactic_id: str | None = None,
        limit: int = 20,
        allowed_path_prefixes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Relationship-aware skill discovery.

        Composable filters combined with AND semantics. Each filter
        prunes the candidate set via a different edge:

        - ``query``: substring match on name / description / when_to_use.
          Cheap signal for when the agent has a keyword like "kerberoast"
          but not a path.
        - ``subdomain``: ``(s:Skill)-[:IN_PHASE]->(:Phase {name: $sub})``.
        - ``mitre_id``: ``(s:Skill)-[:IMPLEMENTS]->(:Technique {id: $id})``
          where ``$id`` can be a top-level T1xxx or a sub-T1xxx.yyy.
        - ``tag``: ``(s:Skill)-[:TAGGED]->(:Tag {name: $tag})``.
        - ``tactic_id``: anchors on a Tactic, follows ``HAS_TECHNIQUE`` to
          its techniques, then back to skills via ``IMPLEMENTS``. Lets
          the agent ask "show me skills covering Initial Access".

        Returns each match's ``name``, ``path``, ``subdomain``,
        ``description`` and the matched dimensions (``matched_mitre``,
        ``matched_tags``) so the agent can see *why* a skill came back.
        """
        wheres: list[str] = []
        params: dict[str, Any] = {"limit": int(min(max(limit, 1), 100))}
        # Path A: subdomain-anchored
        if subdomain:
            wheres.append("(s)-[:IN_PHASE]->(:Phase {name: $subdomain})")
            params["subdomain"] = subdomain
        # Path B: tag-anchored
        if tag:
            wheres.append("(s)-[:TAGGED]->(:Tag {name: $tag})")
            params["tag"] = tag
        # Path C: technique-anchored (direct)
        if mitre_id:
            wheres.append("(s)-[:IMPLEMENTS]->(:Technique {id: $mitre_id})")
            params["mitre_id"] = mitre_id
        # Path D: tactic-anchored (one hop via Technique)
        if tactic_id:
            wheres.append(
                "(s)-[:IMPLEMENTS]->(:Technique)<-[:HAS_TECHNIQUE]-(:Tactic {id: $tactic_id})"
            )
            params["tactic_id"] = tactic_id
        # Path E: keyword search across name / description / triggers.
        if query:
            wheres.append(
                "(toLower(s.name) CONTAINS toLower($query) "
                "OR toLower(s.description) CONTAINS toLower($query) "
                "OR toLower(s.when_to_use) CONTAINS toLower($query))"
            )
            params["query"] = query
        if not wheres:
            raise ValueError(
                "find_skill requires at least one of: query, subdomain, mitre_id, tag, tactic_id"
            )
        # Per ADR-0008 — narrow the candidate set to the per-role
        # path-prefix allowlist when the caller (agent middleware)
        # supplied one. When the parameter is missing/empty we leave the
        # query unrestricted so the standalone CLI, pytest, and the
        # library entrypoint keep their existing behaviour.
        if allowed_path_prefixes:
            wheres.append("ANY(p IN $allowed_path_prefixes WHERE s.path STARTS WITH p)")
            params["allowed_path_prefixes"] = list(allowed_path_prefixes)
        match_clauses = " AND ".join(wheres)
        cypher = (
            "MATCH (s:Skill) "
            f"WHERE {match_clauses} "
            "OPTIONAL MATCH (s)-[:IMPLEMENTS]->(t:Technique) "
            "OPTIONAL MATCH (s)-[:TAGGED]->(tag:Tag) "
            "WITH s, collect(DISTINCT t.id) AS matched_mitre, "
            "     collect(DISTINCT tag.name) AS matched_tags "
            "RETURN s.name AS name, s.path AS path, s.subdomain AS subdomain, "
            "       s.description AS description, "
            "       matched_mitre, matched_tags "
            "ORDER BY name "
            "LIMIT $limit"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            return [dict(record) for record in session.run(cypher, parameters=params)]

    # ---- per-phase MoC summary (used by SkillogyMiddleware system prompt) ----

    def query_moc_summary(self, phase: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Return MoCs belonging to ``phase``, ordered by name.

        Each row carries ``name``, ``description`` (empty string when
        the MoC has none), and ``parent_phase``. Returns an empty list
        when the phase has no MoCs registered yet — some Phase nodes
        are placeholders until corpus coverage catches up, and the
        caller renders a "no MoCs yet" line instead of a bullet list.
        """
        cypher = (
            "MATCH (m:MoC)-[:BELONGS_TO_PHASE]->(:Phase {name: $phase}) "
            "RETURN m.name AS name, "
            "       coalesce(m.description, '') AS description, "
            "       coalesce(m.parent_phase, $phase) AS parent_phase "
            "ORDER BY name "
            "LIMIT $limit"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            return [
                dict(record)
                for record in session.run(
                    cypher,
                    parameters={"phase": phase, "limit": int(min(max(limit, 1), 100))},
                )
            ]

    # ---- explicit graph traversal (used by traverse RPC) ----

    def traverse(
        self,
        from_path: str,
        edge_types: list[str] | None = None,
        depth: int = 2,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Variable-length BFS from a Skill node along whitelisted edge types.

        Returns the neighbouring nodes flattened, each with its
        ``label``, key identifier, depth from the seed, and a string
        representation of the connecting edge type.

        When ``allowed_path_prefixes`` is non-empty (ADR-0008), the seed
        path must match a listed prefix or the call returns an empty
        list; ``:Skill`` neighbours that fall outside the allowlist are
        filtered from the result. Non-``:Skill`` neighbours (``:Tag``,
        ``:Technique``, ``:Tactic``, ``:MoC``) stay visible because
        they are classification metadata, not skill content.
        """
        if allowed_path_prefixes and not _path_under_any_prefix(from_path, allowed_path_prefixes):
            return []
        depth = max(1, min(int(depth), 5))
        # Default edge whitelist mirrors the spec §5.7.2 list.
        whitelist = edge_types or [
            "IN_PHASE",
            "IMPLEMENTS",
            "TAGGED",
            "BELONGS_TO",
            "RELATED_TO",
            "HAS_TECHNIQUE",
            "HAS_SUBTECHNIQUE",
        ]
        # Cypher relationship pattern: ``[r:A|B|C*1..N]``.
        rel_pattern = f"[r:{'|'.join(whitelist)}*1..{depth}]"
        cypher = (
            "MATCH (seed:Skill {path: $from_path}) "
            f"MATCH path = (seed)-{rel_pattern}-(neighbour) "
            "RETURN labels(neighbour) AS labels, "
            "       coalesce(neighbour.name, neighbour.id, neighbour.path) AS key, "
            "       neighbour.path AS neighbour_path, "
            "       length(path) AS hop_depth, "
            "       [rel IN relationships(path) | type(rel)] AS edge_chain "
            "LIMIT $cap"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            rows: list[dict[str, Any]] = []
            for rec in session.run(
                cypher,
                parameters={"from_path": from_path, "cap": self._max_rows},
            ):
                labels = list(rec["labels"])
                # Per ADR-0008 — drop ``:Skill`` neighbours that fall
                # outside the role's path-prefix allowlist. Non-Skill
                # neighbours (Tag/Technique/Tactic/MoC) are classification
                # metadata, not skill content, and stay visible so the
                # agent can still pivot via shared graph structure.
                if (
                    allowed_path_prefixes
                    and "Skill" in labels
                    and not _path_under_any_prefix(rec["neighbour_path"], allowed_path_prefixes)
                ):
                    continue
                rows.append(
                    {
                        "labels": labels,
                        "key": rec["key"],
                        "depth": int(rec["hop_depth"]),
                        "edge_chain": list(rec["edge_chain"]),
                    }
                )
            return rows

    # ---- read-only cypher escape hatch (used by run_cypher_read RPC, Phase 1a) ----

    def run_cypher_read(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute an agent-supplied read-only Cypher query.

        ``assert_read_only`` is the syntactic guard; the Bolt session's
        ``default_access_mode='READ'`` is the server-side guard. Results
        are capped at ``self._max_rows`` so a runaway query cannot exhaust
        the agent context window or wire bandwidth.
        """
        assert_read_only(query)
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result.fetch(self._max_rows)]
