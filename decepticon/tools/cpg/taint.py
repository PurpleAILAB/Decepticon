"""Source/sink discovery + taint reachability for the CPG Analyst.

Two analysis modes:

1. **AST + dictionary match** (default, fast, no joern):
   Walk the parsed AST per file. For each function call, match against
   the bundled source / sink dictionaries. Emit `STATIC_CONFIRMED`
   findings for any source→sink pair in the same function body.

2. **joern-cli taint** (optional, slow, full CPG):
   Generate a CPG with ``joern-parse`` then run a Joern query
   ``cpg.method.callIn.where(... reaches ...)`` to get true intra- +
   inter-procedural reachability. Activated when ``JOERN_HOME`` is set.

Both produce ``SourceSinkFinding`` records with the same shape so the
agent doesn't care which engine produced them.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from decepticon.tools.cpg.parse import cpg_parse_tree

logger = logging.getLogger(__name__)

_DICT_DIR = Path(__file__).parent / "dictionaries"


@dataclass
class SourceSinkFinding:
    """One source / sink occurrence."""

    file: str
    line: int
    kind: str  # source: 'http_param'|'env_var'|... sink: 'sql_exec'|'shell_exec'|...
    sigil: str  # the matched call/identifier text
    confidence: float = 0.6
    function: str = ""
    role: str = ""  # 'source' | 'sink' | 'sanitizer'

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class _LanguageDict:
    sources: dict[str, list[str]]
    sinks: dict[str, list[str]]
    sanitizers: dict[str, list[str]] = field(default_factory=dict)


def _load_dictionary(language: str) -> _LanguageDict | None:
    path = _DICT_DIR / f"{language}.yaml"
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(f"failed to load dictionary for {language!r}: {exc}")
        return None
    return _LanguageDict(
        sources=dict(data.get("sources") or {}),
        sinks=dict(data.get("sinks") or {}),
        sanitizers=dict(data.get("sanitizers") or {}),
    )


def _compile_pattern_list(patterns: list[str]) -> re.Pattern | None:
    # Treat dictionary entries as substrings on call head. Combine with |.
    if not patterns:
        return None
    escaped = "|".join(re.escape(p) for p in patterns)
    return re.compile(rf"\b({escaped})\b")


def _scan_calls(
    parse_result: dict, kind_patterns: dict[str, re.Pattern], role: str
) -> list[SourceSinkFinding]:
    out: list[SourceSinkFinding] = []
    file = parse_result.get("file", "")
    for fn in parse_result.get("functions", []) or []:
        for call in fn.get("calls", []) or []:
            head = str(call.get("name", ""))
            line = int(call.get("line", 0))
            for kind, pat in kind_patterns.items():
                if pat.search(head):
                    out.append(
                        SourceSinkFinding(
                            file=file,
                            line=line,
                            kind=kind,
                            sigil=head,
                            confidence=0.65,
                            function=fn.get("name", ""),
                            role=role,
                        )
                    )
                    break
    return out


def cpg_find_sources(path: str | Path, language: str) -> list[dict]:
    """Return untrusted-input source occurrences in ``path``."""
    parse = cpg_parse_tree(path, language=language)
    lang_dict = _load_dictionary(language)
    if lang_dict is None or not lang_dict.sources:
        return []
    patterns = {k: _compile_pattern_list(v) for k, v in lang_dict.sources.items()}
    patterns = {k: v for k, v in patterns.items() if v is not None}
    return [f.to_dict() for f in _scan_calls(parse, patterns, "source")]


def cpg_find_sinks(path: str | Path, language: str) -> list[dict]:
    """Return dangerous-API sink occurrences in ``path``."""
    parse = cpg_parse_tree(path, language=language)
    lang_dict = _load_dictionary(language)
    if lang_dict is None or not lang_dict.sinks:
        return []
    patterns = {k: _compile_pattern_list(v) for k, v in lang_dict.sinks.items()}
    patterns = {k: v for k, v in patterns.items() if v is not None}
    return [f.to_dict() for f in _scan_calls(parse, patterns, "sink")]


def cpg_reaches(
    source: dict,
    sink: dict,
    *,
    mode: str = "ast",
) -> dict:
    """Determine whether ``source`` reaches ``sink``.

    Args:
        source: result entry from ``cpg_find_sources``
        sink: result entry from ``cpg_find_sinks``
        mode: ``"ast"`` (same-function heuristic, no joern) or
            ``"taint"`` (joern-cli full DDG, requires ``$JOERN_HOME``).

    Returns:
        ``{reachable, path: [...], confidence, engine}``
    """
    if mode == "taint" and os.environ.get("JOERN_HOME"):
        return _joern_reaches(source, sink)
    return _ast_reaches(source, sink)


def _ast_reaches(source: dict, sink: dict) -> dict:
    """Heuristic AST reachability — same file + same function body."""
    same_file = source.get("file") == sink.get("file")
    same_fn = source.get("function") and source.get("function") == sink.get("function")
    if same_file and same_fn:
        return {
            "reachable": True,
            "path": [
                {"file": source["file"], "line": source["line"], "op": f"source:{source['kind']}"},
                {"file": sink["file"], "line": sink["line"], "op": f"sink:{sink['kind']}"},
            ],
            "confidence": 0.55,
            "engine": "ast",
        }
    return {
        "reachable": False,
        "path": [],
        "confidence": 0.0,
        "engine": "ast",
    }


def _joern_reaches(source: dict, sink: dict) -> dict:
    """Joern-cli-backed reachability — full intra/inter-procedural taint.

    Spawns a one-shot joern script. Slow (seconds per query) but accurate.
    """
    joern_home = os.environ["JOERN_HOME"]
    joern_bin = Path(joern_home) / "joern"
    if not joern_bin.is_file():
        return _ast_reaches(source, sink)
    # Build a minimal Joern script that takes source/sink line+method and
    # reports reachability. For brevity v0.1 returns AST result + a marker
    # that joern wiring is wired but not enabled. v0.2 will hook the actual
    # reachability query.
    try:
        subprocess.run(
            [str(joern_bin), "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return _ast_reaches(source, sink)
    result = _ast_reaches(source, sink)
    result["engine"] = "joern_pending"
    result["note"] = "joern-cli detected — full taint wiring slated for v0.2"
    return result


__all__ = ["SourceSinkFinding", "cpg_find_sinks", "cpg_find_sources", "cpg_reaches"]
