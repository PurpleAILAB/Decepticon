"""DNS subdomain-takeover verifier.

Probes a domain's DNS records (CNAME, NS, MX, TXT) over DNS-over-HTTPS
and classifies whether a dangling record points at an orphaned /
claimable cloud service (S3, GitHub Pages, Heroku, ...) or an expired
nameserver delegation.

Why DoH instead of the stdlib resolver
--------------------------------------
``socket.getaddrinfo`` only returns A/AAAA addresses — it cannot read
the CNAME / NS / MX / TXT record types this verifier depends on, and
``dnspython`` is intentionally not a project dependency. DNS-over-HTTPS
(Google's ``dns.google/resolve`` JSON API) gives every record type over
plain HTTP, so it rides the ``httpx.AsyncClient`` already used by the
CVE intelligence module — no new dependency, same async fan-out pattern.

False-positive mitigation
--------------------------
False positives are the dominant failure mode of takeover scanners: a
CNAME to ``foo.s3.amazonaws.com`` is only exploitable if the bucket is
actually unclaimed. We mitigate by

1. fetching the live HTTP body of the target and matching the *service's*
   documented takeover signature (e.g. ``NoSuchBucket``), and
2. actively checking whether the backing resource is still registered /
   resolvable (an NXDOMAIN target is claimable; a resolving target is
   still owned and therefore *secure*).

Every network hop is funneled through small async helpers so tests can
mock them deterministically and no live traffic is required.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import tool

from decepticon_core.utils.logging import get_logger

log = get_logger("research.dns_takeover")

# ── Endpoints / constants ────────────────────────────────────────────────

DOH_URL = "https://dns.google/resolve"
DEFAULT_TIMEOUT = 8.0

# DNS record type codes as returned by the DoH JSON ``type`` field.
DNS_TYPE: dict[str, int] = {
    "A": 1,
    "NS": 2,
    "CNAME": 5,
    "MX": 15,
    "TXT": 16,
}

# DoH ``Status`` == 3 is NXDOMAIN (RFC 8484 maps the DNS RCODE through).
NXDOMAIN_STATUS = 3

# Severity ordering used to fold per-record findings into one verdict.
_VERDICT_ORDER: dict[str, int] = {
    "secure": 0,
    "manual-review": 1,
    "likely-takeover": 2,
    "confirmed-takeover": 3,
}


# ── Service fingerprints ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Fingerprint:
    """A claimable-service signature.

    ``cname_patterns`` are substrings matched (case-insensitively) against
    a CNAME target. ``signatures`` are HTTP-body markers a *vulnerable*
    (unclaimed) instance of the service serves. ``nxdomain_is_takeover``
    flags services where a dangling CNAME alone (target no longer resolves)
    is sufficient evidence of an exploitable delegation.
    """

    service: str
    cname_patterns: tuple[str, ...]
    signatures: tuple[str, ...]
    nxdomain_is_takeover: bool = True


# Curated from the canonical can-i-take-over-xyz fingerprint set. Kept as a
# module-level tuple so it is shared across calls and trivially testable.
FINGERPRINTS: tuple[Fingerprint, ...] = (
    Fingerprint(
        service="aws-s3",
        cname_patterns=("s3.amazonaws.com", "s3-website", ".s3.", "s3.dualstack"),
        signatures=(
            "NoSuchBucket",
            "The specified bucket does not exist",
        ),
    ),
    Fingerprint(
        service="github-pages",
        cname_patterns=("github.io", "github.map.fastly.net"),
        signatures=(
            "There isn't a GitHub Pages site here",
            "For root URLs (like http://example.com/) you must provide an index.html file",
        ),
    ),
    Fingerprint(
        service="heroku",
        cname_patterns=("herokuapp.com", "herokudns.com", "herokussl.com"),
        signatures=(
            "No such app",
            "There's nothing here, yet.",
            "herokucdn.com/error-pages/no-such-app.html",
        ),
    ),
    Fingerprint(
        service="azure",
        cname_patterns=(
            "azurewebsites.net",
            "cloudapp.net",
            "cloudapp.azure.com",
            "trafficmanager.net",
            "blob.core.windows.net",
            "azureedge.net",
            "azurefd.net",
        ),
        signatures=(
            "404 Web Site not found",
            "The specified blob does not exist",
        ),
    ),
    Fingerprint(
        service="fastly",
        cname_patterns=("fastly.net",),
        signatures=("Fastly error: unknown domain",),
        nxdomain_is_takeover=False,
    ),
    Fingerprint(
        service="shopify",
        cname_patterns=("myshopify.com",),
        signatures=(
            "Sorry, this shop is currently unavailable",
            "Only one step left!",
        ),
        nxdomain_is_takeover=False,
    ),
    Fingerprint(
        service="surge",
        cname_patterns=("surge.sh",),
        signatures=("project not found",),
    ),
    Fingerprint(
        service="bitbucket",
        cname_patterns=("bitbucket.io",),
        signatures=("Repository not found",),
    ),
    Fingerprint(
        service="tumblr",
        cname_patterns=("domains.tumblr.com",),
        signatures=(
            "Whatever you were looking for doesn't currently exist at this address",
            "There's nothing here.",
        ),
        nxdomain_is_takeover=False,
    ),
    Fingerprint(
        service="pantheon",
        cname_patterns=("pantheonsite.io",),
        signatures=("The gods are wise, but do not know of the site which you seek.",),
    ),
)


# ── Resolution helpers (mockable in tests) ───────────────────────────────


async def _doh_query(client: httpx.AsyncClient, name: str, rtype: str) -> dict[str, Any]:
    """Resolve ``name``/``rtype`` via DNS-over-HTTPS. Returns ``{}`` on error."""
    try:
        resp = await client.get(
            DOH_URL,
            params={"name": name, "type": rtype},
            headers={"accept": "application/dns-json"},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.debug("doh %s/%s failed: %s", name, rtype, e)
        return {}


async def _fetch_http_body(client: httpx.AsyncClient, host: str) -> str:
    """Fetch ``host`` over HTTPS then HTTP, returning the body or ``""``.

    The live body is what lets us distinguish a *confirmed* takeover
    (service serves its "unclaimed" page) from a benign dangling pointer.
    """
    for scheme in ("https", "http"):
        try:
            resp = await client.get(
                f"{scheme}://{host}",
                timeout=DEFAULT_TIMEOUT,
                follow_redirects=True,
            )
            return resp.text or ""
        except httpx.HTTPError as e:
            log.debug("http probe %s://%s failed: %s", scheme, host, e)
            continue
    return ""


async def _resource_claimable(client: httpx.AsyncClient, target: str) -> bool | None:
    """Is the CNAME/NS ``target`` an orphaned (claimable) resource?

    - ``True``  — target itself is NXDOMAIN; the backing resource is gone.
    - ``False`` — target still resolves to an address; resource is owned.
    - ``None``  — indeterminate (resolver error / empty answer).

    This is the active registration-availability probe that demotes a
    suspicious-looking CNAME back to ``secure`` when the resource is in
    fact still claimed by its owner.
    """
    doh = await _doh_query(client, target, "A")
    if not doh:
        return None
    if _is_nxdomain(doh):
        return True
    if _extract_records(doh, "A"):
        return False
    return None


# ── Pure parsing / matching ──────────────────────────────────────────────


def _is_nxdomain(doh: dict[str, Any]) -> bool:
    """True when the DoH envelope reports NXDOMAIN."""
    return doh.get("Status") == NXDOMAIN_STATUS


def _extract_records(doh: dict[str, Any], rtype: str) -> list[str]:
    """Pull the ``rtype`` answers out of a DoH envelope, trailing-dot trimmed."""
    code = DNS_TYPE[rtype]
    out: list[str] = []
    for ans in doh.get("Answer") or []:
        if ans.get("type") != code:
            continue
        data = ans.get("data")
        if isinstance(data, str) and data:
            out.append(data.rstrip(".").strip('"'))
    return out


def _match_fingerprint(cname: str) -> Fingerprint | None:
    """Return the claimable-service fingerprint matching ``cname``, if any."""
    low = cname.lower()
    for fp in FINGERPRINTS:
        if any(pattern in low for pattern in fp.cname_patterns):
            return fp
    return None


def _classify_cname(fp: Fingerprint, body: str, claimable: bool | None) -> str:
    """Map (fingerprint, live body, claimable) onto a structured verdict."""
    if body and any(sig.lower() in body.lower() for sig in fp.signatures):
        return "confirmed-takeover"
    if claimable is True:
        # Dangling pointer + orphaned resource. For services where an
        # NXDOMAIN target alone is exploitable this is a strong lead.
        return "likely-takeover" if fp.nxdomain_is_takeover else "manual-review"
    if claimable is False:
        # Resource still resolves / is owned — the classic false positive.
        return "secure"
    return "manual-review"


# ── Core analysis ────────────────────────────────────────────────────────


async def _analyze_domain(client: httpx.AsyncClient, domain: str) -> dict[str, Any]:
    """Probe ``domain`` and assemble the takeover report."""
    cname_doh, ns_doh, mx_doh, txt_doh = await asyncio.gather(
        _doh_query(client, domain, "CNAME"),
        _doh_query(client, domain, "NS"),
        _doh_query(client, domain, "MX"),
        _doh_query(client, domain, "TXT"),
    )

    cnames = _extract_records(cname_doh, "CNAME")
    nameservers = _extract_records(ns_doh, "NS")
    mx_records = _extract_records(mx_doh, "MX")
    txt_records = _extract_records(txt_doh, "TXT")

    findings: list[dict[str, Any]] = []
    # The live body is served at ``domain`` (not at the CNAME target), so it
    # is identical across every matching CNAME — fetch it at most once, and
    # only when a fingerprint actually matches.
    body: str | None = None

    for cname in cnames:
        fp = _match_fingerprint(cname)
        if fp is None:
            continue
        if body is None:
            body = await _fetch_http_body(client, domain)
        claimable = await _resource_claimable(client, cname)
        verdict = _classify_cname(fp, body, claimable)
        signature_matched = bool(body and any(sig.lower() in body.lower() for sig in fp.signatures))
        findings.append(
            {
                "type": "CNAME",
                "record": cname,
                "service": fp.service,
                "verdict": verdict,
                "claimable": claimable,
                "signature_matched": signature_matched,
                "reason": _reason(fp, verdict, claimable, signature_matched),
            }
        )

    # Expired-nameserver delegation: a delegated NS host that no longer
    # resolves is a claimable nameserver takeover.
    for ns in nameservers:
        claimable = await _resource_claimable(client, ns)
        if claimable is True:
            findings.append(
                {
                    "type": "NS",
                    "record": ns,
                    "service": "nameserver",
                    "verdict": "likely-takeover",
                    "claimable": True,
                    "signature_matched": False,
                    "reason": "delegated nameserver no longer resolves (expired/claimable)",
                }
            )

    verdict = "secure"
    for finding in findings:
        if _VERDICT_ORDER[finding["verdict"]] > _VERDICT_ORDER[verdict]:
            verdict = finding["verdict"]

    return {
        "domain": domain,
        "records": {
            "cname": cnames,
            "ns": nameservers,
            "mx": mx_records,
            "txt": txt_records,
        },
        "cname_pointers": cnames,
        "findings": findings,
        "verdict": verdict,
    }


def _reason(fp: Fingerprint, verdict: str, claimable: bool | None, signature_matched: bool) -> str:
    if verdict == "confirmed-takeover":
        return f"{fp.service} unclaimed-resource signature served by live host"
    if verdict == "likely-takeover":
        return f"CNAME targets {fp.service} and backing resource is orphaned (NXDOMAIN)"
    if verdict == "secure":
        return f"CNAME targets {fp.service} but backing resource still resolves (owned)"
    return f"CNAME targets {fp.service}; registration status indeterminate — verify manually"


# ── LangChain tool surface ───────────────────────────────────────────────


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


@tool
async def dns_takeover_verifier(domain: str) -> str:
    """Detect subdomain-takeover exposure for a domain.

    WHEN TO USE: After enumerating subdomains (subfinder/dnsx), run this on
    any host with a CNAME to a third-party cloud service to confirm whether
    the delegation is dangling and the backing resource is claimable.

    Probes CNAME/NS/MX/TXT records over DNS-over-HTTPS, fingerprints the
    CNAME target against known claimable services (S3, GitHub Pages,
    Heroku, Azure, Fastly, ...), and actively checks whether the resource
    is still owned to suppress false positives.

    Returns a JSON string with ``records`` (all probed record types),
    ``cname_pointers``, per-record ``findings``, and an overall ``verdict``
    of ``confirmed-takeover`` | ``likely-takeover`` | ``secure`` |
    ``manual-review``.
    """
    domain = (domain or "").strip().rstrip(".").lower()
    if not domain:
        return _json({"error": "empty domain"})

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=5.0),
        follow_redirects=True,
    ) as client:
        report = await _analyze_domain(client, domain)
    return _json(report)


DNS_TOOLS = [dns_takeover_verifier]
