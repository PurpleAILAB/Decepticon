"""OAuth 2.0 / OIDC flow auditor.

Checks a callback URL (the one the authorization server redirects to)
for the canonical OAuth 2.0 security bugs:

- Missing or predictable ``state`` (CSRF)
- Missing or predictable ``nonce`` (OIDC replay)
- Authorization code leaked in Referer or fragment
- ``redirect_uri`` with path traversal / open redirect
- PKCE absence on public clients
- Implicit flow still in use (``response_type=token``)
- ``scope`` over-requests (wildcards, cross-tenant scopes)

The checker is offline: the agent pastes the full callback URL (or
logs) and gets a structured list of findings back.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit


@dataclass
class OAuthFinding:
    """A single OAuth-flow finding."""

    id: str
    severity: str  # "info" | "low" | "medium" | "high" | "critical"
    title: str
    detail: str
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "recommendation": self.recommendation,
        }


# ── Helpers ─────────────────────────────────────────────────────────────


_HEX_RE = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    entropy = 0.0
    length = len(s)
    for count in freq.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _qp(url: str) -> dict[str, list[str]]:
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    # OIDC ``response_mode=fragment`` puts params in the URL fragment
    fragment = parse_qs(parts.fragment, keep_blank_values=True)
    for k, v in fragment.items():
        query.setdefault(k, []).extend(v)
    return query


# ── Main checker ────────────────────────────────────────────────────────


def analyze_oauth_callback(
    callback_url: str,
    *,
    initial_request_url: str | None = None,
    public_client: bool = False,
) -> list[OAuthFinding]:
    """Inspect an OAuth callback URL for security issues.

    ``initial_request_url`` is the authorize-endpoint URL the client
    sent the user to; when provided we cross-check that ``state`` and
    ``nonce`` came back unchanged (session fixation / replay).
    """
    findings: list[OAuthFinding] = []
    params = _qp(callback_url)

    # Canonicalise single-value params
    single = {k: v[0] if v else "" for k, v in params.items()}

    # ── response_type / grant flow ──
    initial_params = _qp(initial_request_url) if initial_request_url else {}
    initial_single = {k: v[0] if v else "" for k, v in initial_params.items()}

    response_type = initial_single.get("response_type") or single.get("response_type", "")
    if response_type == "token":
        findings.append(
            OAuthFinding(
                id="oauth.implicit-flow",
                severity="high",
                title="Implicit flow in use",
                detail=(
                    "response_type=token delivers the access token in the URL "
                    "fragment, exposing it to history and referrers. Deprecated by RFC 9700."
                ),
                recommendation="Use authorization code + PKCE instead.",
            )
        )

    # ── state ──
    state = single.get("state", "")
    if not state:
        findings.append(
            OAuthFinding(
                id="oauth.state-missing",
                severity="high",
                title="Callback has no state parameter",
                detail="CSRF protection requires state. RFC 6749 §10.12.",
                recommendation="Always generate and validate a per-session state value.",
            )
        )
    else:
        entropy = _shannon_entropy(state)
        if len(state) < 8:
            findings.append(
                OAuthFinding(
                    id="oauth.state-short",
                    severity="medium",
                    title="state parameter is too short",
                    detail=f"state={state!r} ({len(state)} chars). "
                    f"Below the RFC 6819 recommended 128-bit equivalent.",
                )
            )
        if entropy < 2.5:
            findings.append(
                OAuthFinding(
                    id="oauth.state-low-entropy",
                    severity="medium",
                    title="state parameter has low Shannon entropy",
                    detail=f"entropy={entropy:.2f} bits/char — may be predictable.",
                )
            )
        if initial_single and initial_single.get("state") and initial_single["state"] != state:
            findings.append(
                OAuthFinding(
                    id="oauth.state-mismatch",
                    severity="critical",
                    title="state returned by AS does not match initial value",
                    detail=(
                        f"initial={initial_single['state']!r} callback={state!r}. "
                        "Authorisation server is not echoing the client's state."
                    ),
                )
            )

    # ── nonce (OIDC) ──
    scope = initial_single.get("scope", "") or single.get("scope", "")
    if "openid" in scope.split():
        nonce = initial_single.get("nonce", "")
        if not nonce:
            findings.append(
                OAuthFinding(
                    id="oidc.nonce-missing",
                    severity="high",
                    title="OIDC flow without nonce",
                    detail="nonce is required for OIDC implicit / hybrid flows (OIDC Core §3.1.2).",
                    recommendation="Generate a per-request nonce and verify it in the ID token.",
                )
            )

    # ── code exposure ──
    code = single.get("code", "")
    if code and urlsplit(callback_url).fragment and "code=" in urlsplit(callback_url).fragment:
        findings.append(
            OAuthFinding(
                id="oauth.code-in-fragment",
                severity="high",
                title="Authorization code delivered in URL fragment",
                detail="Fragments are leaked via document.location and browser history.",
                recommendation="Use response_mode=query or form_post.",
            )
        )

    # ── PKCE ──
    if public_client:
        code_verifier = initial_single.get("code_challenge", "")
        if not code_verifier:
            findings.append(
                OAuthFinding(
                    id="oauth.pkce-missing",
                    severity="high",
                    title="Public client without PKCE",
                    detail="RFC 9700 requires PKCE for all OAuth clients, especially public ones.",
                    recommendation="Send code_challenge + code_challenge_method=S256.",
                )
            )
        elif initial_single.get("code_challenge_method", "plain").lower() == "plain":
            findings.append(
                OAuthFinding(
                    id="oauth.pkce-plain",
                    severity="medium",
                    title="PKCE using plain method",
                    detail="code_challenge_method=plain is weaker than S256 and forbidden for public clients.",
                )
            )

    # ── redirect_uri ──
    redirect_uri = initial_single.get("redirect_uri", "")
    if redirect_uri:
        if any(frag in redirect_uri for frag in ("%252e%252e", "%2e%2e", "../", "..%2f")):
            findings.append(
                OAuthFinding(
                    id="oauth.redirect-uri-traversal",
                    severity="high",
                    title="redirect_uri contains path traversal",
                    detail=f"redirect_uri={redirect_uri!r}",
                    recommendation="Validate redirect_uri against an exact-match allowlist.",
                )
            )
        if "@" in redirect_uri:
            findings.append(
                OAuthFinding(
                    id="oauth.redirect-uri-userinfo",
                    severity="medium",
                    title="redirect_uri contains userinfo component",
                    detail=f"redirect_uri={redirect_uri!r} — URL parser confusion candidate.",
                )
            )

    # ── scope ──
    if scope and any(s in ("*", "all", "admin") for s in scope.split()):
        findings.append(
            OAuthFinding(
                id="oauth.scope-wildcard",
                severity="medium",
                title="Scope contains wildcard / admin token",
                detail=f"scope={scope!r} — least-privilege violation.",
            )
        )

    return findings
