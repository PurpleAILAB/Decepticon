"""Active validation of finding/vulnerability nodes (false-positive reduction).

Where :mod:`decepticon.tools.research.poc` validates a vuln against a
*hand-authored* PoC command, this module derives a probe **from the node
itself** and runs it: it reads the target URL/endpoint and vuln class off a
graph node, builds a minimal HTTP probe (reflected-XSS reflection check,
API-key acceptance check, or a plain reachability check), runs it through an
injected :data:`~decepticon.tools.research.poc.PoCRunner`, and writes the
outcome back onto the node:

- on a confirmed hit → ``validated: true`` (and any stale ``false-positive``
  flag is cleared);
- on a miss or a refused/failed probe → ``false-positive: true``.

The probe-running side effect is fully injectable (the ``runner`` argument),
so :func:`run_active_validation` is unit-testable with a stub runner and no
network or sandbox. The :func:`validate_finding` tool wires the real
``HTTPSandbox`` runner in.
"""

from __future__ import annotations

import shlex
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import tool

from decepticon.tools.research._state import _json, graph_transaction
from decepticon.tools.research.poc import (
    POC_ERR_SANDBOX,
    POC_ERR_TIMEOUT,
    PoCRunner,
    _match_signals,
)
from decepticon_core.types.kg import KnowledgeGraph, Node

_URL_PROP_KEYS: tuple[str, ...] = ("url", "endpoint", "matched_at", "target")
_KEY_PROP_KEYS: tuple[str, ...] = ("key_value", "api_key", "token", "secret", "credential")

# Probe classes.
CHECK_REFLECTED_XSS = "reflected-xss"
CHECK_KEY_ACCEPTED = "key-accepted"
CHECK_REACHABILITY = "reachability"
CHECK_MISSING = "missing"
CHECK_UNPROBEABLE = "unprobeable"

# Stable, harmless reflection marker. Unique enough not to occur in static
# markup by accident; the angle brackets prove the payload was reflected
# WITHOUT HTML-encoding (the actual XSS condition).
_XSS_MARKER = "dcptnXSS9134"
_XSS_PAYLOAD = f"<script>{_XSS_MARKER}</script>"


@dataclass(frozen=True)
class ProbeSpec:
    """A deterministic, runner-agnostic description of an active probe."""

    check: str
    command: str
    success_patterns: list[str]
    negative_command: str | None = None
    negative_patterns: list[str] | None = None


@dataclass
class ValidationResult:
    """Outcome of an active validation probe."""

    finding_id: str
    check: str
    validated: bool
    false_positive: bool
    refused: bool
    summary: str
    command: str = ""
    success_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    stdout_excerpt: str = ""
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "check": self.check,
            "validated": self.validated,
            "false_positive": self.false_positive,
            "refused": self.refused,
            "summary": self.summary,
            "command": self.command,
            "success_signals": self.success_signals,
            "negative_signals": self.negative_signals,
            "stdout_excerpt": self.stdout_excerpt[:800],
            "exit_code": self.exit_code,
        }


def _first_str_prop(node: Node, keys: Sequence[str]) -> str:
    for key in keys:
        value = node.props.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _classification_blob(node: Node) -> str:
    """Lowercased haystack used to classify the probe (label + type + cwe)."""
    parts: list[str] = [node.label or "", str(node.props.get("type") or "")]
    cwe = node.props.get("cwe")
    if isinstance(cwe, str):
        parts.append(cwe)
    elif isinstance(cwe, (list, tuple)):
        parts.extend(str(c) for c in cwe)  # pyright: ignore[reportUnknownArgumentType]
    return " ".join(parts).lower()


def _is_xss(blob: str) -> bool:
    return "xss" in blob or "cross-site scripting" in blob or "cwe-79" in blob


def _is_key_acceptance(blob: str) -> bool:
    if any(tok in blob for tok in ("cwe-287", "cwe-306", "cwe-798", "cwe-321")):
        return True
    return any(
        tok in blob
        for tok in ("api key", "api-key", "apikey", "auth bypass", "broken auth", "access key")
    )


def derive_probe(node: Node) -> ProbeSpec | None:
    """Build a deterministic probe for ``node`` from its stored props.

    Returns ``None`` when the node carries no probe target (URL/endpoint),
    because an active check is impossible without one.
    """
    url = _first_str_prop(node, _URL_PROP_KEYS)
    if not url:
        return None
    q_url = shlex.quote(url)
    blob = _classification_blob(node)

    if _is_xss(blob):
        # Send the marker payload as a query param; success = it comes back
        # verbatim (un-encoded). Negative control = same URL with no payload
        # (baseline must still respond; if the marker shows up there too the
        # "reflection" is static content, not the injected param → demote).
        payload = shlex.quote(_XSS_PAYLOAD)
        command = f"curl -s -i -G {q_url} --data-urlencode dcptn={payload}"
        return ProbeSpec(
            check=CHECK_REFLECTED_XSS,
            command=command,
            success_patterns=[_XSS_PAYLOAD],
            negative_command=f"curl -s -i {q_url}",
            negative_patterns=[r"HTTP/\d"],
        )

    if _is_key_acceptance(blob):
        key = _first_str_prop(node, _KEY_PROP_KEYS) or _first_str_prop(node, ("payload",))
        auth = shlex.quote(f"Authorization: Bearer {key}")
        # success = endpoint accepts the key (2xx). Negative control = same
        # request WITHOUT the key; if that ALSO returns 2xx the endpoint is
        # simply open and "key acceptance" is unproven → demote.
        command = f'curl -s -o /dev/null -w "%{{http_code}}" -H {auth} {q_url}'
        return ProbeSpec(
            check=CHECK_KEY_ACCEPTED,
            command=command,
            success_patterns=[r"\b2\d\d\b"],
            negative_command=f'curl -s -o /dev/null -w "%{{http_code}}" {q_url}',
            negative_patterns=[r"\b(401|403)\b"],
        )

    # Fallback: prove the asset is reachable at all (weak signal, no negative
    # control — used when the vuln class is not one we can actively confirm).
    command = f'curl -s -o /dev/null -w "%{{http_code}}" {q_url}'
    return ProbeSpec(
        check=CHECK_REACHABILITY,
        command=command,
        success_patterns=[r"\b[23]\d\d\b"],
    )


def _is_refusal(stdout: str, stderr: str, exit_code: int) -> bool:
    """A sandbox/transport-level refusal: the probe never reached the target."""
    if stderr.startswith(POC_ERR_TIMEOUT) or stderr.startswith(POC_ERR_SANDBOX):
        return True
    # curl: 7 = connection refused, 28 = operation timeout, 6 = DNS failure.
    if exit_code in {6, 7, 28} and not stdout.strip():
        return True
    return False


def _apply_status(node: Node, *, validated: bool) -> None:
    """Persist the validation verdict onto the node's props."""
    node.props["validated_at"] = time.time()
    if validated:
        node.props["validated"] = True
        node.props["false-positive"] = False
    else:
        node.props["validated"] = False
        node.props["false-positive"] = True
    node.updated_at = time.time()


async def run_active_validation(
    *,
    finding_id: str,
    graph: KnowledgeGraph,
    runner: PoCRunner,
) -> ValidationResult:
    """Probe ``finding_id`` and write ``validated`` / ``false-positive`` back.

    The ``runner`` is an injected ``(command) -> (stdout, stderr, exit_code)``
    awaitable (see :func:`decepticon.tools.research.poc.sandbox_runner`), so
    this function is fully testable without a live sandbox.

    Behaviour:

    - missing node → no mutation, ``check="missing"``.
    - node without a URL/endpoint → no mutation, ``check="unprobeable"``.
    - probe runs: success patterns matched AND (no negative control, or the
      negative control behaved as expected) AND the probe was not refused →
      ``validated: true``. Anything else (miss, demotion, refusal) →
      ``false-positive: true``.
    """
    node = graph.nodes.get(finding_id)
    if node is None:
        return ValidationResult(
            finding_id=finding_id,
            check=CHECK_MISSING,
            validated=False,
            false_positive=False,
            refused=False,
            summary="finding node not found in graph",
        )

    spec = derive_probe(node)
    if spec is None:
        return ValidationResult(
            finding_id=finding_id,
            check=CHECK_UNPROBEABLE,
            validated=False,
            false_positive=False,
            refused=False,
            summary="no probe target (url/endpoint) on node; status unchanged",
        )

    stdout, stderr, code = await runner(spec.command)
    combined = f"{stdout}\n{stderr}"
    refused = _is_refusal(stdout, stderr, code)
    success_signals = _match_signals(combined, spec.success_patterns)

    negative_signals: list[str] = []
    neg_ran = bool(spec.negative_command and spec.negative_patterns)
    if neg_ran:
        n_out, n_err, _ = await runner(spec.negative_command or "")
        n_combined = f"{n_out}\n{n_err}"
        negative_signals = _match_signals(n_combined, spec.negative_patterns or [])
        # Zero-false-positive: if the negative control also fired a success
        # pattern, the signal was noise, not the injected condition.
        if _match_signals(n_combined, spec.success_patterns):
            success_signals = []

    validated = (
        bool(success_signals) and (not neg_ran or bool(negative_signals)) and not refused
    )
    _apply_status(node, validated=validated)

    if refused:
        verdict = "refused"
    elif validated:
        verdict = "validated"
    else:
        verdict = "rejected"
    summary = (
        f"{spec.check}: {verdict} — {len(success_signals)} success, "
        f"{len(negative_signals)} negative, neg_ran={neg_ran}, exit={code}"
    )

    return ValidationResult(
        finding_id=finding_id,
        check=spec.check,
        validated=validated,
        false_positive=not validated,
        refused=refused,
        summary=summary,
        command=spec.command,
        success_signals=success_signals,
        negative_signals=negative_signals,
        stdout_excerpt=stdout[:1600],
        exit_code=code,
    )


@tool("kg_validate_finding")
async def validate_finding(finding_id: str) -> str:
    """Actively validate a finding node to cut false positives.

    WHEN TO USE: after a finding/vulnerability node exists in the graph and
    you want to confirm it is real WITHOUT hand-writing a PoC. This probes
    the node's own target: a reflected-XSS reflection check, an API-key
    acceptance check, or a reachability check, picked from the node's vuln
    class and stored props (url/endpoint, cwe, payload, key_value).

    The node is updated in place: ``validated: true`` on a confirmed hit
    (clearing any stale ``false-positive`` flag), or ``false-positive: true``
    when the probe misses, is demoted by its negative control, or is
    refused/times out. This is the LLM-free counterpart to the PoC-driven
    ``validate_finding`` runner.

    Args:
        finding_id: Graph id of the finding/vulnerability node to probe.

    Returns:
        JSON validation record (check type, verdict, matched signals,
        stdout excerpt, exit code).
    """
    from decepticon.tools.bash.bash import get_sandbox
    from decepticon.tools.research.poc import sandbox_runner

    sandbox = get_sandbox()
    if sandbox is None:
        return _json({"error": "HTTPSandbox not initialized"})

    with graph_transaction() as graph:
        runner = sandbox_runner(sandbox)
        result = await run_active_validation(finding_id=finding_id, graph=graph, runner=runner)
        return _json(result.to_dict())
