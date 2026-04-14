"""Unit tests for the scanner tools (Stage 1 of the vulnresearch pipeline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decepticon.tools.research import _state as state
from decepticon.tools.research.graph import KnowledgeGraph, NodeKind
from decepticon.tools.research.scanner_tools import (
    kg_add_candidate,
    rank_candidates,
    scan_shard,
)


class _FakeStore:
    def __init__(self) -> None:
        self.graph = KnowledgeGraph()

    def load_graph(self):
        return self.graph.model_copy(deep=True)

    def batch_upsert_nodes(self, nodes):
        for n in nodes:
            self.graph.upsert_node(n)
        return len(nodes)

    def batch_upsert_edges(self, edges):
        for e in edges:
            self.graph.upsert_edge(e)
        return len(edges)

    def ensure_schema(self):
        pass

    def close(self):
        pass

    def revision(self):
        return 0.0

    def stats(self):
        return self.graph.stats()

    def upsert_node(self, node):
        self.graph.upsert_node(node)

    def upsert_edge(self, edge):
        self.graph.upsert_edge(edge)


def _configure_kg(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(state, "_store", fake)
    return fake


def _seed_tree(root: Path) -> None:
    """Write a small polyglot corpus with known sinks and sources."""
    (root / "routes").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "vendor").mkdir()

    # Real candidate: http param → os.system  (unsanitized)
    (root / "routes" / "app.py").write_text(
        "from flask import request\n"
        "import os\n"
        "def ping():\n"
        "    host = request.args.get('host')\n"
        "    os.system(f'ping -c 1 {host}')\n"
    )
    # Another candidate: sql string-concat
    (root / "routes" / "search.py").write_text(
        "import sqlite3\n"
        "def search(q, cursor):\n"
        '    cursor.execute("SELECT * FROM products WHERE name=\'" + q + "\'")\n'
    )
    # Should be noise-filtered out by test/vendor pruning
    (root / "tests" / "test_noise.py").write_text(
        "import os\ndef test_thing():\n    os.system('echo hi')\n"
    )
    (root / "vendor" / "legacy.py").write_text(
        "import pickle\ndef load(x):\n    return pickle.loads(x)\n"
    )
    # Non-matching file
    (root / "README.md").write_text("# not scanned\n")


class TestScanShard:
    def test_single_shard_finds_candidates(self, tmp_path: Path) -> None:
        _seed_tree(tmp_path)
        raw = scan_shard.invoke(
            {"root": str(tmp_path), "shard_idx": 0, "shard_total": 1, "max_files": 100}
        )
        data = json.loads(raw)
        assert data["files_scanned"] >= 2
        # At least the app.py os.system hit and the search.py sql hit
        sink_kinds = {h["sink_kind"] for h in data["hits"]}
        assert "os_exec" in sink_kinds
        assert "sql" in sink_kinds

    def test_noise_dirs_pruned(self, tmp_path: Path) -> None:
        _seed_tree(tmp_path)
        raw = scan_shard.invoke(
            {"root": str(tmp_path), "shard_idx": 0, "shard_total": 1, "max_files": 100}
        )
        data = json.loads(raw)
        paths = [h["path"] for h in data["hits"]]
        assert not any("/tests/" in p for p in paths), "tests/ should be pruned"
        assert not any("/vendor/" in p for p in paths), "vendor/ should be pruned"

    def test_shard_fanout_covers_without_overlap(self, tmp_path: Path) -> None:
        # Larger corpus to get multiple files per shard
        for i in range(20):
            d = tmp_path / f"pkg{i}"
            d.mkdir()
            (d / f"mod{i}.py").write_text(f"import os\ndef f{i}(x):\n    os.system(x)\n")

        full = json.loads(
            scan_shard.invoke(
                {"root": str(tmp_path), "shard_idx": 0, "shard_total": 1, "max_files": 500}
            )
        )
        shards = [
            json.loads(
                scan_shard.invoke(
                    {
                        "root": str(tmp_path),
                        "shard_idx": i,
                        "shard_total": 4,
                        "max_files": 500,
                    }
                )
            )
            for i in range(4)
        ]
        total_files = sum(s["files_scanned"] for s in shards)
        assert total_files == full["files_scanned"], (
            f"shard coverage mismatch: union={total_files} full={full['files_scanned']}"
        )

        # Union of shard hits should equal full hits (same dedup key set).
        def _key(h: dict) -> tuple[str, int, str]:
            return (h["path"], h["line"], h["sink_kind"])

        full_keys = {_key(h) for h in full["hits"]}
        shard_keys: set[tuple[str, int, str]] = set()
        for s in shards:
            shard_keys.update(_key(h) for h in s["hits"])
        assert shard_keys == full_keys

    def test_bad_shard_idx_errors(self, tmp_path: Path) -> None:
        raw = scan_shard.invoke({"root": str(tmp_path), "shard_idx": 5, "shard_total": 4})
        assert "error" in json.loads(raw)

    def test_missing_root_errors(self) -> None:
        raw = scan_shard.invoke({"root": "/nonexistent/xyzzy", "shard_idx": 0, "shard_total": 1})
        assert "error" in json.loads(raw)


class TestRankCandidates:
    def test_dedupe_and_topk(self, tmp_path: Path) -> None:
        _seed_tree(tmp_path)
        shards = [
            json.loads(
                scan_shard.invoke(
                    {
                        "root": str(tmp_path),
                        "shard_idx": i,
                        "shard_total": 2,
                        "max_files": 100,
                    }
                )
            )
            for i in range(2)
        ]
        merged = json.loads(
            rank_candidates.invoke({"shard_results": json.dumps(shards), "top_k": 10})
        )
        assert merged["unique_hits"] >= 2
        # Sorted by score descending
        scores = [c["score"] for c in merged["candidates"]]
        assert scores == sorted(scores, reverse=True)

    def test_accepts_concatenated_blobs(self, tmp_path: Path) -> None:
        _seed_tree(tmp_path)
        s0 = scan_shard.invoke(
            {"root": str(tmp_path), "shard_idx": 0, "shard_total": 1, "max_files": 100}
        )
        # Pass a single blob — ranker should accept it
        merged = json.loads(rank_candidates.invoke({"shard_results": s0, "top_k": 5}))
        assert merged["total_hits"] > 0


class TestKgAddCandidate:
    def test_promotes_candidate_to_graph(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _configure_kg(monkeypatch)
        raw = kg_add_candidate.invoke(
            {
                "path": "/workspace/target/app.py",
                "line": 42,
                "score": 0.9,
                "sink_kind": "os_exec",
                "reason": "request.args → os.system",
            }
        )
        result = json.loads(raw)
        assert "id" in result
        assert result["kind"] == NodeKind.CANDIDATE.value
        assert result["severity"] == "high"

        graph = fake.load_graph()
        node = graph.nodes[result["id"]]
        assert node.props["path"] == "/workspace/target/app.py"
        assert node.props["line"] == 42
        assert node.props["status"] == "pending"

    def test_deterministic_dedup_by_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _configure_kg(monkeypatch)
        a = json.loads(
            kg_add_candidate.invoke(
                {
                    "path": "/workspace/target/app.py",
                    "line": 10,
                    "score": 0.7,
                    "sink_kind": "sql",
                }
            )
        )
        b = json.loads(
            kg_add_candidate.invoke(
                {
                    "path": "/workspace/target/app.py",
                    "line": 10,
                    "score": 0.9,
                    "sink_kind": "sql",
                }
            )
        )
        assert a["id"] == b["id"], "same (path,line,sink) should produce same node id"

    def test_severity_buckets(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _configure_kg(monkeypatch)
        hi = json.loads(
            kg_add_candidate.invoke(
                {"path": "a.py", "line": 1, "score": 0.95, "sink_kind": "os_exec"}
            )
        )
        md = json.loads(
            kg_add_candidate.invoke({"path": "b.py", "line": 1, "score": 0.70, "sink_kind": "sql"})
        )
        lo = json.loads(
            kg_add_candidate.invoke(
                {"path": "c.py", "line": 1, "score": 0.30, "sink_kind": "crypto"}
            )
        )
        assert hi["severity"] == "high"
        assert md["severity"] == "medium"
        assert lo["severity"] == "low"
