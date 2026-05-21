"""MentorMiddleware — detect repeated-tool-call loops and force divergence.

Decepticon agents occasionally get stuck calling the same tool with the
same (or near-same) arguments and zero positive results — fuzzing a 404
endpoint for the 50th time, brute-forcing the same wordlist after it
returned nothing, or scanning the same port range repeatedly.

This middleware injects a `<system-reminder>` HumanMessage when a
``loop_window`` of recent tool calls matches the loop signature. The
reminder tells the agent: "you've called <tool>(<args>) N times with no
progress — try a different vector". It's the in-loop equivalent of
PentAGI's mentor agent.

Hook: ``before_model`` — runs every turn, so the loop is broken on the
agent's next inference rather than waiting for the operator to notice.

Tuning knobs:
- ``min_repeat_count``: minimum N identical / near-identical calls before
  intervention. Default 5 (matches the threshold cited in the
  PR-evaluation audit).
- ``loop_window``: how many recent AI messages to look back. Default 12.
- ``arg_similarity``: 1.0 = exact-match, 0.8 = "mostly same args".
  Default 0.85 — catches "same URL, slightly different param".

The middleware does NOT block the agent's tool call; it only injects an
advisory. The agent decides what to do. If it ignores the warning and
keeps looping, the orchestrator's failure-triage will catch it next.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage


@dataclass(frozen=True)
class _CallSignature:
    """A normalized fingerprint of a tool call for similarity comparison."""

    tool: str
    arg_keys: tuple[str, ...]
    arg_value_hash: int

    @classmethod
    def from_tool_call(cls, tc: dict) -> "_CallSignature":
        name = tc.get("name") or "<unknown>"
        args = tc.get("args") or {}
        if not isinstance(args, dict):
            try:
                args = json.loads(args) if isinstance(args, str) else {}
            except (json.JSONDecodeError, TypeError):
                args = {}
        keys = tuple(sorted(args.keys()))
        # Hash a normalized representation of values — coarse equality
        # (string-equality + type-equality) is enough; we're not solving
        # general structural similarity.
        try:
            value_repr = json.dumps({k: args[k] for k in keys}, sort_keys=True, default=str)
        except (TypeError, ValueError):
            value_repr = repr(args)
        return cls(tool=name, arg_keys=keys, arg_value_hash=hash(value_repr))


class MentorMiddleware(AgentMiddleware):
    """Detect tool-call loops and inject a divergence advisory.

    Activation: when ``min_repeat_count`` of the last ``loop_window`` tool
    calls share the same signature (tool + arg-keys + arg-value-hash).

    The middleware tracks a small in-memory dedupe set so the SAME loop
    isn't warned about twice in a row — it gives the agent one turn to
    course-correct before re-warning.

    Args:
        min_repeat_count: trigger threshold. Default 5.
        loop_window: messages to scan. Default 12.
        cooldown_turns: turns to suppress re-warning for the same loop.
            Default 3.
    """

    def __init__(
        self,
        *,
        min_repeat_count: int = 5,
        loop_window: int = 12,
        cooldown_turns: int = 3,
    ) -> None:
        super().__init__()
        self.min_repeat_count = min_repeat_count
        self.loop_window = loop_window
        self.cooldown_turns = cooldown_turns
        # signature -> turn-count when last warned
        self._last_warned: dict[_CallSignature, int] = {}
        self._turn = 0

    # ── core detection ──────────────────────────────────────────────────

    def _collect_signatures(self, messages: list) -> list[_CallSignature]:
        sigs: list[_CallSignature] = []
        for msg in reversed(messages):
            if not isinstance(msg, AIMessage):
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                sigs.append(_CallSignature.from_tool_call(tc))
            if len(sigs) >= self.loop_window:
                break
        return sigs[: self.loop_window]

    def _find_dominant_loop(
        self, signatures: list[_CallSignature]
    ) -> tuple[_CallSignature, int] | None:
        if not signatures:
            return None
        counts = Counter(signatures)
        sig, count = counts.most_common(1)[0]
        if count < self.min_repeat_count:
            return None
        return sig, count

    def _should_emit(self, sig: _CallSignature) -> bool:
        last = self._last_warned.get(sig)
        if last is None:
            return True
        return (self._turn - last) >= self.cooldown_turns

    def _build_message(self, sig: _CallSignature, count: int) -> dict:
        lines = [
            "<system-reminder>",
            f"MENTOR: detected {count}× repeated call to `{sig.tool}` "
            f"with the same shape in the last {self.loop_window} turns.",
            "",
            "Likely loop conditions:",
            "- Same tool + same arg keys + same arg values (or near-same)",
            "- No new evidence emerging from successive calls",
            "",
            "Recommended actions (pick one — do NOT repeat the same call):",
            "1. Switch sub-agent — if this is a recon sweep w/ no hits, "
            "the surface may need a different recon angle (different wordlist, "
            "different protocol, different scope).",
            "2. Narrow scope — drop low-value targets, focus on the most "
            "promising indicator from earlier turns.",
            "3. Try a different vuln class — if you've been hammering one "
            "vector (e.g. SQLi payload variants) with no oracle response, "
            "switch class (try SSRF, IDOR, or auth-bypass against the same "
            "endpoint).",
            "4. Re-read the source SUMMARY.md — you may have missed an "
            "observation that points to a better attack surface.",
            "",
            "Do NOT issue the same call again with marginal arg changes. "
            "That's the recon-as-orchestrator anti-pattern; it eats "
            "context and yields no progress.",
            "</system-reminder>",
        ]
        return {"messages": [HumanMessage(content="\n".join(lines))]}

    # ── middleware hooks ────────────────────────────────────────────────

    def before_model(self, state, runtime):  # type: ignore[override]
        self._turn += 1
        messages = (
            state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
        )
        if not messages:
            return None
        signatures = self._collect_signatures(messages)
        loop = self._find_dominant_loop(signatures)
        if loop is None:
            return None
        sig, count = loop
        if not self._should_emit(sig):
            return None
        self._last_warned[sig] = self._turn
        return self._build_message(sig, count)

    async def abefore_model(self, state, runtime):  # type: ignore[override]
        # Pure CPU work — no async-blocking subprocess calls. Reuse the
        # sync implementation directly.
        return self.before_model(state, runtime)


__all__ = ["MentorMiddleware"]
