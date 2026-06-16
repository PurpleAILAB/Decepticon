"""Crash triage and exploitability classification.

Pure-Python parser for AddressSanitizer output and signal-based crash
dumps. No subprocess calls — feed it the captured crash text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ASAN frame: "    #3 0x55ab in foo /src/foo.c:42:7"
_FRAME_RE = re.compile(r"#\d+\s+0x[0-9a-fA-F]+\s+in\s+(.+)")
# ASAN error line: "ERROR: AddressSanitizer: heap-buffer-overflow on address 0x..."
_ASAN_ERROR_RE = re.compile(
    r"AddressSanitizer:\s+([a-z0-9\-]+)(?:\s+on\s+(?:unknown\s+)?address\s+(0x[0-9a-fA-F]+))?"
)
_SUMMARY_RE = re.compile(r"SUMMARY:\s+.*", re.IGNORECASE)
# Signal-based crash: "SIGSEGV", "SIGABRT", with optional address
_SIGNAL_RE = re.compile(r"\b(SIG[A-Z]+)\b")
_ADDR_RE = re.compile(r"address\s+(0x[0-9a-fA-F]+)", re.IGNORECASE)

_EXPLOITABLE = {"heap-buffer-overflow", "use-after-free", "double-free", "heap-use-after-free"}
_PROBABLY_EXPLOITABLE = {"stack-buffer-overflow", "global-buffer-overflow", "stack-overflow"}
_PROBABLY_NOT = {"null-deref", "null-dereference"}

# Faulting addresses at or below this are treated as null-deref territory.
_LOW_ADDR = 0x1000


@dataclass
class CrashAnalysis:
    """Result of ``triage_crash``."""

    crash_type: str
    severity: str  # exploitable | probably-exploitable | probably-not | unknown
    faulting_address: str
    stack_frames: list[str] = field(default_factory=list)
    asan_summary: str = ""
    exploitability_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "crash_type": self.crash_type,
            "severity": self.severity,
            "faulting_address": self.faulting_address,
            "stack_frames": list(self.stack_frames),
            "asan_summary": self.asan_summary,
            "exploitability_notes": self.exploitability_notes,
        }


def _addr_value(addr: str) -> int | None:
    try:
        return int(addr, 16)
    except (ValueError, TypeError):
        return None


def _classify(crash_type: str, faulting_address: str) -> tuple[str, str]:
    """Return (severity, notes) for a crash type + faulting address."""
    if crash_type in _EXPLOITABLE:
        return (
            "exploitable",
            f"{crash_type} corrupts heap metadata / object lifetime — "
            "primitive for arbitrary write or controlled allocation.",
        )
    if crash_type in _PROBABLY_EXPLOITABLE:
        return (
            "probably-exploitable",
            f"{crash_type} can overwrite return address / adjacent locals; "
            "exploitability depends on stack canary and layout.",
        )

    addr = _addr_value(faulting_address)
    if crash_type in _PROBABLY_NOT or (addr is not None and addr < _LOW_ADDR):
        return (
            "probably-not",
            "Faulting address is in the null page — likely a null-pointer "
            "dereference, typically a DoS rather than a control-flow primitive.",
        )

    return ("unknown", "Crash type not recognized; manual analysis required.")


def triage_crash(crash_output: str, binary_path: str = "") -> CrashAnalysis:
    """Parse ASAN or signal-based crash output into a CrashAnalysis."""
    stack_frames = [m.group(1).strip() for m in _FRAME_RE.finditer(crash_output)]

    summary_match = _SUMMARY_RE.search(crash_output)
    asan_summary = summary_match.group(0).strip() if summary_match else ""

    asan_match = _ASAN_ERROR_RE.search(crash_output)
    if asan_match:
        crash_type = asan_match.group(1)
        faulting_address = asan_match.group(2) or ""
    else:
        # Fall back to signal-based parsing.
        signal_match = _SIGNAL_RE.search(crash_output)
        addr_match = _ADDR_RE.search(crash_output)
        faulting_address = addr_match.group(1) if addr_match else ""
        if signal_match and signal_match.group(1) == "SIGSEGV":
            crash_type = (
                "null-deref"
                if _addr_value(faulting_address) is not None
                and _addr_value(faulting_address) < _LOW_ADDR
                else "segv"
            )
        elif signal_match:
            crash_type = signal_match.group(1).lower()
        else:
            crash_type = "unknown"

    severity, notes = _classify(crash_type, faulting_address)

    if not asan_summary and stack_frames:
        asan_summary = f"crash in {stack_frames[0]}"

    return CrashAnalysis(
        crash_type=crash_type,
        severity=severity,
        faulting_address=faulting_address,
        stack_frames=stack_frames,
        asan_summary=asan_summary,
        exploitability_notes=notes,
    )
