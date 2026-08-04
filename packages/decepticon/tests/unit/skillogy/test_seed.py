"""Unit test for the boot seed guard (``__main__._seed_if_empty``).

The skill graph is persistent, so the boot path must seed an empty
database exactly once and never re-run the corpus against a populated
one. These two cases are the whole contract.
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
    # Stop before the (network-bound) embedding backfill — the seed itself
    # is what this test covers.
    import decepticon.skillogy.embed_ingest as embed

    monkeypatch.setattr(embed, "ingest_embeddings", lambda backend: None)

    backend = _FakeBackend(skill_count=0)
    skillogy_main._seed_if_empty(backend)  # type: ignore[arg-type]
    assert len(backend.ingested) == 1  # empty graph → seeded exactly once
