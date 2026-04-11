"""Classified string extraction from a binary blob.

``strings(1)``-equivalent plus category tagging. Every string is
classified into a high-signal bucket:

- ``url``       — http/https/ftp/ws URLs
- ``ip``        — IPv4/IPv6 literals
- ``email``     — RFC-ish email addresses
- ``path``      — filesystem paths (Unix + Windows)
- ``crypto``    — hex keys (16/32/64 byte), PEM markers, known S-box hints
- ``version``   — X.Y.Z(.W) version strings
- ``format``    — printf-style format strings (LPM candidate)
- ``secret``    — looks like a credential / API key / token (heuristic)
- ``import``    — likely library/function name
- ``text``      — everything else

Categories are useful for auto-populating the knowledge graph: URLs
become potential entrypoints, crypto hits become secret candidates,
versions become CVE lookup seeds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_STRING_LEN = 4

_ASCII_RE = re.compile(rb"[\x20-\x7e]{%d,}" % MIN_STRING_LEN)
_UTF16LE_RE = re.compile((rb"(?:[\x20-\x7e]\x00){%d,}" % MIN_STRING_LEN))


# Category patterns — all unanchored so they substring-match inside a
# printable run (strings(1) may return a run like "visit https://evil.com
# for fun" as a single token and we still want to classify it as a URL).
_URL_RE = re.compile(r"\b(?:https?|ftp|ws)://[^\s<>\"'`]+", re.IGNORECASE)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_EMAIL_RE = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")
_PATH_RE = re.compile(r"(?:/[A-Za-z0-9_.\-]+){2,}|[A-Z]:\\(?:[^\\\s]+\\)+[^\\\s]+")
_VERSION_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)?(?:\.\d+)?(?:[-_][\w.+]+)?\b")
_FORMAT_RE = re.compile(r"%[-+0# ]?(?:\d+)?(?:\.\d+)?[hljztL]?[dDiufFgGeEsScCpxXoabn]")
_HEX_KEY_RE = re.compile(r"\b[0-9A-Fa-f]{32,}\b")
_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----")
_SECRET_RE = re.compile(
    r"""(?:
        sk[-_][A-Za-z0-9]{20,} |                    # stripe-style secret key
        \bAKIA[0-9A-Z]{16}\b |                      # AWS access key
        \bAIza[0-9A-Za-z\-_]{35}\b |                # Google API key
        \bghp_[A-Za-z0-9]{36}\b |                   # GitHub PAT
        \bgho_[A-Za-z0-9]{36}\b |
        \bxox[baprs]-[A-Za-z0-9\-]{10,}\b |         # Slack token
        eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}   # JWT
    )""",
    re.VERBOSE,
)
_IMPORT_HINTS = {
    "malloc",
    "free",
    "memcpy",
    "strcpy",
    "strcat",
    "printf",
    "sprintf",
    "fopen",
    "fread",
    "fwrite",
    "fork",
    "exec",
    "execve",
    "system",
    "socket",
    "bind",
    "listen",
    "accept",
    "connect",
    "recv",
    "send",
    "LoadLibraryA",
    "GetProcAddress",
    "VirtualAlloc",
    "VirtualProtect",
    "CreateThread",
    "CreateProcessA",
    "WinExec",
    "ShellExecuteA",
    "NtCreateThreadEx",
    "NtUnmapViewOfSection",
    "NtMapViewOfSection",
}


@dataclass
class ExtractedString:
    offset: int
    text: str
    encoding: str
    category: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": f"0x{self.offset:x}",
            "text": self.text[:256],
            "encoding": self.encoding,
            "category": self.category,
        }


def _classify(s: str) -> str:
    # Ordering matters — more specific categories before generic ones.
    if _URL_RE.search(s):
        return "url"
    ip_m = _IP_RE.search(s)
    if ip_m:
        parts = ip_m.group(0).split(".")
        try:
            if all(0 <= int(p) <= 255 for p in parts):
                return "ip"
        except ValueError:
            pass
    if _PEM_RE.search(s):
        return "crypto"
    m = _HEX_KEY_RE.search(s)
    if m and len(m.group(0)) in (32, 40, 48, 56, 64, 96, 128):
        return "crypto"
    if _SECRET_RE.search(s):
        return "secret"
    if _EMAIL_RE.search(s):
        return "email"
    if _PATH_RE.search(s):
        return "path"
    if _FORMAT_RE.search(s):
        return "format"
    if _VERSION_RE.search(s):
        return "version"
    if s in _IMPORT_HINTS or any(hint in s for hint in _IMPORT_HINTS):
        return "import"
    return "text"


def extract_strings(
    data: bytes | str | Path,
    *,
    min_length: int = MIN_STRING_LEN,
    include_utf16: bool = True,
) -> list[ExtractedString]:
    """Extract printable ASCII / UTF-16LE strings with category tags."""
    if isinstance(data, (str, Path)):
        blob = Path(data).read_bytes()
    else:
        blob = data

    pat = re.compile(rb"[\x20-\x7e]{%d,}" % max(min_length, 2))
    results: list[ExtractedString] = []
    for m in pat.finditer(blob):
        raw = m.group().decode("ascii", errors="replace")
        results.append(
            ExtractedString(
                offset=m.start(),
                text=raw,
                encoding="ascii",
                category=_classify(raw),
            )
        )

    if include_utf16:
        utf_pat = re.compile((rb"(?:[\x20-\x7e]\x00){%d,}" % max(min_length, 2)))
        for m in utf_pat.finditer(blob):
            raw = m.group().decode("utf-16-le", errors="replace").rstrip("\x00")
            if len(raw) >= min_length:
                results.append(
                    ExtractedString(
                        offset=m.start(),
                        text=raw,
                        encoding="utf16le",
                        category=_classify(raw),
                    )
                )
    return results


def group_by_category(strings: list[ExtractedString]) -> dict[str, list[ExtractedString]]:
    """Group extracted strings by category, preserving order."""
    out: dict[str, list[ExtractedString]] = {}
    for s in strings:
        out.setdefault(s.category, []).append(s)
    return out
