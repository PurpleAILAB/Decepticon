"""Live secret scanner for client-side JavaScript.

Front-end bundles routinely leak long-lived credentials — API keys,
tokens, private keys baked straight into the shipped ``.js``. This module
provides a single agent-facing tool, :func:`scan_secrets`, that:

1. Matches the supplied JS source against a table of high-signal secret
   regexes (AWS, GitHub, Slack, OpenAI, Stripe, Google, GitLab, Twilio,
   SendGrid, generic PEM private keys, JWTs, …).
2. For the credential types we know how to probe, performs a *real* HTTP
   call against the issuing API (e.g. ``GET https://api.github.com/user``
   with the token as a bearer credential) to decide whether the secret is
   still **live** or already **dead** (revoked / rotated).
3. Returns a JSON string mapping each finding to its source line number,
   the pattern that fired, and the validation status (``live`` / ``dead``
   / ``unvalidated``).

The probe layer is deliberately built on a throwaway :class:`httpx.AsyncClient`
so the network surface is trivially mockable in tests — patch
``httpx.AsyncClient`` with a :class:`httpx.MockTransport` and no real egress
ever happens.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import httpx
from langchain_core.tools import tool

from decepticon.tools.research._state import _json

DEFAULT_TIMEOUT = 8.0

# Upper bound on live-credential probes per scan. ``js_content`` is often
# attacker-controlled (it is the page we are reconnoitring); without a cap a
# bundle stuffed with thousands of distinct pattern-matching strings would make
# the scanner fire one outbound request per string — slow, and a fast way to get
# our egress IP rate-limited or blocked by the probed APIs. Secrets past the
# budget are still reported, just left ``unvalidated``.
MAX_VALIDATION_PROBES = 50

# ── Detection patterns ──────────────────────────────────────────────────
#
# High-signal, low-false-positive regexes. Each entry maps a stable
# ``pattern_name`` (used both in the output and to look up a validator) to
# a compiled pattern. Patterns with a single capture group expose the bare
# secret in group 1; the rest expose it as the whole match.

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(
        r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"
    ),
    "aws_secret_access_key": re.compile(r"(?i)aws[^\n]{0,30}?['\"]([A-Za-z0-9/+=]{40})['\"]"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
    "github_fine_grained_token": re.compile(r"github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9]{59}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,48}"),
    "slack_webhook": re.compile(
        r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9_]+"
    ),
    "openai_api_key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "stripe_api_key": re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{24,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "gitlab_pat": re.compile(r"glpat-[A-Za-z0-9_-]{20}"),
    "twilio_api_key": re.compile(r"SK[0-9a-fA-F]{32}"),
    "sendgrid_api_key": re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}


# ── Validation probes ───────────────────────────────────────────────────
#
# Each probe takes a live client + the bare secret and returns True when
# the issuing API accepts the credential (HTTP 200 / ``ok: true``), False
# when it is rejected. Probes never swallow transport errors — the caller
# decides how an unreachable API maps to a status.

_Probe = Callable[[httpx.AsyncClient, str], Awaitable[bool]]


async def _probe_github(client: httpx.AsyncClient, secret: str) -> bool:
    resp = await client.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/vnd.github+json",
        },
    )
    return resp.status_code == 200


async def _probe_openai(client: httpx.AsyncClient, secret: str) -> bool:
    resp = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return resp.status_code == 200


async def _probe_stripe(client: httpx.AsyncClient, secret: str) -> bool:
    # Stripe authenticates with the secret key as HTTP-basic username.
    resp = await client.get("https://api.stripe.com/v1/account", auth=(secret, ""))
    return resp.status_code == 200


async def _probe_slack(client: httpx.AsyncClient, secret: str) -> bool:
    resp = await client.post(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {secret}"},
    )
    if resp.status_code != 200:
        return False
    data = resp.json()
    # auth.test returns a JSON object; guard against unexpected shapes so a
    # non-dict body raises ValueError (caught by _classify) instead of a stray
    # AttributeError that would abort the whole scan.
    if not isinstance(data, dict):
        raise ValueError("slack auth.test returned a non-object body")
    return bool(data.get("ok"))


async def _probe_gitlab(client: httpx.AsyncClient, secret: str) -> bool:
    resp = await client.get(
        "https://gitlab.com/api/v4/user",
        headers={"PRIVATE-TOKEN": secret},
    )
    return resp.status_code == 200


async def _probe_sendgrid(client: httpx.AsyncClient, secret: str) -> bool:
    resp = await client.get(
        "https://api.sendgrid.com/v3/scopes",
        headers={"Authorization": f"Bearer {secret}"},
    )
    return resp.status_code == 200


# Pattern names that have a live-credential probe. Anything not listed here
# is reported as ``unvalidated``.
_VALIDATORS: dict[str, _Probe] = {
    "github_token": _probe_github,
    "github_fine_grained_token": _probe_github,
    "openai_api_key": _probe_openai,
    "stripe_api_key": _probe_stripe,
    "slack_token": _probe_slack,
    "gitlab_pat": _probe_gitlab,
    "sendgrid_api_key": _probe_sendgrid,
}


async def validate_credential(pattern_name: str, secret: str) -> bool:
    """Probe ``secret`` against its issuing API and report liveness.

    Performs a single authenticated HTTP request (over a throwaway
    :class:`httpx.AsyncClient`) against the API that issued the credential
    type identified by ``pattern_name``.

    Args:
        pattern_name: A key from :data:`SECRET_PATTERNS` (and
            :data:`_VALIDATORS`).
        secret: The bare credential to test.

    Returns:
        ``True`` if the API accepts the credential (it is live), ``False``
        if it is rejected (dead/revoked).

    Raises:
        KeyError: If no probe is registered for ``pattern_name``.
        httpx.HTTPError: If the probe request fails at the transport layer.
    """
    probe = _VALIDATORS.get(pattern_name)
    if probe is None:
        raise KeyError(f"no validator registered for pattern: {pattern_name}")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        return await probe(client, secret)


async def _classify(pattern_name: str, secret: str) -> str:
    """Resolve the validation status for a single matched secret."""
    if pattern_name not in _VALIDATORS:
        return "unvalidated"
    try:
        return "live" if await validate_credential(pattern_name, secret) else "dead"
    except (httpx.HTTPError, ValueError, KeyError):
        # Swallow probe failures and report the credential as unvalidated. We do
        # NOT log here: the exception can embed the request (and its secret), and
        # CodeQL conservatively treats any logging sink in this secret-handling
        # frame as clear-text exposure. Liveness is best-effort by contract.
        return "unvalidated"


def _extract(pattern: re.Pattern[str], match: re.Match[str]) -> str:
    """Return the bare secret — capture group 1 when present, else the match."""
    if pattern.groups >= 1:
        return match.group(1)
    return match.group(0)


@tool
async def scan_secrets(js_content: str) -> str:
    """Scan JavaScript for leaked credentials and probe each for liveness.

    WHEN TO USE: After fetching client-side JS (inline ``<script>`` blocks,
    bundled ``app.js``, source-map originals). Surfaces hard-coded API
    keys, tokens, and private keys, and — for credential types we can probe
    — tells you which ones are *still live* so you can prioritise.

    Detected types include AWS access keys, GitHub tokens, Slack tokens and
    webhooks, OpenAI/Stripe/Google/GitLab/Twilio/SendGrid keys, generic PEM
    private keys, and JWTs.

    Args:
        js_content: Raw JavaScript source to scan.

    Returns:
        JSON string of the form::

            {
              "count": <int>,
              "secrets": [
                {"secret": "<value>", "line": <int>,
                 "pattern": "<type>", "status": "live|dead|unvalidated"},
                ...
              ]
            }

        ``status`` is ``live`` / ``dead`` when a probe ran and resolved,
        and ``unvalidated`` when no probe exists for that type or the probe
        could not reach the API.
    """
    if not js_content:
        return _json({"count": 0, "secrets": []})

    findings: list[dict[str, object]] = []
    seen: set[tuple[str, str, int]] = set()
    # Cache probe results so a secret repeated across many lines is only
    # validated once.
    status_cache: dict[tuple[str, str], str] = {}
    probes_done = 0

    for line_no, line in enumerate(js_content.splitlines(), start=1):
        for pattern_name, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(line):
                secret = _extract(pattern, match)
                key = (pattern_name, secret, line_no)
                if key in seen:
                    continue
                seen.add(key)

                cache_key = (pattern_name, secret)
                status = status_cache.get(cache_key)
                if status is None:
                    if pattern_name in _VALIDATORS and probes_done >= MAX_VALIDATION_PROBES:
                        # Probe budget exhausted — report without a live check.
                        status = "unvalidated"
                    else:
                        if pattern_name in _VALIDATORS:
                            probes_done += 1
                        status = await _classify(pattern_name, secret)
                    status_cache[cache_key] = status

                findings.append(
                    {
                        "secret": secret,
                        "line": line_no,
                        "pattern": pattern_name,
                        "status": status,
                    }
                )

    return _json({"count": len(findings), "secrets": findings})
