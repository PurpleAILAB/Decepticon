"""Unit tests for the boot seed and embedding orchestration.

The skill graph is persistent, so the boot path must seed an empty
database exactly once and never re-run the corpus against a populated
one, while the embedding backfill runs on every boot.
"""

from __future__ import annotations

from decepticon.skillogy import __main__ as skillogy_main


class _FakeBackend:
    def __init__(self, skill_count: int) -> None:
        self._skill_count = skill_count
        self.ingested: list[str] = []

    def health(self) -> dict:
        return {"status": "ok", "skill_count": self._skill_count}

    def bulk_ingest_cypher(self, cypher_text: str) -> int:
        self.ingested.append(cypher_text)
        return cypher_text.count(";")


def test_seed_skipped_when_graph_already_populated() -> None:
    backend = _FakeBackend(skill_count=326)
    skillogy_main._seed_if_empty(backend)  # type: ignore[arg-type]
    assert backend.ingested == []  # a populated graph is never re-seeded


def test_seed_runs_once_when_graph_empty(monkeypatch, tmp_path) -> None:
    cypher = tmp_path / "skills.cypher"
    cypher.write_text("MERGE (n:Skill {name: 'x'});\n", encoding="utf-8")
    monkeypatch.setenv("SKILLOGY_CYPHER_PATH", str(cypher))

    backend = _FakeBackend(skill_count=0)
    skillogy_main._seed_if_empty(backend)  # type: ignore[arg-type]
    assert len(backend.ingested) == 1  # empty graph → seeded exactly once


def test_embedding_backfill_runs_when_graph_is_populated(monkeypatch) -> None:
    calls: list[object] = []
    import decepticon.skillogy.embed_ingest as embed

    monkeypatch.setattr(embed, "ingest_embeddings", lambda backend: calls.append(backend))

    backend = _FakeBackend(skill_count=326)
    skillogy_main._ingest_in_background(backend)  # type: ignore[arg-type]
    assert calls == [backend]


def test_seed_failure_does_not_suppress_embedding_backfill(monkeypatch, tmp_path) -> None:
    cypher = tmp_path / "skills.cypher"
    cypher.write_text("MERGE (n:Skill {name: 'x'});\n", encoding="utf-8")
    monkeypatch.setenv("SKILLOGY_CYPHER_PATH", str(cypher))

    calls: list[object] = []
    import decepticon.skillogy.embed_ingest as embed

    monkeypatch.setattr(embed, "ingest_embeddings", lambda backend: calls.append(backend))

    backend = _FakeBackend(skill_count=0)

    def fail_bulk_ingest(_cypher_text: str) -> int:
        raise RuntimeError("seed unavailable")

    backend.bulk_ingest_cypher = fail_bulk_ingest  # type: ignore[method-assign]
    skillogy_main._ingest_in_background(backend)  # type: ignore[arg-type]
    assert calls == [backend]
