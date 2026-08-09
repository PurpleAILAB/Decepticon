from __future__ import annotations

import json
from pathlib import Path

from decepticon.tools.research.tools import (
    _dependency_chains,
    _dependency_provenance,
    _manifest_path,
)


def test_dependency_evidence_uses_workspace_relative_manifest_path(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest = workspace / "requirements.txt"
    manifest.write_text("flask==2.0.0\n", encoding="utf-8")
    monkeypatch.setenv("DECEPTICON_WORKSPACE_PATH", str(workspace))

    assert _manifest_path(manifest) == "requirements.txt"
    assert _manifest_path(tmp_path / "outside.txt") is None
    assert _dependency_provenance(
        ("flask", "2.0.0", "PyPI"), manifest_path="requirements.txt", chains={}
    ) == {
        "reachability_level": "declared",
        "dependency_chain": ["flask@2.0.0"],
        "manifest_path": "requirements.txt",
    }


def test_dependency_evidence_preserves_nested_npm_chain(tmp_path: Path) -> None:
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/parent": {"name": "parent", "version": "1.0.0"},
                    "node_modules/parent/node_modules/child": {
                        "name": "child",
                        "version": "2.0.0",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    chains = _dependency_chains(lock)

    assert chains[("child", "2.0.0", "npm")] == ["parent", "child"]
