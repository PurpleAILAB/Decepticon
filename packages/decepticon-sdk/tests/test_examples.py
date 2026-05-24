"""Smoke tests for the six example plugins under ``examples/``.

Closes spec §14 acceptance #8: each ``packages/decepticon-sdk/examples/*``
has a test that passes. The examples themselves are buildable PyPI-style
plugin packages (the scaffolder dogfoods itself by generating them).
This test only asserts the structural invariants — they're importable
modules with the expected entry-point group declarations, no live
framework integration required.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

KIND_TO_ENTRY_POINT_GROUP = {
    "tool": "decepticon.tools",
    "middleware": "decepticon.middleware",
    "agent": "decepticon.agents",
    "callback": "decepticon.callbacks",
    "skill": "decepticon.skills",
    "prompt": "decepticon.prompts",
}


@pytest.mark.parametrize("kind", sorted(KIND_TO_ENTRY_POINT_GROUP))
def test_example_layout(kind: str) -> None:
    """Each example has the expected pyproject + README + src/ tree."""
    example = EXAMPLES_DIR / kind
    assert example.is_dir(), f"missing example dir for kind={kind!r}"
    assert (example / "pyproject.toml").is_file()
    assert (example / "README.md").is_file()
    module_name = f"decepticon_example_{kind}"
    init = example / "src" / module_name / "__init__.py"
    assert init.is_file(), f"missing src module for {kind!r}"


@pytest.mark.parametrize("kind", sorted(KIND_TO_ENTRY_POINT_GROUP))
def test_example_declares_correct_entry_point_group(kind: str) -> None:
    """Each example's pyproject.toml wires the matching entry-point group."""
    example = EXAMPLES_DIR / kind
    data = tomllib.loads((example / "pyproject.toml").read_text())
    expected_group = KIND_TO_ENTRY_POINT_GROUP[kind]
    entry_points = data.get("project", {}).get("entry-points", {})
    assert expected_group in entry_points, (
        f"example {kind!r} missing entry-points.{expected_group}; got {sorted(entry_points)}"
    )
    # Module name matches kind: decepticon-example-tool -> decepticon_example_tool
    expected_module = f"decepticon_example_{kind}"
    group_entries = entry_points[expected_group]
    assert expected_module in group_entries, (
        f"example {kind!r} entry-point {expected_group} should reference "
        f"module {expected_module!r}; got {sorted(group_entries)}"
    )


@pytest.mark.parametrize("kind", sorted(KIND_TO_ENTRY_POINT_GROUP))
def test_example_module_is_importable_syntactically(kind: str) -> None:
    """Each generated __init__.py compiles cleanly under py3.13."""
    import ast

    module_name = f"decepticon_example_{kind}"
    init = EXAMPLES_DIR / kind / "src" / module_name / "__init__.py"
    source = init.read_text()
    # Compile-checking the AST avoids actually executing plugin
    # imports (which require the framework runtime for some kinds).
    ast.parse(source, filename=str(init))
