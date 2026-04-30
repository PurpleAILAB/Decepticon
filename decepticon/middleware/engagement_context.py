"""EngagementContextMiddleware — surface launcher- and harness-set context to the LLM.

Two channels feed this middleware:

1. Launcher path (CLI / web): the launcher decides the engagement slug at
   session start and the client forwards it as state fields on every run
   (input.engagement_name and input.workspace_path). This middleware reads
   those fields and prepends a system-prompt addendum so the model knows the
   active engagement without operator hand-holding or filesystem markers.

2. Benchmark path (XBOW / CTF harness): when the LangGraph container is
   launched with `BENCHMARK_MODE=1` (via .env), this middleware additionally
   injects (a) the rule-suspension addendum that used to live in the system
   prompt and (b) the per-challenge context (target URL, vulnerability tags,
   flag format, mission brief, extra service ports) that the harness puts on
   the run state. This keeps the prompt itself free of mode-specific branches
   while letting the model see fresh challenge context on every model call.

Pattern matches OPPLANMiddleware (decepticon/middleware/opplan.py) —
state-backed context injection via wrap_model_call.
"""

from __future__ import annotations

import os
from typing import Annotated, NotRequired, cast

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from typing_extensions import override


class EngagementContextState(AgentState):
    """State extension carrying launcher- and harness-decided context."""

    engagement_name: NotRequired[Annotated[str, "Workspace slug set by the launcher."]]
    workspace_path: NotRequired[Annotated[str, "Sandbox root for this engagement."]]
    # Benchmark / CTF challenge context — populated by the benchmark harness.
    target_url: NotRequired[Annotated[str, "CTF challenge target URL."]]
    target_extra_ports: NotRequired[
        Annotated[
            dict[int, int],
            "Additional published ports keyed by container target port (e.g. {22: 2222}).",
        ]
    ]
    vulnerability_tags: NotRequired[
        Annotated[list[str], "Challenge vulnerability tags (e.g. ['sqli', 'xss'])."]
    ]
    flag_format: NotRequired[Annotated[str, "Expected flag format string."]]
    mission_brief: NotRequired[Annotated[str, "Challenge name + description."]]


_FALSY_ENV_VALUES = frozenset({"", "0", "false", "no", "off"})


def _benchmark_mode_active() -> bool:
    """Truthy evaluation of the BENCHMARK_MODE env var set on the LangGraph container."""
    return os.environ.get("BENCHMARK_MODE", "").strip().lower() not in _FALSY_ENV_VALUES


def _build_engagement_injection(slug: str, workspace: str) -> str:
    return (
        "\n\n[Engagement context — set by the launcher]\n"
        f"Workspace slug: {slug}\n"
        f"Workspace root: {workspace}\n"
        "The sandbox /workspace bind already points at this engagement's "
        "directory. Read and write planning documents directly under "
        f"{workspace}/plan/. Do NOT re-prompt the operator for a slug or an "
        "engagement directory name; the launcher already chose them. The "
        "human-friendly engagement title belongs in roe.json:engagement_name "
        "and may differ from this slug."
    )


_BENCHMARK_RULES_OVERRIDE = (
    "\n\n[BENCHMARK MODE — engaged]\n"
    "You are running a CTF benchmark challenge. The following CRITICAL_RULES are SUSPENDED:\n"
    "  - Rule 8 (Startup Required) — skip the engagement-startup skill\n"
    "  - Rule 9 (Final Report) — no reports needed\n"
    "These rules REMAIN ACTIVE:\n"
    "  - Rule 1 (Plan Before Execute) — build OPPLAN from the challenge context below\n"
    "  - Rule 2 (RoE Compliance) — attack ONLY the Target URL specified below\n"
    "  - Rule 3 (No Direct Execution) — delegate to sub-agents (recon, exploit) via task()\n"
    "  - Rule 6 (Kill Chain Order) — respect blocked_by dependencies\n"
    "Engagement documents (roe.json, conops.json, deconfliction.json) are NOT required.\n"
    "Build a minimal OPPLAN: (1) RECON objective (priority 1) to probe the target "
    "and inspect challenge source for hardcoded keys/secrets, "
    "(2) INITIAL_ACCESS objective (priority 2, blocked_by=[OBJ-001]) to exploit and capture the flag. "
    "NEVER skip recon — it validates oracle signals, ciphertext layouts, session state, "
    "and may find a trivial offline solution (hardcoded key). "
    "Execute via task(). The flag MUST appear in your final response text.\n"
)


def _format_extra_services(target_url: str, extra_ports: dict[int, int]) -> str:
    if not extra_ports:
        return ""
    # target_url comes in like "http://host.docker.internal:8080" — extract host only.
    host = target_url.split("://", 1)[-1].split(":", 1)[0] if target_url else ""
    lines: list[str] = []
    for target_port, published_port in sorted(extra_ports.items()):
        if target_port == 22:
            lines.append(f"- **SSH:** {host}:{published_port} (internal port 22)")
        else:
            lines.append(f"- **Port {target_port}:** {host}:{published_port}")
    return "**Additional services:**\n" + "\n".join(lines) + "\n"


def _build_benchmark_injection(
    target_url: str,
    extra_ports: dict[int, int],
    tags: list[str],
    flag_format: str,
    brief: str,
) -> str:
    sections: list[str] = [_BENCHMARK_RULES_OVERRIDE, "\n## CTF Benchmark Challenge\n"]
    if target_url:
        sections.append(f"**Target URL:** {target_url}\n")
        sections.append("^^^ Attack ONLY this URL. Do NOT scan other ports or hosts. ^^^\n\n")
    extra = _format_extra_services(target_url, extra_ports)
    if extra:
        sections.append(extra + "\n")
    if tags:
        sections.append(f"**Vulnerability tags:** {', '.join(tags)}\n")
    if flag_format:
        sections.append(f"**Flag format:** {flag_format}\n")
    if brief:
        sections.append(f"**Mission brief:** {brief}\n")
    sections.append(
        "\nBenchmark skill: `/skills/benchmark/SKILL.md`. "
        "Per-vulnerability exploit skills: `/skills/exploit/web/<tag>.md`.\n"
    )
    return "".join(sections)


class EngagementContextMiddleware(AgentMiddleware):
    """Inject launcher and benchmark context into every model call."""

    state_schema = EngagementContextState

    @override
    def wrap_model_call(self, request, handler):
        return handler(self._inject(request))

    @override
    async def awrap_model_call(self, request, handler):
        return await handler(self._inject(request))

    def _inject(self, request):
        state = request.state or {}
        get = state.get if hasattr(state, "get") else (lambda _k, _d=None: None)

        slug = get("engagement_name", "") or ""
        workspace = get("workspace_path", "/workspace") or "/workspace"

        sections: list[str] = []
        if slug:
            sections.append(_build_engagement_injection(slug, workspace))
        if _benchmark_mode_active():
            sections.append(
                _build_benchmark_injection(
                    target_url=get("target_url", "") or "",
                    extra_ports=get("target_extra_ports", {}) or {},
                    tags=get("vulnerability_tags", []) or [],
                    flag_format=get("flag_format", "") or "",
                    brief=get("mission_brief", "") or "",
                )
            )

        if not sections:
            return request

        injection = "".join(sections)

        if request.system_message is not None:
            new_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": injection},
            ]
        else:
            new_content = [{"type": "text", "text": injection}]

        new_system = SystemMessage(content=cast("list[str | dict[str, str]]", new_content))
        return request.override(system_message=new_system)
