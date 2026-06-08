"""Unit tests for :mod:`kg_internal.migration_runner`.

Covers the statement splitter, ``list_applied`` against a fake store,
and the idempotent ``apply_migrations`` flow with multiple migration
files. Live-Neo4j verification lives in
``tests/integration/kg/test_migration_runner_live.py`` (PR-A.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from decepticon.middleware.kg_internal.migration_runner import (
    _MIGRATION_ENGAGEMENT,
    _split_cypher_statements,
    _strip_line_comments,
    apply_migrations,
    list_applied,
)
from decepticon.middleware.kg_internal.store import KGStore, KGStoreConfig

# ── _strip_line_comments / _split_cypher_statements ─────────────────────


def test_strip_line_comments_removes_double_dash_to_eol() -> None:
    text = "CREATE INDEX foo -- inline note\nFOR (n:Host) ON (n.ip);"
    out = _strip_line_comments(text)
    assert "inline note" not in out
    assert "CREATE INDEX foo" in out
    assert "FOR (n:Host)" in out


def test_strip_line_comments_handles_no_comments() -> None:
    text = "CREATE INDEX foo FOR (n:Host) ON (n.ip);"
    assert _strip_line_comments(text) == text


def test_split_cypher_strips_comments_and_splits() -> None:
    text = """
    -- Header comment
    CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;
    -- Inline note
    CREATE INDEX b IF NOT EXISTS FOR (n:Service) ON (n.engagement);
    """
    stmts = _split_cypher_statements(text)
    assert len(stmts) == 2
    assert stmts[0].startswith("CREATE CONSTRAINT a")
    assert stmts[1].startswith("CREATE INDEX b")


def test_split_cypher_drops_empty_statements() -> None:
    text = ";;CREATE INDEX a FOR (n:Host) ON (n.ip);;;"
    stmts = _split_cypher_statements(text)
    assert stmts == ["CREATE INDEX a FOR (n:Host) ON (n.ip)"]


def test_split_cypher_preserves_multiline_statements() -> None:
    text = """
    CREATE VECTOR INDEX v IF NOT EXISTS
      FOR (n:Vulnerability) ON (n.embedding)
      OPTIONS {
        indexConfig: {
          `vector.dimensions`: 1536
        }
      };
    """
    stmts = _split_cypher_statements(text)
    assert len(stmts) == 1
    assert "CREATE VECTOR INDEX v" in stmts[0]
    assert "OPTIONS" in stmts[0]
    assert "1536" in stmts[0]


# ── KGStore mock plumbing ───────────────────────────────────────────────


def _fake_driver() -> MagicMock:
    driver = MagicMock(name="Driver")
    session = MagicMock(name="Session")
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = None
    return driver


def _make_store(driver: Any | None = None) -> KGStore:
    cfg = KGStoreConfig(uri="bolt://x", user="u", password="p", database="neo4j")
    return KGStore(cfg, driver=driver or _fake_driver())


def _stub_store(
    *,
    applied_names: list[str] | None = None,
) -> tuple[KGStore, list[tuple[str, dict[str, Any], str]]]:
    """Build a KGStore whose execute_read/write record into a list.

    Returns ``(store, calls)`` where each call is a tuple of
    ``(cypher, params, engagement)``.
    """
    calls: list[tuple[str, dict[str, Any], str]] = []
    store = _make_store()

    applied = applied_names or []

    def fake_execute_read(
        cypher: str, params: dict[str, Any] | None = None, *, engagement: str
    ) -> list[dict[str, Any]]:
        calls.append((cypher, dict(params or {}), engagement))
        if "MATCH (m:MigrationLog)" in cypher:
            return [{"name": name} for name in applied]
        return []

    def fake_execute_write(
        cypher: str, params: dict[str, Any] | None = None, *, engagement: str
    ) -> list[dict[str, Any]]:
        calls.append((cypher, dict(params or {}), engagement))
        return []

    store.execute_read = fake_execute_read  # type: ignore[assignment]
    store.execute_write = fake_execute_write  # type: ignore[assignment]
    return store, calls


# ── list_applied ─────────────────────────────────────────────────────────


def test_list_applied_returns_empty_on_fresh_store() -> None:
    store, _calls = _stub_store(applied_names=[])
    assert list_applied(store) == set()


def test_list_applied_returns_recorded_names() -> None:
    store, calls = _stub_store(applied_names=["V001__initial_schema"])
    assert list_applied(store) == {"V001__initial_schema"}
    # The read must have scoped to the reserved engagement label.
    read_call = calls[0]
    assert read_call[2] == _MIGRATION_ENGAGEMENT


# ── apply_migrations ─────────────────────────────────────────────────────


def _write_migration(dir_path: Path, name: str, cypher: str) -> Path:
    path = dir_path / f"{name}.cypher"
    path.write_text(cypher, encoding="utf-8")
    return path


def test_apply_migrations_returns_empty_when_no_files(tmp_path: Path) -> None:
    store, _calls = _stub_store()
    assert apply_migrations(store, migrations_dir=tmp_path) == []


def test_apply_migrations_runs_pending_in_order(tmp_path: Path) -> None:
    _write_migration(
        tmp_path,
        "V001__a",
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;",
    )
    _write_migration(
        tmp_path,
        "V002__b",
        "CREATE INDEX b IF NOT EXISTS FOR (n:Service) ON (n.engagement);",
    )
    store, calls = _stub_store(applied_names=[])

    applied = apply_migrations(store, migrations_dir=tmp_path)
    assert applied == ["V001__a", "V002__b"]

    # The order of writes: list_applied read, then V001 statements, then
    # V001 MigrationLog upsert, then V002 statements, then V002
    # MigrationLog upsert.
    cyphers = [c for (c, _, _) in calls]
    assert any("CREATE CONSTRAINT a" in c for c in cyphers)
    assert any("CREATE INDEX b" in c for c in cyphers)
    log_writes = [c for c in cyphers if "MERGE (m:MigrationLog" in c]
    assert len(log_writes) == 2

    # All writes scoped to the reserved engagement label.
    for cypher, params, eng in calls:
        if cypher.startswith("MERGE (m:MigrationLog"):
            assert params["name"] in {"V001__a", "V002__b"}
        assert eng == _MIGRATION_ENGAGEMENT


def test_apply_migrations_skips_already_applied(tmp_path: Path) -> None:
    _write_migration(
        tmp_path, "V001__a", "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;"
    )
    _write_migration(
        tmp_path, "V002__b", "CREATE INDEX b IF NOT EXISTS FOR (n:Service) ON (n.engagement);"
    )
    store, calls = _stub_store(applied_names=["V001__a"])

    applied = apply_migrations(store, migrations_dir=tmp_path)
    assert applied == ["V002__b"]

    cyphers = [c for (c, _, _) in calls]
    # V001 statements must NOT have been executed.
    assert not any("CREATE CONSTRAINT a" in c for c in cyphers)
    # V002 statements MUST have been executed.
    assert any("CREATE INDEX b" in c for c in cyphers)


def test_apply_migrations_idempotent_re_run(tmp_path: Path) -> None:
    _write_migration(
        tmp_path, "V001__a", "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;"
    )
    # Second invocation simulates the runner discovering the same
    # migration already recorded.
    store, _calls = _stub_store(applied_names=["V001__a"])
    assert apply_migrations(store, migrations_dir=tmp_path) == []


def test_apply_migrations_records_cypher_sha_in_migration_log(tmp_path: Path) -> None:
    path = _write_migration(
        tmp_path,
        "V001__a",
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;",
    )
    import hashlib

    expected_sha = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    store, calls = _stub_store()
    apply_migrations(store, migrations_dir=tmp_path)

    log_calls = [(c, p) for (c, p, _e) in calls if c.startswith("MERGE (m:MigrationLog")]
    assert len(log_calls) == 1
    _cypher, params = log_calls[0]
    assert params["name"] == "V001__a"
    assert params["sha"] == expected_sha
    assert isinstance(params["now"], int) and params["now"] > 0


def test_apply_migrations_uses_reserved_schema_engagement(tmp_path: Path) -> None:
    _write_migration(
        tmp_path, "V001__a", "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:Host) REQUIRE n.k IS UNIQUE;"
    )
    store, calls = _stub_store()
    apply_migrations(store, migrations_dir=tmp_path)
    # Every recorded call must have the reserved engagement label.
    for _cypher, _params, eng in calls:
        assert eng == _MIGRATION_ENGAGEMENT
    # And that label MUST be valid per is_valid_engagement_label so
    # KGStore.execute_write doesn't reject it.
    from decepticon_core.utils.engagement_scope import is_valid_engagement_label

    assert is_valid_engagement_label(_MIGRATION_ENGAGEMENT)


# ── Shipped migrations exist and parse cleanly ──────────────────────────


def test_shipped_migrations_present_and_parseable() -> None:
    """The two migrations shipped with PR-A.3 must be loadable + non-empty."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    files = sorted(_DEFAULT_MIGRATIONS_DIR.glob("V*.cypher"))
    names = [p.stem for p in files]
    assert "V001__initial_schema" in names
    assert "V002__engagement_composite_indexes_and_provenance" in names
    for path in files:
        text = path.read_text(encoding="utf-8")
        stmts = _split_cypher_statements(text)
        assert stmts, f"{path.name} contains no executable statements"


def test_v001_creates_migration_log_constraint() -> None:
    """V001 must bootstrap the MigrationLog constraint so subsequent runs
    can record applied migrations."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    v001 = next(
        (_DEFAULT_MIGRATIONS_DIR / "V001__initial_schema.cypher").parent.glob("V001*.cypher")
    )
    text = v001.read_text(encoding="utf-8")
    assert "MigrationLog" in text
    assert "migration_log_name" in text


def test_v002_creates_vector_index_for_future_semantic_recall() -> None:
    """V002 must include the vector schema placeholder (Q5 = yes)."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    v002 = next(
        (_DEFAULT_MIGRATIONS_DIR).glob("V002__*.cypher"),
    )
    text = v002.read_text(encoding="utf-8")
    assert "CREATE VECTOR INDEX" in text
    assert "vuln_embedding" in text
    assert "1536" in text
    assert "cosine" in text


def test_v004_creates_technology_key_engagement_constraint() -> None:
    """V004 must enforce the ``(key, engagement)`` MERGE invariant for the
    Technology label (ADR-0007) so corroborating classifier writes dedup."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    v004 = next((_DEFAULT_MIGRATIONS_DIR).glob("V004__*.cypher"))
    text = v004.read_text(encoding="utf-8")
    stmts = _split_cypher_statements(text)
    assert any("(n:Technology)" in s and "(n.key, n.engagement) IS UNIQUE" in s for s in stmts), (
        "V004 must add the Technology (key, engagement) uniqueness constraint"
    )
    assert any("FOR (n:Technology) ON (n.engagement, n.category)" in s for s in stmts), (
        "V004 must add the engagement-scoped category index"
    )


# ── KGStore record_observations must not interfere with migration log ───


def test_migration_log_uses_distinct_label_from_canonical_nodes() -> None:
    """Sanity: the MigrationLog label must not collide with any of the
    canonical node labels listed in V001."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    v001 = (_DEFAULT_MIGRATIONS_DIR / "V001__initial_schema.cypher").read_text(encoding="utf-8")
    # Naive grep: every canonical node label appears as "FOR (n:Label)"
    # exactly once for the (key, engagement) constraint plus once at
    # the MigrationLog block. MigrationLog appears under a different
    # constraint (migration_log_name) — confirm the constraint name
    # does NOT shadow another label's constraint.
    assert "migration_log_name" in v001
    canonical_labels_with_key_engagement = [
        line for line in v001.splitlines() if "REQUIRE (n.key, n.engagement) IS UNIQUE" in line
    ]
    assert "MigrationLog" not in "\n".join(canonical_labels_with_key_engagement)


@pytest.mark.parametrize(
    "label",
    [
        "Host",
        "Service",
        "Vulnerability",
        "URL",
        "User",
        "Credential",
        "CVE",
        "Entrypoint",
        "CrownJewel",
        "AttackPath",
        "Finding",
    ],
)
def test_v001_constrains_high_traffic_labels(label: str) -> None:
    """The labels the analyst will write most often must be constrained
    so dedup MERGE is enforced engagement-scoped."""
    from decepticon.middleware.kg_internal.migration_runner import _DEFAULT_MIGRATIONS_DIR

    v001 = (_DEFAULT_MIGRATIONS_DIR / "V001__initial_schema.cypher").read_text(encoding="utf-8")
    assert f"FOR (n:{label})" in v001
