"""Kerberos ticket and hash analysis.

Two primary inputs the agent encounters:

1. Hashcat-formatted Kerberos hashes (``$krb5tgs$...``, ``$krb5asrep$``)
2. Base64 .kirbi tickets dumped from Rubeus / Impacket

This module parses both, classifies the encryption type (RC4 = easy,
AES = hard), and emits a recommendation for hashcat mode + wordlist
strategy. It does NOT crack the hashes itself — that's hashcat's job.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class KerberosTicket:
    kind: str  # "tgs" | "asrep" | "kirbi" | "unknown"
    etype: str  # "rc4" | "aes128" | "aes256" | "unknown"
    principal: str | None
    realm: str | None
    hashcat_mode: int | None
    notes: list[str]
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "etype": self.etype,
            "principal": self.principal,
            "realm": self.realm,
            "hashcat_mode": self.hashcat_mode,
            "notes": list(self.notes),
        }


# ── Hashcat hash classifier ─────────────────────────────────────────────

_HASH_PATTERNS: tuple[tuple[re.Pattern[str], str, int], ...] = (
    # $krb5tgs$23$*USER$DOMAIN$SPN*$checksum$cipher
    (re.compile(r"^\$krb5tgs\$23\$"), "tgs-rc4", 13100),
    (re.compile(r"^\$krb5tgs\$17\$"), "tgs-aes128", 19600),
    (re.compile(r"^\$krb5tgs\$18\$"), "tgs-aes256", 19700),
    (re.compile(r"^\$krb5asrep\$23\$"), "asrep-rc4", 18200),
    (re.compile(r"^\$krb5asrep\$17\$"), "asrep-aes128", 29700),
    (re.compile(r"^\$krb5asrep\$18\$"), "asrep-aes256", 29800),
    (re.compile(r"^\$krb5pa\$23\$"), "preauth-rc4", 7500),
    (re.compile(r"^\$krb5pa\$18\$"), "preauth-aes256", 19800),
)


def classify_hashcat_hash(hash_line: str) -> KerberosTicket:
    """Classify a single hashcat-format Kerberos hash line."""
    hash_line = hash_line.strip()
    for pat, kind, mode in _HASH_PATTERNS:
        if pat.match(hash_line):
            etype = "rc4"
            if "aes128" in kind:
                etype = "aes128"
            elif "aes256" in kind:
                etype = "aes256"
            principal: str | None = None
            realm: str | None = None
            # Form: $krb5tgs$23$*user$realm$spn*$cksum$cipher
            m = re.match(
                r"^\$krb5(?:tgs|asrep|pa)\$\d+\$\*?([^$*]+)\$([^$*]+)\$",
                hash_line,
            )
            if m:
                principal = m.group(1)
                realm = m.group(2)
            notes: list[str] = []
            if etype == "rc4":
                notes.append(
                    "RC4 encryption — attempt hashcat with rockyou.txt + common AD rule sets. "
                    "Weak passwords crack in seconds."
                )
            elif etype.startswith("aes"):
                notes.append(
                    f"{etype.upper()} — crack only if a constrained wordlist + username heuristics "
                    "are available. Slow without GPU."
                )
            return KerberosTicket(
                kind=kind.split("-")[0],
                etype=etype,
                principal=principal,
                realm=realm,
                hashcat_mode=mode,
                notes=notes,
                raw=hash_line[:200],
            )
    return KerberosTicket(
        kind="unknown",
        etype="unknown",
        principal=None,
        realm=None,
        hashcat_mode=None,
        notes=["hash format not recognised"],
        raw=hash_line[:200],
    )


# ── .kirbi detection (base64) ──────────────────────────────────────────


def parse_ticket(raw: str) -> KerberosTicket:
    """Classify a raw ticket string (hashcat hash or base64 .kirbi).

    Base64 .kirbi tickets are ASN.1 KRB_CRED structures — we don't
    parse the full ASN.1 but flag the header and let the agent shell
    out to Rubeus / klist for full detail.
    """
    raw = raw.strip()
    if raw.startswith("$krb5"):
        return classify_hashcat_hash(raw)
    if re.match(r"^[A-Za-z0-9+/=]{100,}$", raw):
        return KerberosTicket(
            kind="kirbi",
            etype="unknown",
            principal=None,
            realm=None,
            hashcat_mode=None,
            notes=[
                "looks like a base64 .kirbi — use `rubeus describe /ticket:<b64>` or "
                "`impacket-ticketConverter` to inspect encryption type and principal.",
            ],
            raw=raw[:200],
        )
    return KerberosTicket(
        kind="unknown",
        etype="unknown",
        principal=None,
        realm=None,
        hashcat_mode=None,
        notes=["unrecognised ticket format"],
        raw=raw[:200],
    )
