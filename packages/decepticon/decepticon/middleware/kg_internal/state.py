"""KGState — agent-state extension owned by ``KGMiddleware``.

Three ``NotRequired`` fields stash KG-relevant context for the agent's
turn. The middleware's ``before_agent`` hook hydrates them; the
``wrap_model_call`` hook reads ``kg_summary`` and injects it into the
system message.

The state schema is auto-merged with the underlying ``AgentState`` at
``create_agent`` compile time (langchain middleware behavior) so the
agent's existing fields (messages, engagement_name, etc.) remain
untouched.
"""

from __future__ import annotations

from typing import Annotated, NotRequired

from langchain.agents import AgentState

from decepticon.middleware.state_reducers import reduce_converging_value


class KGState(AgentState):
    """State extension owned by ``KGMiddleware``.

    All fields are ``NotRequired`` so the schema is non-invasive — an
    agent built without the KG slot retains its original state surface.

    Each channel carries ``reduce_converging_value``. The KG slot runs in
    several subagent roles (analyst / contract_auditor / ad_operator), so an
    orchestrator that dispatches two of them in parallel writes these channels
    from concurrent branches. All three derive from the single shared
    ``KGStore`` (same engagement scope, same revision token, same rendered
    summary), so every branch carries the same value — last-write-wins is
    correct, and the reducer satisfies LangGraph's contract for parallel writes
    (without it, fan-out trips INVALID_CONCURRENT_GRAPH_UPDATE; cf. #183).
    """

    kg_engagement: NotRequired[
        Annotated[
            str,
            "Engagement scope label that every KG read / write is constrained to.",
            reduce_converging_value,
        ]
    ]
    kg_revision: NotRequired[
        Annotated[
            str,
            (
                "Opaque revision token returned by ``KGStore.revision``. "
                "When this differs from the prior turn the middleware "
                "rebuilds ``kg_summary``."
            ),
            reduce_converging_value,
        ]
    ]
    kg_summary: NotRequired[
        Annotated[
            str,
            (
                "Cached markdown summary block. Injected into the system "
                "message in ``wrap_model_call`` so the LLM sees current "
                "graph state without burning tokens on read tools."
            ),
            reduce_converging_value,
        ]
    ]
