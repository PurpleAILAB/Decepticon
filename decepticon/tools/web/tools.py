"""LangChain @tool wrappers for the web exploitation suite."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.web.browser import BrowserSession, BrowserUnavailable
from decepticon.tools.web.graphql import GraphQLSchema
from decepticon.tools.web.jwt import (
    DEFAULT_WEAK_SECRETS,
    crack_hs_secret,
    forge_token,
    parse_token,
)
from decepticon.tools.web.oauth import analyze_oauth_callback
from decepticon.tools.web.proxy import ProxySession
from decepticon.tools.web.session import analyze_cookie


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@tool
def jwt_parse(token: str) -> str:
    """Parse a JWT and surface known header / claim findings.

    Returns a JSON object with the decoded header, claims, and any
    security findings (alg=none, no-exp, jku/kid injection, etc.).
    """
    t = parse_token(token)
    return _json(
        {
            "header": t.header.to_dict(),
            "claims": t.claims.to_dict(),
            "findings": list(t.findings),
            "expired": t.claims.expired,
        }
    )


@tool
def jwt_forge(
    claims_json: str,
    alg: str = "none",
    secret: str = "",
    header_json: str = "",
) -> str:
    """Forge a JWT with arbitrary claims/algorithm.

    Args:
        claims_json: JSON object for the body. Example:
            ``'{"sub":"admin","exp":9999999999}'``
        alg: none | HS256 | HS384 | HS512
        secret: Required for HS* algs
        header_json: Optional JSON for extra header fields (kid, jku, x5u)

    Returns:
        JSON with the forged token string.
    """
    try:
        claims = json.loads(claims_json) if claims_json else {}
        header = json.loads(header_json) if header_json else None
        token = forge_token(claims, alg=alg, secret=secret or None, header=header)
    except (json.JSONDecodeError, ValueError) as e:
        return _json({"error": str(e)})
    return _json({"token": token})


@tool
def jwt_crack(token: str, wordlist: str = "") -> str:
    """Dictionary-attack an HS* JWT with a candidate wordlist.

    ``wordlist`` is a newline-separated list. If empty, the default
    weak-secret list is used (seeds from ``DEFAULT_WEAK_SECRETS``).
    """
    t = parse_token(token)
    candidates = wordlist.splitlines() if wordlist else list(DEFAULT_WEAK_SECRETS)
    secret = crack_hs_secret(t, candidates)
    return _json({"cracked": secret is not None, "secret": secret, "tried": len(candidates)})


@tool
def graphql_plan(introspection_json: str) -> str:
    """Parse a GraphQL introspection blob, list IDOR candidates, and
    auto-generate a baseline query for each.

    ``introspection_json`` should be the full JSON body returned by the
    server for the introspection query.
    """
    try:
        data = json.loads(introspection_json)
    except json.JSONDecodeError as e:
        return _json({"error": f"introspection must be JSON: {e}"})
    schema = GraphQLSchema.from_introspection(data)
    candidates = [
        {
            "kind": kind,
            "field": fld.name,
            "args": list(fld.args),
            "sample_query": schema.generate_query(fld.name, kind=kind.lower()),
        }
        for kind, fld in schema.idor_candidates()
    ]
    return _json(
        {
            "query_type": schema.query_type,
            "mutation_type": schema.mutation_type,
            "idor_candidates": candidates,
            "query_count": len(schema.query_fields()),
            "mutation_count": len(schema.mutation_fields()),
        }
    )


@tool
def oauth_audit(
    callback_url: str,
    initial_request_url: str = "",
    public_client: bool = False,
) -> str:
    """Audit an OAuth / OIDC callback URL for canonical RFC issues.

    Flags missing/predictable state, missing nonce, implicit flow,
    PKCE absence, open redirect_uri, scope over-request, etc.
    """
    findings = analyze_oauth_callback(
        callback_url,
        initial_request_url=initial_request_url or None,
        public_client=public_client,
    )
    return _json([f.to_dict() for f in findings])


@tool
def cookie_audit(
    name: str,
    value: str,
    secure: bool = False,
    http_only: bool = False,
    same_site: str = "",
) -> str:
    """Classify a cookie and flag framework + entropy + transport issues."""
    analysis = analyze_cookie(
        name,
        value,
        secure=secure,
        http_only=http_only,
        same_site=same_site or None,
    )
    return _json(analysis.to_dict())


# ── Proxy + browser session singletons ─────────────────────────────────────
# One ProxySession / BrowserSession per process — the agent runs a single
# attack chain at a time inside the sandbox. Lazy-initialised so importing
# the toolkit never starts a browser or an httpx client.

_PROXY: ProxySession | None = None
_BROWSER: BrowserSession | None = None


def _proxy() -> ProxySession:
    global _PROXY
    if _PROXY is None:
        _PROXY = ProxySession()
    return _PROXY


def _browser() -> BrowserSession:
    global _BROWSER
    if _BROWSER is None:
        _BROWSER = BrowserSession.from_playwright(headless=True)
    return _BROWSER


@tool
def proxy_request(
    name: str,
    method: str,
    url: str,
    headers: str = "{}",
    body: str = "",
    send: bool = True,
) -> str:
    """Record (and by default send) an HTTP request into the proxy session.

    ``headers`` is a JSON object string. Set ``send=false`` to stage the
    request as a template for later ``proxy_tamper`` / ``proxy_replay``.
    Returns the captured entry as JSON (status, response headers, body).
    """
    try:
        hdrs = json.loads(headers) if headers else {}
    except json.JSONDecodeError as exc:
        return _json({"error": f"headers must be JSON object: {exc}"})
    try:
        entry = _proxy().record(name, method=method, url=url, headers=hdrs, body=body, send=send)
    except (ValueError, RuntimeError) as exc:
        return _json({"error": str(exc)})
    return _json(entry.to_dict())


@tool
def proxy_replay(
    name: str,
    headers: str = "{}",
    body: str = "",
    url: str = "",
) -> str:
    """Re-issue a recorded request with optional header/body/url overrides.

    The replay is recorded under ``<name>-replay-N`` so the original entry
    stays pristine for further mutation. Returns the replayed entry JSON.
    """
    try:
        hdrs = json.loads(headers) if headers else {}
    except json.JSONDecodeError as exc:
        return _json({"error": f"headers must be JSON object: {exc}"})
    try:
        entry = _proxy().replay(
            name,
            headers=hdrs or None,
            body=body or None,
            url=url or None,
        )
    except (KeyError, ValueError) as exc:
        return _json({"error": str(exc)})
    return _json(entry.to_dict())


@tool
def proxy_tamper(
    name: str,
    header_overrides: str = "{}",
    param_overrides: str = "{}",
    body_overrides: str = "",
    send: bool = False,
) -> str:
    """Produce a mutated copy of a recorded request (IDOR/header-injection PoC).

    Defaults to ``send=false`` so you can stage the mutation and inspect it
    before firing. Set ``send=true`` to also dispatch it immediately.
    """
    try:
        h = json.loads(header_overrides) if header_overrides else {}
        p = json.loads(param_overrides) if param_overrides else {}
    except json.JSONDecodeError as exc:
        return _json({"error": f"overrides must be JSON objects: {exc}"})
    try:
        entry = _proxy().tamper(
            name,
            header_overrides=h or None,
            param_overrides=p or None,
            body_overrides=body_overrides or None,
            send=send,
        )
    except (KeyError, ValueError) as exc:
        return _json({"error": str(exc)})
    return _json(entry.to_dict())


@tool
def proxy_diff(name_a: str, name_b: str) -> str:
    """Unified diff of two recorded responses (body only)."""
    try:
        return _proxy().diff(name_a, name_b)
    except KeyError as exc:
        return _json({"error": str(exc)})


@tool
def proxy_history() -> str:
    """List every recorded proxy entry name in insertion order."""
    return _json({"entries": _proxy().list()})


@tool
def browser_navigate(url: str, page: str = "main") -> str:
    """Open (or reuse) a browser tab and navigate it to ``url``.

    Requires Playwright in the sandbox. Returns the resolved URL after
    any redirects the browser followed.
    """
    try:
        sess = _browser()
    except BrowserUnavailable as exc:
        return _json({"error": str(exc), "fallback": "use proxy_request instead"})
    if page not in sess.list_pages():
        sess.open_page(page)
    final = sess.navigate(page, url)
    return _json({"page": page, "url": final})


@tool
def browser_interact(
    action: str,
    selector: str = "",
    value: str = "",
    page: str = "main",
) -> str:
    """Drive the page: ``action`` ∈ click | fill | press | content | url.

    ``fill`` needs ``selector`` + ``value``; ``press`` needs ``selector`` +
    ``value`` (the key); ``click`` needs ``selector``; ``content``/``url``
    take no extra args.
    """
    try:
        sess = _browser()
    except BrowserUnavailable as exc:
        return _json({"error": str(exc)})
    try:
        if action == "click":
            sess.click(page, selector)
            return _json({"ok": True, "action": "click", "selector": selector})
        if action == "fill":
            sess.fill(page, selector, value)
            return _json({"ok": True, "action": "fill", "selector": selector})
        if action == "press":
            sess.press(page, selector, value)
            return _json({"ok": True, "action": "press", "key": value})
        if action == "content":
            return _json({"content": sess.content(page)[:20000]})
        if action == "url":
            return _json({"url": sess.current_url(page)})
        return _json({"error": f"unknown action {action!r}"})
    except KeyError as exc:
        return _json({"error": str(exc)})


@tool
def browser_evaluate(expression: str, page: str = "main") -> str:
    """Execute JS in the page context (DOM XSS / PoC validation).

    Returns the JSON-serialised evaluation result. Use this to confirm a
    reflected/DOM XSS actually executes in the page origin instead of
    inferring from the response body.
    """
    try:
        sess = _browser()
    except BrowserUnavailable as exc:
        return _json({"error": str(exc)})
    try:
        result = sess.evaluate(page, expression)
    except KeyError as exc:
        return _json({"error": str(exc)})
    return _json({"result": result})


WEB_TOOLS = [
    jwt_parse,
    jwt_forge,
    jwt_crack,
    graphql_plan,
    oauth_audit,
    cookie_audit,
    proxy_request,
    proxy_replay,
    proxy_tamper,
    proxy_diff,
    proxy_history,
    browser_navigate,
    browser_interact,
    browser_evaluate,
]
