"""Broad-spectrum scanner tools — Stage 1 of the vulnresearch pipeline.

Scale target: 10^5–10^6 files. The scanner must stay cheap — no LLM
reasoning per file — so all of the heavy lifting is done by deterministic
Python regex over a sharded ``os.walk`` of the target repo. The scanner
agent only *orchestrates* shards, merges results, and calls
:func:`kg_add_candidate` for the top-ranked hits.

Sharding
--------
``scan_shard(root, shard_idx, shard_total)`` walks ``root`` in
deterministic sorted order and keeps only files whose index modulo
``shard_total`` equals ``shard_idx``. This lets N parallel scanner
instances cover the whole tree with zero overlap and zero coordination.

Heuristic scoring
-----------------
Each file is matched against two small regex tables:

- **Sources** — untrusted data entry points (``request.args``, ``$_GET``,
  ``os.environ``, etc.)
- **Sinks**   — dangerous operations (``eval``, ``exec``, ``system``,
  ``innerHTML``, ``SELECT ...``, ``pickle.loads``, ``yaml.load``, SSRF
  fetchers, deserialization, etc.)

A candidate is emitted whenever a sink hit is found. The score is a
linear blend of:

    base_sink_weight
  + 0.3  if a source hit occurs in the same file
  + 0.15 per additional sink hit (capped at +0.4)
  + 0.1  if the file path is in a known hot directory (routes/, views/,
         handlers/, api/, controllers/)
  - 0.2  for obvious test/vendor noise

The scanner agent feeds the raw JSON output through
:func:`rank_candidates` (a pure-Python merge + top-k selector) before
promoting the top hits to ``CODE_LOCATION`` / ``CANDIDATE`` nodes via
:func:`kg_add_candidate`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from decepticon.core.logging import get_logger
from decepticon.tools.research._state import _json, _load, _save
from decepticon.tools.research.graph import Edge, EdgeKind, Node, NodeKind, Severity

log = get_logger("research.scanner_tools")


# ── Heuristic tables ────────────────────────────────────────────────────
#
# Kept intentionally small. These are *prefilters*, not a detector — the
# goal is to surface ~1% of functions in a 100k-file repo, not to enumerate
# every vuln class. The detector agent (Stage 2) applies real reasoning.

_SOURCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "http_param": re.compile(
        r"\b(request\.(args|form|values|json|data|GET|POST|body|params|query|cookies)"
        r"|req\.(body|params|query|cookies|headers)"
        r"|\$_(GET|POST|REQUEST|COOKIE|SERVER)"
        r"|params\[|query_params|HttpServletRequest)\b"
    ),
    "env": re.compile(r"\b(os\.environ|getenv|System\.getenv|process\.env)\b"),
    "cli": re.compile(r"\b(sys\.argv|os\.args|Process\.argv|argv\[)\b"),
    "stdin": re.compile(r"\b(sys\.stdin|input\(|readLine|fgets)\b"),
    "file_read": re.compile(r"\b(open\(|read_text|readFileSync|ioutil\.ReadFile|fs\.readFile)\b"),
    "network": re.compile(r"\b(recv|recvfrom|socket\.recv|ws\.onmessage)\b"),
}

_SINK_PATTERNS: dict[str, tuple[re.Pattern[str], float]] = {
    # key : (pattern, base_weight ∈ [0,1])
    "code_exec": (
        re.compile(r"\b(eval|exec|Function\(|setTimeout\(\s*['\"]|new\s+Function)\b"),
        0.70,
    ),
    "os_exec": (
        re.compile(
            r"\b(os\.system|os\.popen|subprocess\.(call|run|Popen|check_output)"
            r"|Runtime\.getRuntime\(\)\.exec|shell_exec|passthru|proc_open"
            r"|child_process\.exec|execSync|spawn\b)"
        ),
        0.85,
    ),
    "sql": (
        re.compile(
            r"""(?xi)
            (?:execute|executemany|query|raw)\s*\(\s*(?:f?['"][^'"\n]*\b
                (?:SELECT|INSERT|UPDATE|DELETE|UNION|DROP)\b)
            | cursor\.execute\s*\([^)]*%\s*
            | ["']SELECT\s+.+\s+FROM\s+.+["']\s*\+\s*
            """
        ),
        0.80,
    ),
    "ssrf": (
        re.compile(
            r"\b(requests\.(get|post|put|delete|head|request)|urllib\.request\.urlopen"
            r"|urlopen\(|http\.Get|axios\.(get|post)|fetch\(|HttpClient|curl_exec)\b"
        ),
        0.55,
    ),
    "deserialize": (
        re.compile(
            r"\b(pickle\.loads|marshal\.loads|yaml\.load\b(?!_safe)"
            r"|ObjectInputStream|unserialize|Marshal\.load|deserialize)\b"
        ),
        0.90,
    ),
    "xss": (
        re.compile(
            r"\b(innerHTML|outerHTML|document\.write|dangerouslySetInnerHTML"
            r"|v-html|\.html\(|Markup\(|mark_safe|render_template_string)\b"
        ),
        0.65,
    ),
    "path": (
        re.compile(
            r"\b(open\s*\([^,)]*\+|os\.path\.join\s*\([^,)]*request"
            r"|fs\.readFile\s*\([^,)]*req\.|send_file\s*\([^)]*request)\b"
        ),
        0.70,
    ),
    "ssti": (
        re.compile(r"\b(render_template_string|Template\(|Jinja2Templates|Handlebars\.compile)\b"),
        0.70,
    ),
    "crypto": (
        re.compile(r"\b(MD5|SHA1|DES|RC4|ECB|PKCS1|math\.random|Math\.random|rand\(\))\b"),
        0.35,
    ),
    "auth": (
        re.compile(
            r"\b(verify\s*=\s*False|rejectUnauthorized\s*:\s*false"
            r"|InsecureSkipVerify|check_hostname\s*=\s*False)\b"
        ),
        0.60,
    ),
    "secret_hardcode": (
        re.compile(
            r"""(?xi)
            \b(api[_-]?key|secret[_-]?key|password|token|private[_-]?key)\s*
            [=:]\s*['"][A-Za-z0-9+/_\-]{16,}['"]
            """
        ),
        0.75,
    ),
}

_HOT_DIR_HINTS = {
    "routes",
    "views",
    "handlers",
    "controllers",
    "api",
    "endpoints",
    "resolvers",
    "server",
    "backend",
    "auth",
    "login",
    "admin",
}

_NOISE_HINTS = {
    "test",
    "tests",
    "__tests__",
    "spec",
    "specs",
    "fixtures",
    "vendor",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "target",
    ".git",
    "site-packages",
    "third_party",
}

_DEFAULT_EXTS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".php",
    ".rb",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".sol",
    ".swift",
    ".m",
    ".mm",
    ".sh",
}


# ── Walk + slice ────────────────────────────────────────────────────────


def _iter_files(root: Path, extensions: set[str], max_files: int) -> list[Path]:
    """Deterministic sorted walk, extension filter, hard cap.

    Sorting by posix path guarantees shard_idx stability across hosts.
    """
    out: list[Path] = []
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune obvious noise dirs in-place so os.walk doesn't descend.
        dirnames[:] = sorted(d for d in dirnames if d not in _NOISE_HINTS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.suffix.lower() not in extensions:
                continue
            out.append(p)
            if len(out) >= max_files:
                return out
    out.sort(key=lambda p: str(p))
    return out


def _is_noisy(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & _NOISE_HINTS)


def _is_hot(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & _HOT_DIR_HINTS)


# ── Scoring ─────────────────────────────────────────────────────────────


def _score_hit(
    *,
    sink_weight: float,
    sink_count: int,
    has_source_in_file: bool,
    hot: bool,
    noisy: bool,
) -> float:
    score = sink_weight
    if has_source_in_file:
        score += 0.30
    if sink_count > 1:
        score += min(0.40, 0.15 * (sink_count - 1))
    if hot:
        score += 0.10
    if noisy:
        score -= 0.20
    return round(max(0.0, min(1.0, score)), 3)


def _scan_one(path: Path, max_bytes: int = 512 * 1024) -> list[dict[str, Any]]:
    """Return a list of hit dicts for a single file. Best-effort — skips
    binaries, unreadable files, and anything over ``max_bytes``."""
    try:
        size = path.stat().st_size
        if size == 0 or size > max_bytes:
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return []
    if "\x00" in text[:2048]:
        return []  # likely binary

    source_hits: list[str] = [name for name, pat in _SOURCE_PATTERNS.items() if pat.search(text)]
    sink_hits: list[tuple[str, float, int]] = []  # (key, weight, line)
    for key, (pat, weight) in _SINK_PATTERNS.items():
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            sink_hits.append((key, weight, line_no))

    if not sink_hits:
        return []

    # One candidate per unique (sink_kind, line) — avoid spamming the graph.
    seen: set[tuple[str, int]] = set()
    hot = _is_hot(path)
    noisy = _is_noisy(path)
    total_sinks = len(sink_hits)
    out: list[dict[str, Any]] = []
    for key, weight, line_no in sink_hits:
        sig = (key, line_no)
        if sig in seen:
            continue
        seen.add(sig)
        # Extract the matched line + 2 lines of context (small).
        lines = text.splitlines()
        lo = max(0, line_no - 2)
        hi = min(len(lines), line_no + 1)
        snippet = "\n".join(lines[lo:hi])[:400]
        out.append(
            {
                "path": str(path),
                "line": line_no,
                "sink_kind": key,
                "source_hits": source_hits,
                "score": _score_hit(
                    sink_weight=weight,
                    sink_count=total_sinks,
                    has_source_in_file=bool(source_hits),
                    hot=hot,
                    noisy=noisy,
                ),
                "snippet": snippet,
            }
        )
    return out


# ── Tools ───────────────────────────────────────────────────────────────


@tool
def scan_shard(
    root: str,
    shard_idx: int = 0,
    shard_total: int = 1,
    extensions: str = "",
    max_files: int = 5000,
    max_hits: int = 400,
) -> str:
    """Walk a slice of ``root`` and return heuristic vulnerability candidates.

    WHEN TO USE: Stage 1 broad-spectrum sweep. Call this once per shard
    (N parallel scanner instances, each with a unique ``shard_idx`` in
    ``[0, shard_total)``) so a 10^5-file repo is covered without overlap.
    The output is raw hits — pipe through :func:`rank_candidates` before
    promoting anything to the graph.

    This tool does NOT call the LLM, does NOT execute shell commands, and
    does NOT write to the knowledge graph. It is a pure-Python prefilter
    tuned to surface <1% of the codebase for downstream LLM analysis.

    Args:
        root: Absolute directory to scan (usually ``/workspace/target``).
        shard_idx: Zero-based shard number, in ``[0, shard_total)``.
        shard_total: Total shard count. ``shard_total=1`` → scan everything.
        extensions: Comma-separated file extensions to include (e.g.
            ``"py,js,ts"``). Empty string uses the built-in polyglot set.
        max_files: Hard cap on files inspected per shard (default 5000).
        max_hits: Hard cap on hits returned per shard (default 400).

    Returns:
        JSON object with ``shard_idx``, ``files_scanned``, ``hits_returned``,
        and a ``hits`` array of ``{path, line, sink_kind, source_hits,
        score, snippet}`` dicts.
    """
    if shard_total < 1 or shard_idx < 0 or shard_idx >= shard_total:
        return _json({"error": f"bad shard: {shard_idx}/{shard_total}"})

    root_p = Path(root)
    if not root_p.exists():
        return _json({"error": f"root not found: {root}"})

    exts = (
        {f".{e.strip().lower().lstrip('.')}" for e in extensions.split(",") if e.strip()}
        if extensions
        else _DEFAULT_EXTS
    )

    all_files = _iter_files(root_p, exts, max_files=max_files * shard_total)
    shard_files = [p for i, p in enumerate(all_files) if i % shard_total == shard_idx]

    hits: list[dict[str, Any]] = []
    for p in shard_files:
        hits.extend(_scan_one(p))
        if len(hits) >= max_hits:
            break

    # Sort shard-local by score desc so top-k callers can truncate cheaply.
    hits.sort(key=lambda h: h["score"], reverse=True)
    if len(hits) > max_hits:
        hits = hits[:max_hits]

    return _json(
        {
            "shard_idx": shard_idx,
            "shard_total": shard_total,
            "files_scanned": len(shard_files),
            "hits_returned": len(hits),
            "hits": hits,
        }
    )


@tool
def rank_candidates(shard_results: str, top_k: int = 50) -> str:
    """Merge shard outputs, dedupe by ``(path,line,sink_kind)``, return top-k.

    WHEN TO USE: After fanning out N :func:`scan_shard` calls, pass the
    concatenated JSON (newline- or comma-separated list of shard JSON
    blobs, or a single JSON array) here to get a clean, ranked candidate
    list for the detector stage.

    The ranker does **not** write to the knowledge graph. Call
    :func:`kg_add_candidate` per returned hit once the detector has
    decided which ones to investigate.

    Args:
        shard_results: JSON array of shard outputs, OR a newline-separated
            list of shard JSON blobs (the format ``scan_shard`` returns).
        top_k: Max candidates to return (default 50).

    Returns:
        JSON with ``total_hits``, ``unique_hits``, and a ``candidates``
        array sorted by descending score.
    """
    raw = shard_results.strip()
    blobs: list[dict[str, Any]] = []
    # Three accepted shapes:
    #   1. A single JSON object (one shard)
    #   2. A JSON array of shard objects
    #   3. Several JSON objects concatenated back-to-back
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        blobs = [parsed]
    elif isinstance(parsed, list):
        blobs = [b for b in parsed if isinstance(b, dict)]
    else:
        # Fallback: walk a depth counter to find balanced top-level
        # objects. Handles newline-separated and concatenated JSON
        # without mis-splitting on indented nested objects.
        depth = 0
        start = -1
        for i, ch in enumerate(raw):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    chunk = raw[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                        if isinstance(obj, dict):
                            blobs.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start = -1

    seen: dict[tuple[str, int, str], dict[str, Any]] = {}
    total = 0
    for blob in blobs:
        if not isinstance(blob, dict):
            continue
        for hit in blob.get("hits", []):
            total += 1
            key = (hit.get("path", ""), int(hit.get("line", 0)), hit.get("sink_kind", ""))
            prior = seen.get(key)
            if prior is None or hit.get("score", 0) > prior.get("score", 0):
                seen[key] = hit

    uniq = sorted(seen.values(), key=lambda h: h.get("score", 0), reverse=True)
    return _json(
        {
            "total_hits": total,
            "unique_hits": len(uniq),
            "candidates": uniq[: max(0, top_k)],
        }
    )


@tool
def kg_add_candidate(
    path: str,
    line: int,
    score: float,
    sink_kind: str,
    reason: str = "",
    repo: str = "",
) -> str:
    """Promote a scanner hit to a ``CANDIDATE`` node in the knowledge graph.

    WHEN TO USE: Only for the top-ranked hits from :func:`rank_candidates`
    that the scanner agent judges worth the detector's token budget. Every
    candidate gets a deterministic dedup key of ``"{path}:{line}:{sink_kind}"``
    so repeated shard runs never double-insert.

    Downstream: the detector stage calls ``kg_query(kind="candidate")`` to
    fetch these, reads the surrounding source, and either promotes the
    candidate to a ``VULNERABILITY`` node (with a ``DERIVED_FROM`` edge
    back to the candidate) or marks it as a false positive by updating
    its ``props.status``.

    Args:
        path: File path inside the sandbox (e.g. ``/workspace/target/app.py``).
        line: 1-indexed line number of the suspected sink.
        score: Suspicion score in ``[0,1]`` from the scanner heuristic.
        sink_kind: One of the sink keys (``code_exec``, ``os_exec``, ``sql``,
            ``ssrf``, ``deserialize``, ``xss``, ``path``, ``ssti``, ``crypto``,
            ``auth``, ``secret_hardcode``).
        reason: Optional free-text justification (keep it short).
        repo: Optional repo id (graph node id) to link with a ``LOCATED_AT``
            edge. Leave empty if not yet modelled.

    Returns:
        JSON with the created/updated candidate node id and graph stats.
    """
    label = f"{sink_kind}@{Path(path).name}:{line}"
    props: dict[str, Any] = {
        "key": f"{path}:{line}:{sink_kind}",
        "path": path,
        "line": int(line),
        "sink_kind": sink_kind,
        "score": float(score),
        "status": "pending",  # detector flips to promoted/rejected
    }
    if reason:
        props["reason"] = reason

    graph, db_path = _load()
    node = graph.upsert_node(Node.make(NodeKind.CANDIDATE, label, **props))

    # Tag severity bucket for kg_query(min_severity=...) convenience.
    if score >= 0.85:
        node.props["severity"] = Severity.HIGH.value
    elif score >= 0.60:
        node.props["severity"] = Severity.MEDIUM.value
    else:
        node.props["severity"] = Severity.LOW.value

    if repo and repo in graph.nodes:
        graph.upsert_edge(Edge.make(node.id, repo, EdgeKind.DEFINED_IN))

    _save(graph, db_path)
    return _json(
        {
            "id": node.id,
            "kind": node.kind.value,
            "label": node.label,
            "severity": node.props.get("severity"),
            "stats": graph.stats(),
        }
    )


SCANNER_TOOLS = [scan_shard, rank_candidates, kg_add_candidate]
