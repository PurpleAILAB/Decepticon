"""LangChain @tool wrappers for the web exploitation suite."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.web.graphql import GraphQLSchema
from decepticon.tools.web.jwt import (
    DEFAULT_WEAK_SECRETS,
    crack_hs_secret,
    forge_token,
    parse_token,
)
from decepticon.tools.web.oauth import analyze_oauth_callback
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


WEB_TOOLS = [jwt_parse, jwt_forge, jwt_crack, graphql_plan, oauth_audit, cookie_audit]
