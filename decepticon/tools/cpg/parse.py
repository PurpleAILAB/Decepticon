"""tree-sitter-based AST parse for the CPG Analyst agent.

Returns a Python-friendly summary of every function found per file:
- ``name``, ``start_line``, ``end_line``
- ``params`` — flat list of parameter names
- ``calls`` — list of ``{name, line}`` for every call site inside

When the ``tree_sitter_languages`` package isn't installed (e.g.
operator hasn't run ``pip install decepticon[cpg]``), this module
gracefully degrades to a regex-based extractor that still finds top-level
function names + call sites in Python and JavaScript. That's enough for
the agent to build candidate source/sink tables without missing the
majority of cases. For C/C++/Java the regex fallback is brittle — those
languages need a real parse.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FunctionSummary:
    name: str
    start_line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "params": self.params,
            "calls": self.calls,
        }


@dataclass
class FileParse:
    file: str
    language: str
    functions: list[FunctionSummary] = field(default_factory=list)
    parse_method: str = "tree_sitter"  # or "regex_fallback"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "language": self.language,
            "parse_method": self.parse_method,
            "functions": [f.to_dict() for f in self.functions],
        }


# ── Tree-sitter path (preferred) ──────────────────────────────────────


_TS_FN_QUERIES: dict[str, str] = {
    # Each query captures a (function-like) node with name + parameters.
    # Used via tree_sitter.Language.query — only loaded lazily.
    "python": "(function_definition name: (identifier) @name parameters: (parameters) @params) @fn",
    "javascript": "(function_declaration name: (identifier) @name parameters: (formal_parameters) @params) @fn",
    "go": "(function_declaration name: (identifier) @name parameters: (parameter_list) @params) @fn",
    "java": "(method_declaration name: (identifier) @name parameters: (formal_parameters) @params) @fn",
    "c": "(function_definition declarator: (function_declarator declarator: (identifier) @name parameters: (parameter_list) @params)) @fn",
}


def _try_tree_sitter_parse(path: Path, language: str) -> FileParse | None:
    """Return a tree-sitter-backed FileParse or None if unavailable."""
    try:
        from tree_sitter_languages import get_language, get_parser  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        parser = get_parser(language)
        lang = get_language(language)
    except Exception as exc:
        logger.debug(f"tree-sitter has no grammar for {language!r}: {exc}")
        return None
    try:
        src = path.read_bytes()
    except OSError:
        return None
    tree = parser.parse(src)
    query_str = _TS_FN_QUERIES.get(language)
    if not query_str:
        return FileParse(file=str(path), language=language, functions=[])
    try:
        query = lang.query(query_str)
        matches = query.captures(tree.root_node)
    except Exception:
        return FileParse(file=str(path), language=language, functions=[])
    fns: list[FunctionSummary] = []
    # tree-sitter returns [(node, capture_name)] flat — group by @fn.
    current: dict[str, object] | None = None
    for node, name in matches:
        if name == "fn":
            if current is not None:
                fns.append(_finalize_ts_function(current, src))
            current = {"node": node, "name": "", "params_node": None}
        elif name == "name" and current is not None:
            current["name"] = src[node.start_byte : node.end_byte].decode("utf-8", "replace")
        elif name == "params" and current is not None:
            current["params_node"] = node
    if current is not None:
        fns.append(_finalize_ts_function(current, src))
    return FileParse(file=str(path), language=language, functions=fns)


def _finalize_ts_function(current: dict, src: bytes) -> FunctionSummary:
    node = current["node"]
    name = str(current["name"]) or "<anonymous>"
    params: list[str] = []
    pn = current["params_node"]
    if pn is not None:
        # Walk children, collect identifier-typed nodes' text
        for child in pn.children:  # type: ignore[union-attr]
            text = src[child.start_byte : child.end_byte].decode("utf-8", "replace").strip()
            if text and text not in {",", "(", ")", "*", "**"}:
                params.append(text.split(":")[0].split("=")[0].strip())
    # Find call sites inside the function body (simple traversal)
    calls: list[dict] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in {"call", "call_expression", "method_invocation"}:
            text = src[n.start_byte : n.end_byte].decode("utf-8", "replace")
            head = text.split("(", 1)[0].strip()
            calls.append({"name": head, "line": n.start_point[0] + 1})
        stack.extend(n.children)
    return FunctionSummary(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        params=params,
        calls=calls,
    )


# ── Regex fallback path ───────────────────────────────────────────────


_REGEX_FN_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"^[ \t]*(async\s+)?def\s+(?P<name>[a-zA-Z_][a-zA-Z_0-9]*)\s*\((?P<params>[^)]*)\)", re.MULTILINE),
    "javascript": re.compile(r"^[ \t]*(?:async\s+)?function\s+(?P<name>[a-zA-Z_$][\w$]*)\s*\((?P<params>[^)]*)\)", re.MULTILINE),
    "typescript": re.compile(r"^[ \t]*(?:async\s+)?function\s+(?P<name>[a-zA-Z_$][\w$]*)\s*\((?P<params>[^)]*)\)", re.MULTILINE),
}

_REGEX_CALL = re.compile(r"\b([a-zA-Z_][\w.]*)\s*\(")


def _regex_parse(path: Path, language: str) -> FileParse:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FileParse(file=str(path), language=language, parse_method="regex_fallback")
    pat = _REGEX_FN_PATTERNS.get(language)
    fns: list[FunctionSummary] = []
    if pat is None:
        return FileParse(file=str(path), language=language, parse_method="regex_fallback")
    lines = src.split("\n")
    for m in pat.finditer(src):
        start_line = src.count("\n", 0, m.start()) + 1
        name = m.group("name")
        params_str = m.group("params") or ""
        params = [p.split(":")[0].split("=")[0].strip() for p in params_str.split(",") if p.strip()]
        # End line: scan ahead until we exit indentation (Python) or
        # match braces (JS) — keep it simple, use indent-based heuristic
        # everywhere. Good enough for fallback.
        end_line = start_line
        for i in range(start_line, len(lines)):
            if lines[i].strip() and not lines[i].startswith((" ", "\t")) and i > start_line:
                end_line = i
                break
        else:
            end_line = len(lines)
        # Calls inside the function
        body = "\n".join(lines[start_line - 1 : end_line])
        calls: list[dict] = []
        for cm in _REGEX_CALL.finditer(body):
            call_name = cm.group(1)
            if call_name in {"if", "for", "while", "return", "print", "def", "function"}:
                continue
            line_offset = body.count("\n", 0, cm.start())
            calls.append({"name": call_name, "line": start_line + line_offset})
        fns.append(FunctionSummary(
            name=name,
            start_line=start_line,
            end_line=end_line,
            params=params,
            calls=calls,
        ))
    return FileParse(
        file=str(path),
        language=language,
        functions=fns,
        parse_method="regex_fallback",
    )


# ── Public entry ──────────────────────────────────────────────────────


def cpg_parse_tree(
    path: str | Path,
    *,
    language: str | None = None,
) -> dict:
    """Parse a single source file into a FileParse dict.

    Args:
        path: source file path
        language: override auto-detection. If None, infer from extension.

    Returns:
        Dict shape from FileParse.to_dict(). Empty ``functions`` list +
        ``parse_method`` indicates either no functions found or both
        tree-sitter + regex fallback didn't recognize the language.
    """
    p = Path(path)
    if language is None:
        from decepticon.tools.cpg.inventory import _EXT_TO_LANG  # type: ignore[reportPrivateUsage]
        ext = p.suffix.lower()
        language = _EXT_TO_LANG.get(ext) or ""
    if not language:
        return FileParse(file=str(p), language="unknown", parse_method="regex_fallback").to_dict()
    fp = _try_tree_sitter_parse(p, language)
    if fp is not None:
        return fp.to_dict()
    return _regex_parse(p, language).to_dict()


__all__ = ["FileParse", "FunctionSummary", "cpg_parse_tree"]
