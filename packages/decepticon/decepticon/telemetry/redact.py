"""Identifier masking for the research reasoning corpus.

Captures attacker reasoning **as-is** (no summarization, no reshaping — that
would degrade its training value) while replacing only the **target
identifiers** with stable, typed, human-readable placeholders:

    "scan 10.0.0.5, then exploit 10.0.0.5 via the login at app.corp.internal"
    →
    "scan <IP_1>, then exploit <IP_1> via the login at <DOMAIN_1>"

Detection layers, highest-confidence first:

1. **Known engagement targets** (RoE / OPPLAN scope passed as ``known``) — the
   actual targets, masked with certainty. This is ground truth, not a guess, and
   is the most reliable layer; no PII library ships it.
2. **LangChain's built-in PII detectors** (``ip`` / ``mac_address`` / ``url`` /
   ``email``) — already in the stack (``langchain.agents.middleware``), so the
   well-structured classes use a maintained detector instead of hand-rolled
   regex. Falls back to local regex if that module moves.
3. **Custom detectors** for classes no library ships: private keys, JWTs, AWS
   keys, credentials, and bare hostnames/domains.

Stable placeholders: the same value maps to the same token for the life of a
:class:`Redactor` (one per session), so a multi-step trajectory stays coherent.
The gateway re-scans masked text as a second, server-side line of defense.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# A detector locates sensitive spans: text -> list of (start, end, value).
_Detector = Callable[[str], list[tuple[int, int, str]]]

# ── custom detectors (classes no PII library ships) ──────────────────────────
_KEY = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
    re.DOTALL,
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
_AWSKEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
# user:pass@host, and user:pass whose password carries a special char (so
# host:port and plain key:value pairs are left intact).
_CRED_AT = re.compile(r"\b[\w.-]+:[^\s:@/]{3,}@[\w.-]+")
# Long opaque base64/hex run — hashes, dumps, key material. The Tier-C scanner
# REJECTS these, so the masker must have a matching detector: without one, any
# reasoning step quoting a hash was silently dropped whole instead of masked.
_BLOB = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")
_CRED_SPECIAL = re.compile(r"\b[\w.-]+:[^\s:@/]*[!@#$%^&*+=][^\s:@/]*")
# Credential written as key=value / key: value. `_CRED_SPECIAL` only fires when
# the password carries a special character and `_CRED_AT` only on `user:pass@host`,
# so the most common real form — `login:bob senha:123456` — shipped in the clear.
# Only the VALUE (group 1) is masked, so the reasoning stays readable:
# "senha:123456" -> "senha:<CRED_1>", not "<CRED_1>".
_CRED_SECRET_KV = re.compile(
    r"(?:password|passwd|pwd|pass|senha|contrase\w+|пароль"
    r"|secret|token|api[_-]?key)"
    r"\s*(?:[:=]|\s+(?:is|es|la|là)\s+)\s*([^\s,;\"']{3,64})",
    re.IGNORECASE,
)
# Username pairs, TIGHT form only (`user:bob`). A spaced `user: the attacker` is
# prose, not a credential, and masking it would corrupt the reasoning.
_CRED_USER_KV = re.compile(r"(?:login|username|user)[:=]([^\s,;\"']{3,64})", re.IGNORECASE)
# Credential passed as a COMMAND-LINE FLAG. Observed leaking verbatim in a real
# engagement: `nxc smb <ip> -u Administrator -p 'Ujmqaz5055'`. Operators paste
# whole command lines, and no key:value detector sees a flag.
#
# `-p` is overloaded — it is nmap's port flag — so a purely numeric/comma/dash
# value is left alone (`nmap -p 80,443`, `-p 1-65535`, `-p-`). A password is
# never shaped like a port list.
_CRED_PW_FLAG = re.compile(
    r"(?:^|\s)--?(?:p|pw|pass|passwd|password)[=\s]+"
    r"['\"]?(?![\d,\-]+(?:\s|$|['\"]))([^\s'\"]{3,64})",
    re.IGNORECASE,
)
# `-u` only in its credential form (`curl -u admin:secret`). A bare `-u` is far
# too overloaded to touch — `sort -u`, `docker -u`, `nxc -u <name>`.
_CRED_USERPASS_FLAG = re.compile(
    r"(?:^|\s)--?(?:u|user|username)[=\s]+['\"]?([^\s'\":]{1,64}:[^\s'\"]{1,64})",
    re.IGNORECASE,
)
# IPv4 glued to a label — `ESXI10.10.0.95`. The maintained detector anchors on
# `\b`, and a letter directly before a digit is not a word boundary, so this
# leaked a real address verbatim. A leading digit or dot is still excluded so a
# longer dotted number is never sliced in half.
_IP_GLUED = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?![\d.])"
)
# Bare host/domain — requires a non-numeric TLD so "1.2.3"/"x86_64" never match.
# The trailing `(?!\()` keeps dotted CODE out: `json.load(...)`, `os.uname()` and
# friends are not hosts, and masking them destroyed the prompt. Measured: 1,697
# of 7,990 masked turns carried a `<DOMAIN_n>(` — a mangled function call.
_DOMAIN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b(?!\()", re.IGNORECASE
)

# Local-regex fallbacks for the LangChain built-ins (used only if the import fails).
_IP = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
# Four groups minimum. Three colon-separated groups is a wall-clock time —
# `21:35:00` was being masked as an address, and tool output is full of
# timestamps. Compressed `::` forms never matched this pattern anyway, so
# nothing real is lost.
_IP6 = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){3,7}[A-Fa-f0-9]{1,4}\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
_URL = re.compile(r"\bhttps?://[^\s)\]\"'<>]+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _group_detector(pattern: re.Pattern[str], group: int = 1) -> _Detector:
    """Detector that reports only a capture group — the surrounding text stays.

    Used for credential pairs, where masking the whole `senha:123456` would drop
    the fact that a password was involved; masking only the value keeps that.
    """

    def detect(text: str) -> list[tuple[int, int, str]]:
        return [
            (m.start(group), m.end(group), m.group(group))
            for m in pattern.finditer(text)
            if m.group(group)
        ]

    return detect


def _regex_detector(pattern: re.Pattern[str]) -> _Detector:
    def detect(text: str) -> list[tuple[int, int, str]]:
        return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]

    return detect


# Lower rank = higher priority when two matches overlap.
_PRIORITY = {"ORG": 0, "HOST": 0, "KEY": 1, "JWT": 1, "AWSKEY": 1, "CRED": 2, "BLOB": 3}


_BUILTINS: list[tuple[str, _Detector]] | None = None


def _builtin_detectors() -> list[tuple[str, _Detector]]:
    """Reuse LangChain's maintained PII detectors; fall back to local regex.

    Resolved once and cached. Lazy so importing this module never forces the
    heavy LangChain import on callers that only need the regex fallback.
    """
    global _BUILTINS
    if _BUILTINS is not None:
        return _BUILTINS
    try:
        from langchain.agents.middleware._redaction import (
            detect_email,
            detect_ip,
            detect_mac_address,
            detect_url,
        )

        def _wrap(fn: Callable[[str], list[dict[str, Any]]]) -> _Detector:
            def detect(text: str) -> list[tuple[int, int, str]]:
                return [(m["start"], m["end"], m["value"]) for m in fn(text)]

            return detect

        _BUILTINS = [
            ("IP", _wrap(detect_ip)),
            ("MAC", _wrap(detect_mac_address)),
            ("URL", _wrap(detect_url)),
            ("EMAIL", _wrap(detect_email)),
        ]
    except Exception:  # noqa: BLE001 — degrade to local regex, never fail to mask
        _BUILTINS = [
            ("IP", _regex_detector(_IP)),
            ("IP6", _regex_detector(_IP6)),
            ("MAC", _regex_detector(_MAC)),
            ("URL", _regex_detector(_URL)),
            ("EMAIL", _regex_detector(_EMAIL)),
        ]
    return _BUILTINS


class Redactor:
    """Stateful, stable identifier masker. One instance per session."""

    def __init__(self, known: list[str] | None = None) -> None:
        self._map: dict[str, str] = {}  # real value -> placeholder, stable
        self._counters: dict[str, int] = {}
        # (term, placeholder type). Ground truth beats every detector: no PII
        # model reliably finds a client's project slug or a bare NetBIOS name,
        # but the engagement already knows them.
        self._known: list[tuple[str, str]] = sorted(
            {(k, "HOST") for k in (known or []) if k}, key=lambda kv: len(kv[0]), reverse=True
        )
        # Custom classes (no library ships these) + always-on IPv6 fallback, then
        # the LangChain built-ins, then bare-domain last (least specific).
        self._detectors: list[tuple[str, _Detector]] = [
            ("KEY", _regex_detector(_KEY)),
            ("JWT", _regex_detector(_JWT)),
            ("AWSKEY", _regex_detector(_AWSKEY)),
            ("CRED", _regex_detector(_CRED_AT)),
            ("CRED", _regex_detector(_CRED_SPECIAL)),
            ("CRED", _group_detector(_CRED_SECRET_KV)),
            ("CRED", _group_detector(_CRED_USER_KV)),
            ("CRED", _group_detector(_CRED_PW_FLAG)),
            ("CRED", _group_detector(_CRED_USERPASS_FLAG)),
            ("IP", _regex_detector(_IP_GLUED)),
            ("BLOB", _regex_detector(_BLOB)),
            ("IP6", _regex_detector(_IP6)),
            *_builtin_detectors(),
            ("DOMAIN", _regex_detector(_DOMAIN)),
        ]

    def add_known(self, targets: list[str], ptype: str = "HOST") -> None:
        """Add engagement-known terms, masked with certainty by exact match.

        Covers what no detector — regex or model — reliably catches: bare Windows
        hostnames (``dc01``), NetBIOS names, and (with ``ptype="ORG"``) the
        client / engagement slug that shows up verbatim in workspace paths.
        Cross-domain PII models score F1 ~0.5 on names; ground truth scores 1.0.

        Re-sorted longest-first so a subdomain is replaced before its parent.
        """
        merged = set(self._known)
        merged.update((t, ptype) for t in targets if t)
        self._known = sorted(merged, key=lambda kv: len(kv[0]), reverse=True)

    def _placeholder(self, value: str, ptype: str) -> str:
        existing = self._map.get(value)
        if existing is not None:
            return existing
        n = self._counters.get(ptype, 0) + 1
        self._counters[ptype] = n
        token = f"<{ptype}_{n}>"
        self._map[value] = token
        return token

    def redact(self, text: str) -> str:
        """Return ``text`` with every detected target identifier masked."""
        if not text:
            return text
        spans: list[tuple[int, int, str, str]] = []  # (start, end, ptype, value)
        for target, ktype in self._known:
            # Case-insensitive: a hostname or project slug is written both ways
            # ("CodeAnt" in prose, "codeant" in a path). The matched TEXT is the
            # map key, so casing stays stable per spelling.
            for m in re.finditer(re.escape(target), text, re.IGNORECASE):
                spans.append((m.start(), m.end(), ktype, m.group(0)))
        for ptype, detect in self._detectors:
            for start, end, value in detect(text):
                spans.append((start, end, ptype, value))
        if not spans:
            return text
        # Resolve overlaps: earliest start, then longest, then highest priority.
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0]), _PRIORITY.get(s[2], 5)))
        chosen: list[tuple[int, int, str, str]] = []
        last_end = -1
        for start, end, ptype, value in spans:
            if start >= last_end:
                chosen.append((start, end, ptype, value))
                last_end = end
        # Assign placeholders in first-appearance order so numbering reads
        # naturally (the first host mentioned is <IP_1>); the map is stable so
        # later occurrences reuse it.
        for _start, _end, ptype, value in chosen:
            self._placeholder(value, ptype)
        # Replace right-to-left so earlier indices stay valid.
        out = text
        for start, end, ptype, value in sorted(chosen, key=lambda s: s[0], reverse=True):
            out = out[:start] + self._placeholder(value, ptype) + out[end:]
        return out

    def redact_obj(self, value: Any) -> Any:
        """Recursively redact every string in a dict/list/scalar structure.

        Keys are left intact (they are fixed field names); only values are masked.
        """
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, (list, tuple)):
            return [self.redact_obj(v) for v in value]
        if isinstance(value, dict):
            return {k: self.redact_obj(v) for k, v in value.items()}
        return value

    @property
    def mapping(self) -> dict[str, str]:
        """The session's real→placeholder map (kept LOCAL — never transmitted)."""
        return dict(self._map)
