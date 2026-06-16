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

    # ---- vector index + embedding backfill (hybrid retrieval, ADR-0011) ----

    # Native Neo4j vector index over the per-skill embedding. Created
    # idempotently at boot AFTER the cypher dump loads; embeddings are
    # then backfilled through the litellm proxy (the dump stays embedding-
    # free so a model swap is a re-embed, not a rebuild). The query side
    # (find_skill) uses this index for the semantic-local leg of the
    # hybrid score, and silently skips it when no embeddings exist.
    VECTOR_INDEX_NAME = "skill_embedding"

    def ensure_vector_index(self, dim: int) -> None:
        """Create the ``:Skill(embedding)`` vector index if absent (idempotent).

        ``dim`` is inlined as a literal — Neo4j does not accept a query
        parameter for ``vector.dimensions`` in index DDL. It is coerced to
        ``int`` first so the f-string cannot carry an injection.
        """
        dim_literal = int(dim)
        cypher = (
            f"CREATE VECTOR INDEX {self.VECTOR_INDEX_NAME} IF NOT EXISTS "
            "FOR (s:Skill) ON (s.embedding) "
            "OPTIONS {indexConfig: {"
            f"`vector.dimensions`: {dim_literal}, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        with self._driver.session(database=self._database) as session:
            session.run(cypher)

    def fetch_skills_for_embedding(self) -> list[dict[str, Any]]:
        """Return the text fields each skill is embedded from, plus the sha of
        the input that produced its current embedding (``None`` if never
        embedded). The caller re-embeds only rows whose recomputed input sha
        differs — so a content edit re-embeds, an unchanged corpus is a no-op.
        """
        cypher = (
            "MATCH (s:Skill) "
            "RETURN s.path AS path, s.name AS name, "
            "       coalesce(s.description, '') AS description, "
            "       coalesce(s.when_to_use, '') AS when_to_use, "
            "       s.embedding_input_sha256 AS embedding_input_sha256"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            return [dict(record) for record in session.run(cypher)]

    def write_embeddings(self, rows: list[dict[str, Any]]) -> int:
        """Persist embeddings onto their ``:Skill`` nodes.

        Each row is ``{"path": str, "vector": list[float], "sha": str}``.
        Uses ``db.create.setNodeVectorProperty`` (the supported way to store a
        vector so the index picks it up) and records the input sha so the next
        boot can skip unchanged skills. Returns the number of nodes written.
        """
        if not rows:
            return 0
        cypher = (
            "UNWIND $rows AS row "
            "MATCH (s:Skill {path: row.path}) "
            "CALL db.create.setNodeVectorProperty(s, 'embedding', row.vector) "
            "SET s.embedding_input_sha256 = row.sha "
            "RETURN count(s) AS written"
        )
        with self._driver.session(database=self._database) as session:
            result = session.run(cypher, rows=rows).single()
        return 0 if result is None else int(result["written"])

    # ---- skill ops ----

    def load_skill(
        self,
        path: str,
        *,
        allowed_path_prefixes: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Fetch one ``:Skill`` node by canonical path OR unique frontmatter
        name. Returns its full property dict, or ``None`` if no such skill
        exists.

        Agents routinely pass a skill ``name`` (the field ``find_skill``
        surfaces most prominently — e.g. ``load_skill("oauth")``), not the
        ``/skills/.../SKILL.md`` path. A path-only match silently returned
        ``None`` for every name, which forced a fragile client-side
        ``find_skill`` fallback that the mixed APT + web skill corpus
        pollutes (``"oauth"``/``"ssrf"`` never resolved while ``"sqli"`` did,
        purely by which name happened to win the polluted keyword search).
        Match by exact ``path`` first (always unique), then fall back to an
        exact ``name`` match.

        When ``allowed_path_prefixes`` is non-empty, the **resolved** skill's
        path must be under a listed prefix, else ``None`` (the same shape the
        agent sees for a genuinely missing skill — ADR-0008). The check is
        applied AFTER resolution: a bare name has no prefix of its own, so
        gating on the *input* would reject every name-based load. ``None`` /
        empty list preserves the unrestricted behaviour for the standalone
        library, the skillogy CLI, and pytest, where no role context exists.
        """
        query = (
            "MATCH (s:Skill) WHERE s.path = $arg OR s.name = $arg "
            "RETURN properties(s) AS props "
            "ORDER BY CASE WHEN s.path = $arg THEN 0 ELSE 1 END "
            "LIMIT 1"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            result = session.run(query, arg=path).single()
        if result is None:
            return None
        props = dict(result["props"])
        if allowed_path_prefixes and not _path_under_any_prefix(
            str(props.get("path", "")), allowed_path_prefixes
        ):
            return None
        return props

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
        """Relationship-aware skill discovery — hybrid retrieval (ADR-0011).

        The structured filters are hard AND constraints; each prunes the
        candidate set via a different edge:

        - ``subdomain``: ``(s:Skill)-[:IN_PHASE]->(:Phase {name: $sub})``.
        - ``mitre_id``: ``(s:Skill)-[:IMPLEMENTS]->(:Technique {id: $id})``
          where ``$id`` can be a top-level T1xxx or a sub-T1xxx.yyy.
        - ``tag``: ``(s:Skill)-[:TAGGED]->(:Tag {name: $tag})``.
        - ``tactic_id``: anchors on a Tactic, follows ``HAS_TECHNIQUE`` to
          its techniques, then back to skills via ``IMPLEMENTS``.

        ``query`` (free text) drives **ranking** via two legs fused with
        reciprocal-rank fusion:

        - *lexical* — substring match on name / description / when_to_use
          (the legacy signal; exact for keywords like "kerberoast").
        - *semantic* — cosine k-NN over the per-skill embedding vector
          index, so a paraphrase ("steal kerberos tickets") finds the skill
          even with no shared substring.

        The semantic leg is **opt-in**: when no embeddings exist (the
        litellm proxy is unconfigured, or the corpus was never embedded),
        ``find_skill`` returns the pure lexical result, name-ordered —
        byte-for-byte the pre-ADR-0011 behaviour. The structured-only path
        (no ``query``) is likewise unchanged.

        Returns each match's ``name``, ``path``, ``subdomain``,
        ``description`` and the matched dimensions (``matched_mitre``,
        ``matched_tags``) so the agent can see *why* a skill came back.
        """
        from decepticon.skillogy import embeddings  # noqa: PLC0415

        limit = int(min(max(limit, 1), 100))
        # Over-fetch from each leg so reciprocal-rank fusion has signal to
        # work with before the final top-``limit`` cut.
        cand_n = min(max(limit * 3, 30), 100)

        # Structured (edge) filters — shared verbatim by both legs.
        structured: list[str] = []
        shared: dict[str, Any] = {}
        if subdomain:
            structured.append("(s)-[:IN_PHASE]->(:Phase {name: $subdomain})")
            shared["subdomain"] = subdomain
        if tag:
            structured.append("(s)-[:TAGGED]->(:Tag {name: $tag})")
            shared["tag"] = tag
        if mitre_id:
            structured.append("(s)-[:IMPLEMENTS]->(:Technique {id: $mitre_id})")
            shared["mitre_id"] = mitre_id
        if tactic_id:
            structured.append(
                "(s)-[:IMPLEMENTS]->(:Technique)<-[:HAS_TECHNIQUE]-(:Tactic {id: $tactic_id})"
            )
            shared["tactic_id"] = tactic_id
        # Per-role path-prefix ACL (ADR-0008) — applied identically to both
        # legs. Empty/missing leaves both unrestricted (CLI / pytest / lib).
        acl_clause: str | None = None
        if allowed_path_prefixes:
            acl_clause = "ANY(p IN $allowed_path_prefixes WHERE s.path STARTS WITH p)"
            shared["allowed_path_prefixes"] = list(allowed_path_prefixes)

        if not query and not structured:
            raise ValueError(
                "find_skill requires at least one of: query, subdomain, mitre_id, tag, tactic_id"
            )

        lexical = self._find_lexical(query, structured, acl_clause, shared, cand_n)

        # Semantic leg only when there is free text AND it can be embedded.
        query_vec = embeddings.embed_text(query) if query else None
        if query_vec is None:
            return lexical[:limit]

        semantic = self._find_semantic(query_vec, structured, acl_clause, shared, cand_n)
        return self._rrf_fuse(lexical, semantic, limit)

    # Shared RETURN tail so the lexical and semantic legs yield identical row
    # shapes (``score`` is appended by the semantic leg only and stripped at
    # fusion time).
    _ENRICH_TAIL = (
        "OPTIONAL MATCH (s)-[:IMPLEMENTS]->(t:Technique) OPTIONAL MATCH (s)-[:TAGGED]->(tg:Tag) "
    )
    _RETURN_FIELDS = (
        "s.name AS name, s.path AS path, s.subdomain AS subdomain, "
        "s.description AS description, matched_mitre, matched_tags"
    )

    def _find_lexical(
        self,
        query: str | None,
        structured: list[str],
        acl_clause: str | None,
        shared: dict[str, Any],
        cand_n: int,
    ) -> list[dict[str, Any]]:
        """Substring + structured leg. Name-ordered (stable, legacy order)."""
        wheres = list(structured)
        params = dict(shared)
        params["cand_n"] = cand_n
        if query:
            wheres.append(
                "(toLower(s.name) CONTAINS toLower($query) "
                "OR toLower(s.description) CONTAINS toLower($query) "
                "OR toLower(s.when_to_use) CONTAINS toLower($query))"
            )
            params["query"] = query
        if acl_clause:
            wheres.append(acl_clause)
        cypher = (
            "MATCH (s:Skill) "
            f"WHERE {' AND '.join(wheres)} "
            f"{self._ENRICH_TAIL}"
            "WITH s, collect(DISTINCT t.id) AS matched_mitre, "
            "     collect(DISTINCT tg.name) AS matched_tags "
            f"RETURN {self._RETURN_FIELDS} "
            "ORDER BY name "
            "LIMIT $cand_n"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            return [dict(record) for record in session.run(cypher, parameters=params)]

    def _find_semantic(
        self,
        query_vec: list[float],
        structured: list[str],
        acl_clause: str | None,
        shared: dict[str, Any],
        cand_n: int,
    ) -> list[dict[str, Any]]:
        """Vector k-NN leg over the ``:Skill(embedding)`` index, score-ordered.

        ``db.index.vector.queryNodes`` cannot pre-apply the structured /
        ACL predicates, so we over-fetch ``k`` neighbours and filter after —
        ``k`` is widened when filters are present since many neighbours will
        be dropped.
        """
        post_filters = list(structured)
        if acl_clause:
            post_filters.append(acl_clause)
        k = min(cand_n * 5, 500) if post_filters else cand_n
        params = dict(shared)
        params.update(
            {"index_name": self.VECTOR_INDEX_NAME, "k": k, "qvec": query_vec, "cand_n": cand_n}
        )
        where = f"WHERE {' AND '.join(post_filters)} " if post_filters else ""
        cypher = (
            "CALL db.index.vector.queryNodes($index_name, $k, $qvec) "
            "YIELD node AS s, score "
            f"{where}"
            f"{self._ENRICH_TAIL}"
            "WITH s, score, collect(DISTINCT t.id) AS matched_mitre, "
            "     collect(DISTINCT tg.name) AS matched_tags "
            f"RETURN {self._RETURN_FIELDS}, score "
            "ORDER BY score DESC "
            "LIMIT $cand_n"
        )
        with self._driver.session(database=self._database, default_access_mode="READ") as session:
            return [dict(record) for record in session.run(cypher, parameters=params)]

    @staticmethod
    def _rrf_fuse(
        lexical: list[dict[str, Any]],
        semantic: list[dict[str, Any]],
        limit: int,
        *,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Reciprocal-rank fusion of the two ranked legs, keyed by skill path.

        Each leg contributes ``1 / (rrf_k + rank)`` to a skill's score; a
        skill found by both legs ranks above one found by either alone. Ties
        break on name for deterministic output. ``rrf_k`` is the standard
        rank-smoothing constant (60).
        """
        scores: dict[str, float] = {}
        record_by_path: dict[str, dict[str, Any]] = {}
        for leg in (lexical, semantic):
            for rank, rec in enumerate(leg):
                path = rec["path"]
                record_by_path.setdefault(path, rec)
                scores[path] = scores.get(path, 0.0) + 1.0 / (rrf_k + rank + 1)
        ordered = sorted(
            record_by_path.values(),
            key=lambda r: (-scores[r["path"]], r.get("name") or ""),
        )
        return [{k: v for k, v in r.items() if k != "score"} for r in ordered[:limit]]

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
