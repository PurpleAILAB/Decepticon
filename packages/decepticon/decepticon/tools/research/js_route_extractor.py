"""Front-end JavaScript route & endpoint extraction.

Static recon helper that mines client-side JavaScript bundles for the
server-side attack surface they reveal: REST endpoints, API paths,
SPA route tables and the query parameters wired into them.

The extractor is intentionally regex-driven (no JS parser) so it copes
with minified, transpiled and partially-obfuscated bundles where an AST
parse would simply throw. Eight+ complementary patterns cover the common
ways front-end code names a server route:

- ``fetch("...")`` / ``fetch(`...`)``
- ``axios.get("...")`` and the other verb helpers, plus ``axios({url})``
- ``XMLHttpRequest.open("GET", "...")``
- ``$.ajax({url: "..."})`` / jQuery ``$.get`` / ``$.post``
- client routers — ``router.get("/path")`` / ``app.post("/path")``
- SPA route tables — ``path: "/dashboard"`` (Angular/Vue/React-Router)
- absolute ``http(s)://host/path`` URLs
- bare path string literals — ``"/api/v1/users"``
- template-literal endpoints — `` `/users/${id}` ``

Each extracted route is classified into a coarse taxonomy (``auth``,
``admin``, ``api``, ``upload``, ``search``, ``file_access``) and every
query parameter is mapped to a sensitivity class that hints at the
likely vulnerability primitive:

- ``id_params``      → possible IDOR / BOLA
- ``file_params``    → possible LFI / path traversal
- ``redirect_params``→ possible SSRF / open redirect
- ``command_params`` → possible RCE / command injection

The :func:`js_route_extractor` ``@tool`` returns a compact JSON string so
it satisfies the LangChain tool contract and keeps LLM token usage low.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from langchain_core.tools import tool

from decepticon_core.utils.logging import get_logger

log = get_logger("research.js_route_extractor")


# ── Extraction patterns ──────────────────────────────────────────────────
#
# Every pattern captures the route string in group 1 (or the named group
# ``route``) and, where the syntax carries it, the HTTP verb in ``method``.
# ``QUOTE`` matches single, double or back-tick string delimiters.

_QUOTE = r"['\"`]"
_STR = rf"{_QUOTE}([^'\"`]+){_QUOTE}"

_PATTERNS: list[tuple[str, re.Pattern[str], int, int | None]] = [
    # (source label, compiled pattern, route group, method group or None)
    (
        "fetch",
        re.compile(rf"\bfetch\s*\(\s*{_STR}"),
        1,
        None,
    ),
    (
        "axios",
        re.compile(rf"\baxios\.(get|post|put|delete|patch|head|options)\s*\(\s*{_STR}", re.I),
        2,
        1,
    ),
    (
        "axios",
        re.compile(rf"\baxios\s*\(\s*\{{[^}}]*?\burl\s*:\s*{_STR}", re.I | re.S),
        1,
        None,
    ),
    (
        "xhr",
        re.compile(
            rf"\.open\s*\(\s*{_QUOTE}(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS){_QUOTE}\s*,\s*{_STR}",
            re.I,
        ),
        2,
        1,
    ),
    (
        "jquery_ajax",
        re.compile(rf"\$\.ajax\s*\(\s*\{{[^}}]*?\burl\s*:\s*{_STR}", re.I | re.S),
        1,
        None,
    ),
    (
        "jquery",
        re.compile(rf"\$\.(get|post|getJSON)\s*\(\s*{_STR}", re.I),
        2,
        1,
    ),
    (
        "router",
        re.compile(
            rf"\b(?:app|router|route|server|api)\.(get|post|put|delete|patch|all|use)\s*\(\s*{_STR}",
            re.I,
        ),
        2,
        1,
    ),
    (
        "spa_route",
        re.compile(rf"\bpath\s*:\s*{_STR}", re.I),
        1,
        None,
    ),
    (
        "absolute_url",
        re.compile(rf"{_QUOTE}(https?://[^'\"`\s]+){_QUOTE}", re.I),
        1,
        None,
    ),
    (
        "string_literal",
        re.compile(rf"{_QUOTE}(/[A-Za-z0-9_./:{{}}$%\-?=&]*){_QUOTE}"),
        1,
        None,
    ),
    (
        "template_literal",
        re.compile(r"`(/[^`]*\$\{[^`]*)`"),
        1,
        None,
    ),
]


# ── Route classification taxonomy ────────────────────────────────────────
#
# Keyword → category. A route may belong to several categories at once
# (``/api/admin/users`` is both ``api`` and ``admin``). Matching is done on
# the lower-cased route value.

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "auth": (
        "login",
        "logout",
        "signin",
        "sign-in",
        "signup",
        "sign-up",
        "register",
        "auth",
        "oauth",
        "token",
        "password",
        "passwd",
        "session",
        "sso",
        "saml",
        "mfa",
        "otp",
        "2fa",
        "verify",
        "credential",
        "forgot",
        "reset",
    ),
    "admin": (
        "admin",
        "manage",
        "management",
        "dashboard",
        "console",
        "superuser",
        "root",
        "internal",
        "settings",
        "config",
        "moderat",
        "backend",
    ),
    "api": (
        "/api",
        "/v1",
        "/v2",
        "/v3",
        "/graphql",
        "/rest",
        "/rpc",
        "/gql",
        ".json",
    ),
    "upload": (
        "upload",
        "import",
        "attachment",
        "media",
        "blob",
        "avatar",
        "/file/upload",
    ),
    "search": (
        "search",
        "query",
        "find",
        "lookup",
        "filter",
        "autocomplete",
        "suggest",
        "typeahead",
    ),
    "file_access": (
        "download",
        "export",
        "/file",
        "/files",
        "document",
        "/doc",
        "/docs",
        "/static",
        "/assets",
        "/media",
        "fetchfile",
        "getfile",
        "read",
        "view",
    ),
}


# ── Parameter sensitivity classification ─────────────────────────────────
#
# Keyword → (class, vulnerability hint). Highest-severity classes are
# checked first so a parameter is labelled with its most dangerous plausible
# primitive. ``_PARAM_KEYWORDS`` keywords ≥ 4 chars also match as substrings
# (so ``returnurl`` matches ``return``); shorter keywords match only as
# whole tokens to avoid false positives (``idea`` must not match ``id``).

_PARAM_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "command_params",
        "possible RCE / command injection",
        (
            "cmd",
            "command",
            "exec",
            "execute",
            "run",
            "ping",
            "shell",
            "code",
            "eval",
            "system",
            "process",
            "spawn",
            "func",
            "do",
        ),
    ),
    (
        "redirect_params",
        "possible SSRF / open redirect",
        (
            "redirect",
            "redirect_uri",
            "redirecturl",
            "url",
            "uri",
            "next",
            "return",
            "returnurl",
            "return_url",
            "callback",
            "dest",
            "destination",
            "target",
            "continue",
            "goto",
            "link",
            "out",
            "forward",
            "to",
            "rurl",
            "checkout_url",
        ),
    ),
    (
        "file_params",
        "possible LFI / path traversal",
        (
            "file",
            "filename",
            "filepath",
            "path",
            "dir",
            "folder",
            "doc",
            "document",
            "page",
            "template",
            "include",
            "load",
            "read",
            "src",
            "source",
            "attachment",
            "download",
            "name",
        ),
    ),
    (
        "id_params",
        "possible IDOR / BOLA",
        (
            "id",
            "uid",
            "userid",
            "user_id",
            "account",
            "acct",
            "customer",
            "order",
            "object",
            "pid",
            "gid",
            "num",
            "no",
            "key",
            "ref",
            "record",
            "item",
        ),
    ),
]

_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(name: str) -> list[str]:
    """Split a parameter name into lower-case tokens, expanding camelCase."""
    snake = _CAMEL_RE.sub(r"\1_\2", name)
    return [t for t in _TOKEN_SPLIT_RE.split(snake.lower()) if t]


def classify_param(name: str) -> tuple[str | None, str | None]:
    """Map a query-parameter name to its sensitivity class + vuln hint.

    Returns ``(None, None)`` when the name matches no rule.
    """
    if not name:
        return None, None
    normalized = name.lower()
    tokens = set(_tokenize(name))
    for cls, hint, keywords in _PARAM_RULES:
        for kw in keywords:
            if kw in tokens:
                return cls, hint
            if len(kw) >= 4 and kw in normalized:
                return cls, hint
    return None, None


def classify_route(route: str) -> list[str]:
    """Return the (possibly empty) list of taxonomy categories for a route."""
    lowered = route.lower()
    return [
        cat for cat, keywords in _CATEGORY_KEYWORDS.items() if any(k in lowered for k in keywords)
    ]


# ``http://`` URLs, rooted paths and template literals are interesting; bare
# words, mime types and pure host:port tokens are not.
_ROUTE_LIKE_RE = re.compile(r"^(?:https?://|/|\.{1,2}/)|\$\{")


def _looks_like_route(value: str) -> bool:
    value = value.strip()
    if not value or len(value) > 2048:
        return False
    if not _ROUTE_LIKE_RE.search(value):
        return False
    # Reject obvious non-routes that slip past the path regexes.
    if value in {"/", "//"}:
        return False
    if re.fullmatch(r"https?://", value, re.I):
        return False
    return True


def _split_query(value: str) -> tuple[str, str]:
    """Return ``(path_without_query, query_string)`` for a route value.

    Falls back to a manual ``?`` split for template-literal routes that
    :func:`urllib.parse.urlsplit` cannot reason about cleanly.
    """
    if value.startswith(("http://", "https://")):
        parts = urlsplit(value)
        return parts._replace(query="", fragment="").geturl(), parts.query
    base, sep, query = value.partition("?")
    return base, query if sep else ""


def _extract_params(query: str) -> list[str]:
    """Extract parameter names from a query string.

    Handles ordinary ``a=1&b=2`` query strings *and* template-literal forms
    such as ``id=${userId}&file=${path}`` where the value is an interpolation.
    """
    names: list[str] = []
    if not query:
        return names
    for raw in re.split(r"[&;]", query):
        raw = raw.strip()
        if not raw:
            continue
        name = raw.split("=", 1)[0].strip()
        # Strip any leftover interpolation/brace noise from the name itself.
        name = name.strip("${} ")
        if name:
            names.append(name)
    # Defensive fall-back: standards-compliant parse may recover names the
    # naive split missed (encoded separators, etc.).
    try:
        for name, _ in parse_qsl(query, keep_blank_values=True):
            if name and name not in names:
                names.append(name)
    except ValueError:
        pass
    return names


def extract_routes(js_content: str) -> dict[str, Any]:
    """Mine *js_content* for routes, categories and parameter sensitivity.

    Pure function (no I/O); the :func:`js_route_extractor` tool wraps it.

    Returns a dict with ``routes``, ``categories``, ``parameters`` and a
    roll-up ``summary``.
    """
    if not isinstance(js_content, str):
        raise TypeError("js_content must be a string")

    # value → {"methods": set, "sources": set}
    found: dict[str, dict[str, set[str]]] = {}

    for source, pattern, route_grp, method_grp in _PATTERNS:
        for match in pattern.finditer(js_content):
            value = match.group(route_grp)
            if not value or not _looks_like_route(value):
                continue
            value = value.strip()
            entry = found.setdefault(value, {"methods": set(), "sources": set()})
            entry["sources"].add(source)
            if method_grp is not None:
                verb = match.group(method_grp)
                if verb:
                    entry["methods"].add(verb.upper())

    routes: list[dict[str, Any]] = []
    categories: dict[str, list[str]] = {cat: [] for cat in _CATEGORY_KEYWORDS}
    parameters: list[dict[str, Any]] = []
    seen_params: set[tuple[str, str]] = set()
    sensitive_count = 0

    for value in sorted(found):
        meta = found[value]
        cats = classify_route(value)
        path, query = _split_query(value)
        param_names = _extract_params(query)

        route_params: list[dict[str, Any]] = []
        for name in param_names:
            cls, hint = classify_param(name)
            record = {
                "name": name,
                "classification": cls,
                "vulnerability_hint": hint,
            }
            route_params.append(record)
            key = (value, name)
            if key not in seen_params:
                seen_params.add(key)
                parameters.append(
                    {
                        "name": name,
                        "route": value,
                        "classification": cls,
                        "vulnerability_hint": hint,
                    }
                )
                if cls is not None:
                    sensitive_count += 1

        routes.append(
            {
                "value": value,
                "path": path,
                "methods": sorted(meta["methods"]),
                "sources": sorted(meta["sources"]),
                "categories": cats,
                "params": route_params,
            }
        )
        for cat in cats:
            categories[cat].append(value)

    categories = {cat: vals for cat, vals in categories.items() if vals}

    return {
        "routes": routes,
        "categories": categories,
        "parameters": parameters,
        "summary": {
            "total_routes": len(routes),
            "categories": {cat: len(vals) for cat, vals in categories.items()},
            "total_parameters": len(parameters),
            "sensitive_parameters": sensitive_count,
        },
    }


@tool
async def js_route_extractor(js_content: str) -> str:
    """Mine front-end JavaScript for the server attack surface it leaks.

    WHEN TO USE: After pulling a site's JS bundles (main.js, app.js,
    vendor chunks, inline ``<script>`` blocks). Front-end code hard-codes
    the REST endpoints, API paths and SPA routes the backend exposes —
    this tool lifts them out and flags the dangerous ones before you ever
    send a request.

    It applies 8+ complementary regexes (``fetch``, ``axios``,
    ``XMLHttpRequest.open``, jQuery ``$.ajax``/``$.get``, client routers,
    SPA ``path:`` route tables, absolute URLs, rooted path literals and
    template-literal endpoints), then:

    - classifies each route into ``auth`` / ``admin`` / ``api`` /
      ``upload`` / ``search`` / ``file_access``; and
    - maps every query parameter to a sensitivity class hinting at the
      likely primitive: ``id_params`` (IDOR/BOLA), ``file_params``
      (LFI/path traversal), ``redirect_params`` (SSRF/open redirect) or
      ``command_params`` (RCE/command injection).

    Args:
        js_content: Raw JavaScript source (minified or pretty-printed).

    Returns:
        JSON string with ``routes``, ``categories``, ``parameters`` and a
        ``summary`` roll-up.
    """
    result = extract_routes(js_content or "")
    log.debug(
        "js_route_extractor: %d routes, %d params (%d sensitive)",
        result["summary"]["total_routes"],
        result["summary"]["total_parameters"],
        result["summary"]["sensitive_parameters"],
    )
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)
