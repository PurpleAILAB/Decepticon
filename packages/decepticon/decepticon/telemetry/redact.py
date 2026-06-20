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
_CRED_SPECIAL = re.compile(r"\b[\w.-]+:[^\s:@/]*[!@#$%^&*+=][^\s:@/]*")
# Bare host/domain — requires a non-numeric TLD so "1.2.3"/"x86_64" never match.
_DOMAIN = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b", re.IGNORECASE)

# Local-regex fallbacks for the LangChain built-ins (used only if the import fails).
_IP = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_IP6 = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")
_URL = re.compile(r"\bhttps?://[^\s)\]\"'<>]+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _regex_detector(pattern: re.Pattern[str]) -> _Detector:
    def detect(text: str) -> list[tuple[int, int, str]]:
        return [(m.start(), m.end(), m.group(0)) for m in pattern.finditer(text)]

    return detect


# Lower rank = higher priority when two matches overlap.
_PRIORITY = {"HOST": 0, "KEY": 1, "JWT": 1, "AWSKEY": 1, "CRED": 2}


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
        self._known: list[str] = sorted({k for k in (known or []) if k}, key=len, reverse=True)
        # Custom classes (no library ships these) + always-on IPv6 fallback, then
        # the LangChain built-ins, then bare-domain last (least specific).
        self._detectors: list[tuple[str, _Detector]] = [
            ("KEY", _regex_detector(_KEY)),
            ("JWT", _regex_detector(_JWT)),
            ("AWSKEY", _regex_detector(_AWSKEY)),
            ("CRED", _regex_detector(_CRED_AT)),
            ("CRED", _regex_detector(_CRED_SPECIAL)),
            ("IP6", _regex_detector(_IP6)),
            *_builtin_detectors(),
            ("DOMAIN", _regex_detector(_DOMAIN)),
        ]

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
        for target in self._known:
            for m in re.finditer(re.escape(target), text):
                spans.append((m.start(), m.end(), "HOST", target))
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
