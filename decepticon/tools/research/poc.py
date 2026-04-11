"""PoC validator + CVSS estimator.

Takes a PoC script (bash, python, curl invocation, http request text) and
runs it inside the Docker sandbox against the target. The validator looks
for caller-defined success indicators ("reflected payload", "HTTP 500
with stack trace", "shell spawned") and marks the associated vulnerability
node as ``validated=True`` on hit, alongside provenance (raw output hash,
stdout/stderr excerpt, exit code).

A ZFP (Zero-False-Positive) layer demands *both* a success signal AND
a negative control (same request without payload) to differentiate
"works because of payload" from "works anyway". Optional but strongly
recommended for bounty reports.

CVSS estimation
---------------
If the PoC confirms exploitation, :class:`CVSSVector` is built from
caller-provided access flags (AV/AC/PR/UI/S/C/I/A). The base score is
computed with the standard v3.1 formula so the agent can attach a
defensible score to each validated finding without reaching for an
external calculator.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

from decepticon.core.logging import get_logger
from decepticon.tools.research.graph import (
    Edge,
    EdgeKind,
    KnowledgeGraph,
    Node,
    NodeKind,
    Severity,
)

log = get_logger("research.poc")


# ── CVSS v3.1 base score ────────────────────────────────────────────────


class AV(StrEnum):
    NETWORK = "N"
    ADJACENT = "A"
    LOCAL = "L"
    PHYSICAL = "P"


class AC(StrEnum):
    LOW = "L"
    HIGH = "H"


class PR(StrEnum):
    NONE = "N"
    LOW = "L"
    HIGH = "H"


class UI(StrEnum):
    NONE = "N"
    REQUIRED = "R"


class Scope(StrEnum):
    UNCHANGED = "U"
    CHANGED = "C"


class Impact(StrEnum):
    NONE = "N"
    LOW = "L"
    HIGH = "H"


_AV_VALUE = {AV.NETWORK: 0.85, AV.ADJACENT: 0.62, AV.LOCAL: 0.55, AV.PHYSICAL: 0.2}
_AC_VALUE = {AC.LOW: 0.77, AC.HIGH: 0.44}
_UI_VALUE = {UI.NONE: 0.85, UI.REQUIRED: 0.62}
_IMPACT_VALUE = {Impact.NONE: 0.0, Impact.LOW: 0.22, Impact.HIGH: 0.56}
_PR_UNCHANGED = {PR.NONE: 0.85, PR.LOW: 0.62, PR.HIGH: 0.27}
_PR_CHANGED = {PR.NONE: 0.85, PR.LOW: 0.68, PR.HIGH: 0.5}


@dataclass
class CVSSVector:
    av: AV = AV.NETWORK
    ac: AC = AC.LOW
    pr: PR = PR.NONE
    ui: UI = UI.NONE
    scope: Scope = Scope.UNCHANGED
    c: Impact = Impact.HIGH
    i: Impact = Impact.HIGH
    a: Impact = Impact.HIGH

    def to_vector_string(self) -> str:
        return (
            f"CVSS:3.1/AV:{self.av.value}/AC:{self.ac.value}/PR:{self.pr.value}/"
            f"UI:{self.ui.value}/S:{self.scope.value}/"
            f"C:{self.c.value}/I:{self.i.value}/A:{self.a.value}"
        )

    def base_score(self) -> float:
        """Compute CVSS v3.1 base score per spec.

        Reference: https://www.first.org/cvss/v3.1/specification-document
        """
        iss = 1 - (
            (1 - _IMPACT_VALUE[self.c]) * (1 - _IMPACT_VALUE[self.i]) * (1 - _IMPACT_VALUE[self.a])
        )
        if self.scope == Scope.UNCHANGED:
            impact = 6.42 * iss
        else:
            impact = 7.52 * (iss - 0.029) - 3.25 * math.pow(iss - 0.02, 15)
        pr_val = _PR_UNCHANGED[self.pr] if self.scope == Scope.UNCHANGED else _PR_CHANGED[self.pr]
        exploitability = (
            8.22 * _AV_VALUE[self.av] * _AC_VALUE[self.ac] * pr_val * _UI_VALUE[self.ui]
        )
        if impact <= 0:
            return 0.0
        if self.scope == Scope.UNCHANGED:
            base = min(impact + exploitability, 10.0)
        else:
            base = min(1.08 * (impact + exploitability), 10.0)
        # CVSS rounds up to 1 decimal
        return math.ceil(base * 10) / 10

    def to_severity(self) -> Severity:
        score = self.base_score()
        if score >= 9.0:
            return Severity.CRITICAL
        if score >= 7.0:
            return Severity.HIGH
        if score >= 4.0:
            return Severity.MEDIUM
        if score > 0.0:
            return Severity.LOW
        return Severity.INFO


# ── PoC validation ──────────────────────────────────────────────────────


@dataclass
class PoCResult:
    """Outcome of a PoC validation run."""

    validated: bool
    vuln_id: str
    summary: str
    success_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    exit_code: int | None = None
    cvss: str | None = None
    cvss_score: float | None = None
    severity: str | None = None
    output_hash: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "validated": self.validated,
            "vuln_id": self.vuln_id,
            "summary": self.summary,
            "success_signals": self.success_signals,
            "negative_signals": self.negative_signals,
            "stdout_excerpt": self.stdout_excerpt[:800],
            "stderr_excerpt": self.stderr_excerpt[:400],
            "exit_code": self.exit_code,
            "cvss": self.cvss,
            "cvss_score": self.cvss_score,
            "severity": self.severity,
            "output_hash": self.output_hash,
            "duration_seconds": round(self.duration_seconds, 3),
        }


# Any awaitable that takes a bash command and returns (stdout, stderr, exit_code).
PoCRunner = Callable[[str], Awaitable[tuple[str, str, int]]]


def _hash_output(stdout: str, stderr: str, exit_code: int) -> str:
    h = hashlib.sha1()
    h.update(stdout.encode("utf-8", errors="replace"))
    h.update(b"||")
    h.update(stderr.encode("utf-8", errors="replace"))
    h.update(f"||{exit_code}".encode())
    return h.hexdigest()[:16]


def _match_signals(blob: str, patterns: list[str]) -> list[str]:
    """Return the subset of patterns whose regex matches the blob."""
    matched: list[str] = []
    for pat in patterns:
        try:
            if re.search(pat, blob, re.DOTALL | re.IGNORECASE):
                matched.append(pat)
        except re.error:
            if pat.lower() in blob.lower():
                matched.append(pat)
    return matched


async def validate_poc(
    *,
    vuln_id: str,
    poc_command: str,
    success_patterns: list[str],
    runner: PoCRunner,
    negative_command: str | None = None,
    negative_patterns: list[str] | None = None,
    cvss: CVSSVector | None = None,
    graph: KnowledgeGraph | None = None,
) -> PoCResult:
    """Run a PoC command and evaluate against success/negative patterns.

    If ``graph`` is provided, the vuln node is updated with ``validated=True``
    and a ``FINDING`` node is created with a ``VALIDATES`` edge back to it.
    A failed validation is still recorded (``validated=False``) so the
    analyst can iterate without losing attempt history.
    """
    start = time.monotonic()
    stdout, stderr, code = await runner(poc_command)
    duration = time.monotonic() - start
    combined = f"{stdout}\n{stderr}"
    success = _match_signals(combined, success_patterns)

    neg_hits: list[str] = []
    if negative_command and negative_patterns:
        n_out, n_err, _ = await runner(negative_command)
        n_combined = f"{n_out}\n{n_err}"
        neg_hits = _match_signals(n_combined, negative_patterns)
        # ZFP: if the negative control also matched any success pattern,
        # the signal was noise and we demote.
        if _match_signals(n_combined, success_patterns):
            log.warning("vuln %s: negative control also matched — demoting", vuln_id)
            success = []

    validated = bool(success) and not neg_hits
    summary = f"{len(success)} success signals, {len(neg_hits)} negative hits, exit={code}"
    cvss_vec_str: str | None = None
    cvss_score: float | None = None
    sev: str | None = None
    if cvss is not None:
        cvss_vec_str = cvss.to_vector_string()
        cvss_score = cvss.base_score()
        sev = cvss.to_severity().value

    result = PoCResult(
        validated=validated,
        vuln_id=vuln_id,
        summary=summary,
        success_signals=success,
        negative_signals=neg_hits,
        stdout_excerpt=stdout[:1600],
        stderr_excerpt=stderr[:800],
        exit_code=code,
        cvss=cvss_vec_str,
        cvss_score=cvss_score,
        severity=sev,
        output_hash=_hash_output(stdout, stderr, code),
        duration_seconds=duration,
    )

    if graph is not None:
        _persist_result(graph, result)

    return result


def _persist_result(graph: KnowledgeGraph, result: PoCResult) -> None:
    """Write validation outcome into the graph."""
    vuln = graph.nodes.get(result.vuln_id)
    if vuln is None:
        log.warning("validate_poc: vuln node %s not found in graph", result.vuln_id)
        return
    vuln.props["validated"] = result.validated
    vuln.props["validated_at"] = time.time()
    vuln.props["output_hash"] = result.output_hash
    if result.severity:
        vuln.props["severity"] = result.severity
    if result.cvss_score is not None:
        vuln.props["cvss_score"] = result.cvss_score
        vuln.props["cvss_vector"] = result.cvss
    vuln.updated_at = time.time()

    finding_label = (
        f"validated: {vuln.label[:80]}" if result.validated else f"rejected: {vuln.label[:80]}"
    )
    finding = Node.make(
        NodeKind.FINDING,
        finding_label,
        key=f"finding::{result.output_hash}",
        validated=result.validated,
        vuln_id=result.vuln_id,
        summary=result.summary,
        stdout_excerpt=result.stdout_excerpt[:400],
        exit_code=result.exit_code,
        cvss_score=result.cvss_score,
    )
    graph.upsert_node(finding)
    graph.upsert_edge(Edge.make(finding.id, vuln.id, EdgeKind.VALIDATES))
    graph.upsert_edge(Edge.make(finding.id, vuln.id, EdgeKind.MAPS_TO))


# ── Convenience: build a runner from a DockerSandbox ────────────────────


def sandbox_runner(sandbox: Any) -> PoCRunner:
    """Adapt a ``DockerSandbox`` into a :data:`PoCRunner` callable.

    The sandbox must expose ``execute_tmux_async`` (or ``execute_tmux``) that
    returns a str output. We split the returned blob on ``[Exit code:`` to
    recover an exit code when present.
    """

    async def _run(command: str) -> tuple[str, str, int]:
        try:
            if hasattr(sandbox, "execute_tmux_async"):
                out = await sandbox.execute_tmux_async(
                    command=command, session="poc", timeout=60, is_input=False
                )
            else:
                out = await asyncio.to_thread(
                    sandbox.execute_tmux,
                    command=command,
                    session="poc",
                    timeout=60,
                    is_input=False,
                )
        except Exception as e:  # pragma: no cover — defensive
            return "", str(e), -1
        code = 0
        m = re.search(r"\[Exit code:\s*(-?\d+)", out)
        if m:
            try:
                code = int(m.group(1))
            except ValueError:
                pass
        return out, "", code

    return _run
