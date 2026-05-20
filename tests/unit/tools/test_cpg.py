"""Unit tests for the white-box CPG agent's tooling.

Covers:
- Language inventory walks
- AST parse (regex fallback path)
- Source / sink dictionary discovery
- AST-mode reachability heuristic
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decepticon.tools.cpg import (
    cpg_find_sinks,
    cpg_find_sources,
    cpg_inventory_languages,
    cpg_parse_tree,
    cpg_reaches,
)


# ── Inventory ─────────────────────────────────────────────────────────


def test_inventory_detects_python_and_js(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def f(): pass\n")
    (tmp_path / "util.py").write_text("def g(): pass\n")
    (tmp_path / "front.js").write_text("function h(){}\n")
    out = cpg_inventory_languages(tmp_path)
    assert "python" in out
    assert "javascript" in out
    assert out["python"]["file_count"] == 2
    assert out["javascript"]["file_count"] == 1
    # Python wins on file count → primary
    assert out["python"]["primary"] is True
    assert out["javascript"]["primary"] is False


def test_inventory_skips_vendored(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("pass\n")
    nm = tmp_path / "node_modules" / "lodash"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n")
    out = cpg_inventory_languages(tmp_path, skip_vendored=True)
    assert "python" in out
    assert "javascript" not in out


def test_inventory_includes_vendored_when_disabled(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("pass\n")
    nm = tmp_path / "vendor"
    nm.mkdir()
    (nm / "x.go").write_text("package x\n")
    out = cpg_inventory_languages(tmp_path, skip_vendored=False)
    assert "go" in out


# ── Parse ─────────────────────────────────────────────────────────────


def test_parse_python_regex_fallback(tmp_path: Path) -> None:
    src = """
def handler(req):
    name = req.args.get('name')
    cursor.execute("SELECT * FROM u WHERE n='" + name + "'")
    return name

def other(x):
    return x + 1
"""
    p = tmp_path / "h.py"
    p.write_text(src)
    res = cpg_parse_tree(p)
    assert res["language"] == "python"
    fn_names = [f["name"] for f in res["functions"]]
    assert "handler" in fn_names
    assert "other" in fn_names


def test_parse_unknown_language(tmp_path: Path) -> None:
    p = tmp_path / "x.weird"
    p.write_text("blob\n")
    res = cpg_parse_tree(p)
    assert res["language"] == "unknown"
    assert res["functions"] == []


# ── Sources / sinks ───────────────────────────────────────────────────


def test_find_sources_python_http(tmp_path: Path) -> None:
    src = """
def handler(req):
    name = request.args.get('name')
    return name
"""
    p = tmp_path / "h.py"
    p.write_text(src)
    sources = cpg_find_sources(p, "python")
    assert any(s["kind"] == "http_param" for s in sources)


def test_find_sinks_python_sql_exec(tmp_path: Path) -> None:
    src = """
def lookup(name):
    cursor.execute("SELECT * FROM u WHERE n='" + name + "'")
"""
    p = tmp_path / "h.py"
    p.write_text(src)
    sinks = cpg_find_sinks(p, "python")
    assert any(s["kind"] == "sql_exec" for s in sinks)


def test_find_sinks_python_shell_exec(tmp_path: Path) -> None:
    src = """
def run(cmd):
    os.system(cmd)
"""
    p = tmp_path / "h.py"
    p.write_text(src)
    sinks = cpg_find_sinks(p, "python")
    assert any(s["kind"] == "shell_exec" for s in sinks)


def test_find_sources_empty_for_unknown_language(tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_text("def f(): pass\n")
    assert cpg_find_sources(p, "esoteric-lang") == []
    assert cpg_find_sinks(p, "esoteric-lang") == []


# ── Reachability ──────────────────────────────────────────────────────


def test_reaches_same_function_returns_reachable() -> None:
    src = {"file": "/x.py", "line": 10, "kind": "http_param", "sigil": "request.args.get", "function": "handler", "role": "source", "confidence": 0.65}
    sink = {"file": "/x.py", "line": 12, "kind": "sql_exec", "sigil": "cursor.execute", "function": "handler", "role": "sink", "confidence": 0.65}
    r = cpg_reaches(src, sink)
    assert r["reachable"] is True
    assert r["engine"] == "ast"
    assert len(r["path"]) == 2


def test_reaches_different_functions_returns_unreachable() -> None:
    src = {"file": "/x.py", "line": 10, "kind": "http_param", "sigil": "request.args.get", "function": "a", "role": "source", "confidence": 0.65}
    sink = {"file": "/x.py", "line": 22, "kind": "sql_exec", "sigil": "cursor.execute", "function": "b", "role": "sink", "confidence": 0.65}
    r = cpg_reaches(src, sink)
    assert r["reachable"] is False


def test_end_to_end_python_sqli_pattern(tmp_path: Path) -> None:
    src = """
def handler(req):
    name = request.args.get('name')
    cursor.execute("SELECT * FROM u WHERE n='" + name + "'")
"""
    p = tmp_path / "h.py"
    p.write_text(src)
    sources = cpg_find_sources(p, "python")
    sinks = cpg_find_sinks(p, "python")
    # at least one source + one sink in handler()
    in_handler = [s for s in sources if s["function"] == "handler"]
    sk_handler = [s for s in sinks if s["function"] == "handler"]
    assert in_handler and sk_handler
    r = cpg_reaches(in_handler[0], sk_handler[0])
    assert r["reachable"] is True


# ── Dictionary load smoke ─────────────────────────────────────────────


@pytest.mark.parametrize("lang", ["python", "javascript", "typescript", "go", "java", "c"])
def test_dictionaries_load(lang: str) -> None:
    from decepticon.tools.cpg.taint import _load_dictionary  # type: ignore[reportPrivateUsage]
    d = _load_dictionary(lang)
    assert d is not None
    assert d.sources
    assert d.sinks
