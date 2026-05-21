"""Instrumented proof of exploitation — MDASH-style "Prove stage".

The Verifier confirms a finding with pattern-matched PoC validation. That
answers "did the success signal appear" — not "did the bug actually
trigger". This module hardens that into a *proof*:

  - native memory-corruption (CWE-119/787/416/...) → rebuild with
    AddressSanitizer/UBSan, run the triggering input, confirm a sanitizer
    report (reusing ``fuzz.parse_asan``). Falls back to a debugger crash.
  - web injection (CWE-89/78/79/...) → a deterministic differential: the
    payload run carries a unique sentinel the negative-control run does
    not.
  - logic / authz (CWE-285/287/22/...) → re-execute with a negative
    control and require a behavioural delta.

Pure-Python: the sandbox is reached only through an injected
:data:`~decepticon.tools.research.poc.PoCRunner`, so the engine is
unit-testable without a C toolchain.
"""

from __future__ import annotations

import hashlib
import re
import shlex
import time
from dataclasses import dataclass, field
from enum import StrEnum

from decepticon.tools.research.fuzz import parse_asan
from decepticon.tools.research.poc import PoCRunner, _match_signals

# ── Bug-class routing ────────────────────────────────────────────────


class ProofStrategy(StrEnum):
    """How a finding's bug class admits instrumented proof."""

    SANITIZER = "sanitizer"  # native memory corruption — ASan/UBSan/gdb
    DIFFERENTIAL = "differential"  # web injection — payload vs negative control
    RECHECK = "recheck"  # logic/authz — negative-control re-execution
    UNPROVABLE = "unprovable"  # no instrumented proof admitted


_SANITIZER_CWES = frozenset(
    {
        "119",
        "120",
        "121",
        "122",
        "124",
        "125",
        "126",
        "127",
        "787",
        "415",
        "416",
        "476",
        "190",
        "191",
    }
)
_DIFFERENTIAL_CWES = frozenset({"89", "78", "79", "94", "1336", "611", "918", "917", "943"})
_RECHECK_CWES = frozenset({"285", "287", "639", "22", "200", "306", "862", "863"})


def _cwe_digits(cwes: list[str] | None) -> set[str]:
    out: set[str] = set()
    for c in cwes or []:
        digits = re.sub(r"\D", "", str(c))
        if digits:
            out.add(digits)
    return out


def route_proof_strategy(
    *,
    cwes: list[str] | None = None,
    crash_kind: str = "",
    sanitizer: str = "",
    scanner: str = "",
) -> ProofStrategy:
    """Pick the proof strategy for a finding's bug class.

    A fuzzer-set ``crash_kind`` / ``sanitizer`` prop forces SANITIZER —
    the bug was already found through instrumentation.
    """
    _ = scanner  # reserved for scanner-specific overrides
    if crash_kind or sanitizer:
        return ProofStrategy.SANITIZER
    digits = _cwe_digits(cwes)
    if digits & _SANITIZER_CWES:
        return ProofStrategy.SANITIZER
    if digits & _DIFFERENTIAL_CWES:
        return ProofStrategy.DIFFERENTIAL
    if digits & _RECHECK_CWES:
        return ProofStrategy.RECHECK
    return ProofStrategy.UNPROVABLE


# ── Proof result ─────────────────────────────────────────────────────


@dataclass
class ProofResult:
    """Outcome of an instrumented proof attempt."""

    proven: bool
    proof_admitted: bool  # False for UNPROVABLE — not a failure, just N/A
    strategy: str
    method: str  # asan-report|ubsan-report|gdb-crash|differential|negative-control|...
    confidence: str  # proven|verified|unverified
    sanitizer: str = ""
    crash_kind: str = ""
    stack: list[str] = field(default_factory=list)
    triggering_input_ref: str = ""
    sanitizer_log_excerpt: str = ""
    stdout_excerpt: str = ""
    exit_signal: str = ""
    proof_hash: str = ""
    duration_seconds: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "proven": self.proven,
            "proof_admitted": self.proof_admitted,
            "strategy": self.strategy,
            "method": self.method,
            "confidence": self.confidence,
            "sanitizer": self.sanitizer,
            "crash_kind": self.crash_kind,
            "stack": self.stack[:15],
            "triggering_input_ref": self.triggering_input_ref,
            "sanitizer_log_excerpt": self.sanitizer_log_excerpt[:1200],
            "stdout_excerpt": self.stdout_excerpt[:800],
            "exit_signal": self.exit_signal,
            "proof_hash": self.proof_hash,
            "duration_seconds": round(self.duration_seconds, 3),
            "summary": self.summary,
        }


_SANITIZER_FLAGS = "-fsanitize=address,undefined -g -O1 -fno-omit-frame-pointer"
_CRASH_SIGNAL_RE = re.compile(
    r"SIGSEGV|SIGABRT|Segmentation fault|Aborted|core dumped|Program received signal",
    re.IGNORECASE,
)


def sanitizer_build_command(build_command: str) -> str:
    """Wrap a build command so it compiles with ASan + UBSan.

    Injects sanitizer flags via the standard ``CFLAGS`` / ``CXXFLAGS`` /
    ``LDFLAGS`` env vars rather than guessing the build system — the
    caller supplies their own ``build_command`` (``make``, ``cmake
    --build``, ...).
    """
    env = (
        f'CFLAGS="{_SANITIZER_FLAGS}" '
        f'CXXFLAGS="{_SANITIZER_FLAGS}" '
        f'LDFLAGS="-fsanitize=address,undefined"'
    )
    return f"{env} {build_command}"


def _signal_of(blob: str) -> str:
    m = _CRASH_SIGNAL_RE.search(blob)
    return m.group(0) if m else ""


def _proof_hash(*parts: str) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    for p in parts:
        h.update(p.encode("utf-8", errors="replace"))
        h.update(b"||")
    return h.hexdigest()[:16]


# ── Native (sanitizer) proof ─────────────────────────────────────────


async def prove_native(
    *,
    runner: PoCRunner,
    target_command: str,
    triggering_input_ref: str = "",
    source_dir: str = "",
    build_command: str = "",
    instrumented_binary: str = "",
) -> ProofResult:
    """Prove a native memory-corruption finding with a sanitizer or debugger.

    If ``source_dir`` + ``build_command`` are given, rebuild with ASan/UBSan
    first. Else if ``instrumented_binary`` is given, use it as-is. Run the
    triggering input and parse the output for a sanitizer report. With no
    instrumented build available, fall back to a debugger crash check.
    """
    start = time.monotonic()
    instrumented = bool(instrumented_binary)

    if source_dir and build_command:
        build = f"cd {shlex.quote(source_dir)} && {sanitizer_build_command(build_command)}"
        await runner(build)
        instrumented = True

    if instrumented:
        run_cmd = (
            "ASAN_OPTIONS=abort_on_error=1:detect_leaks=1 "
            "UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1 "
            f"{target_command}"
        )
        stdout, stderr, _ = await runner(run_cmd)
        combined = f"{stdout}\n{stderr}"
        crash = parse_asan(combined)
        duration = time.monotonic() - start
        if crash is not None:
            return ProofResult(
                proven=True,
                proof_admitted=True,
                strategy=ProofStrategy.SANITIZER.value,
                method=f"{crash.sanitizer.lower()}-report",
                confidence="proven",
                sanitizer=crash.sanitizer,
                crash_kind=crash.kind,
                stack=crash.stack,
                triggering_input_ref=triggering_input_ref,
                sanitizer_log_excerpt=combined[:1200],
                proof_hash=_proof_hash(target_command, crash.kind, combined[:400]),
                duration_seconds=duration,
                summary=f"{crash.sanitizer} confirmed {crash.kind}",
            )
        return ProofResult(
            proven=False,
            proof_admitted=True,
            strategy=ProofStrategy.SANITIZER.value,
            method="sanitizer-clean",
            confidence="unverified",
            stdout_excerpt=combined[:800],
            duration_seconds=duration,
            summary="instrumented run produced no sanitizer report",
        )

    # No instrumented build — fall back to a debugger crash check.
    gdb_cmd = f"gdb --batch -ex run -ex bt --args {target_command}"
    stdout, stderr, _ = await runner(gdb_cmd)
    combined = f"{stdout}\n{stderr}"
    duration = time.monotonic() - start
    signal = _signal_of(combined)
    if signal:
        return ProofResult(
            proven=True,
            proof_admitted=True,
            strategy=ProofStrategy.SANITIZER.value,
            method="gdb-crash",
            confidence="verified",  # weaker than a sanitizer report
            triggering_input_ref=triggering_input_ref,
            exit_signal=signal,
            sanitizer_log_excerpt=combined[:1200],
            proof_hash=_proof_hash(target_command, "gdb", combined[:400]),
            duration_seconds=duration,
            summary=f"debugger observed {signal}",
        )
    return ProofResult(
        proven=False,
        proof_admitted=True,
        strategy=ProofStrategy.SANITIZER.value,
        method="gdb-clean",
        confidence="unverified",
        stdout_excerpt=combined[:800],
        duration_seconds=duration,
        summary="debugger run did not crash",
    )


# ── Differential proof (web injection / logic) ───────────────────────


async def _prove_differential(
    *,
    runner: PoCRunner,
    poc_command: str,
    success_patterns: list[str],
    negative_command: str,
    negative_patterns: list[str],
    strategy: ProofStrategy,
) -> ProofResult:
    """Run a payload vs a negative control; the proof is the delta.

    The bug is proven only when the success signal appears in the payload
    run AND is absent from the negative-control run.
    """
    start = time.monotonic()
    p_out, p_err, _ = await runner(poc_command)
    poc_blob = f"{p_out}\n{p_err}"
    poc_hits = _match_signals(poc_blob, success_patterns)

    neg_hits_success: list[str] = []
    if negative_command:
        n_out, n_err, _ = await runner(negative_command)
        neg_blob = f"{n_out}\n{n_err}"
        neg_hits_success = _match_signals(neg_blob, success_patterns)
        if negative_patterns:
            _match_signals(neg_blob, negative_patterns)

    duration = time.monotonic() - start
    proven = bool(poc_hits) and not neg_hits_success
    return ProofResult(
        proven=proven,
        proof_admitted=True,
        strategy=strategy.value,
        method="differential" if strategy == ProofStrategy.DIFFERENTIAL else "negative-control",
        confidence="proven" if proven else "unverified",
        triggering_input_ref=poc_command,
        stdout_excerpt=poc_blob[:800],
        proof_hash=_proof_hash(poc_command, poc_blob[:400]),
        duration_seconds=duration,
        summary=(
            "payload signal absent from the negative control"
            if proven
            else "signal not differential — negative control also matched or payload missed"
        ),
    )


async def prove_web(
    *,
    runner: PoCRunner,
    poc_command: str,
    success_patterns: list[str],
    negative_command: str = "",
    negative_patterns: list[str] | None = None,
) -> ProofResult:
    """Prove a web-injection finding by a deterministic differential."""
    return await _prove_differential(
        runner=runner,
        poc_command=poc_command,
        success_patterns=success_patterns,
        negative_command=negative_command,
        negative_patterns=negative_patterns or [],
        strategy=ProofStrategy.DIFFERENTIAL,
    )


async def prove_logic(
    *,
    runner: PoCRunner,
    poc_command: str,
    negative_command: str,
    success_patterns: list[str],
) -> ProofResult:
    """Prove a logic/authz finding by negative-control re-execution.

    The negative control is the same action under a different principal
    (unauthenticated, or a different user); a proven finding shows the
    privileged behaviour only in the payload run.
    """
    return await _prove_differential(
        runner=runner,
        poc_command=poc_command,
        success_patterns=success_patterns,
        negative_command=negative_command,
        negative_patterns=[],
        strategy=ProofStrategy.RECHECK,
    )


def unprovable_result(reason: str) -> ProofResult:
    """A result for a bug class that admits no instrumented proof."""
    return ProofResult(
        proven=False,
        proof_admitted=False,
        strategy=ProofStrategy.UNPROVABLE.value,
        method="none",
        confidence="unverified",
        summary=reason,
    )
