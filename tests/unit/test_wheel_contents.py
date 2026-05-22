import glob
import subprocess
import zipfile
from pathlib import Path

import pytest


@pytest.mark.slow
def test_wheel_bundles_skills_but_excludes_benchmark(tmp_path):
    # Build the wheel with the project's backend (hatchling) via `uv build`
    # and assert the published artifact carries the standard/shared/plugins
    # skill trees as package data while excluding the benchmark eval-harness
    # skills. Marked slow: it shells out to a real build.
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=repo_root,
        check=True,
    )
    whl = sorted(glob.glob(str(tmp_path / "*.whl")))[-1]
    names = zipfile.ZipFile(whl).namelist()

    assert any(n.startswith("decepticon/skills/standard/") for n in names), (
        "standard skills missing from wheel"
    )
    assert any(n.startswith("decepticon/skills/shared/") for n in names), (
        "shared skills missing from wheel"
    )
    assert any(n.startswith("decepticon/skills/plugins/") for n in names), (
        "plugins skills missing from wheel"
    )
    assert not any(n.startswith("decepticon/skills/benchmark/") for n in names), (
        "benchmark skills must be excluded from the wheel"
    )
