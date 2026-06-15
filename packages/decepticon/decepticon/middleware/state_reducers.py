"""Shared LangGraph state-channel reducers.

A reducer is REQUIRED on any agent-state channel that more than one
concurrent graph branch may write in the same superstep. The canonical
trigger is an orchestrator that dispatches several subagents in one turn
(parallel ``task()`` calls): each branch carries the shared middleware
state back on join, and LangGraph rejects the simultaneous writes with
``INVALID_CONCURRENT_GRAPH_UPDATE`` unless the channel declares how to
merge them. (``OmitFromInput`` does NOT prevent this — see #183, which
had to add a reducer to ``workspace_path`` despite it being
``OmitFromInput``.)

``reduce_converging_value`` is the merge for **convergent** channels:
every concurrent writer derives the same value from a single source of
truth (the launcher config, the benchmark harness, or a shared store),
so last-write-wins on a non-None value is both correct and sufficient.

This is deliberately NOT a fit for *accumulating* channels (a growing
list, a monotonic counter) — there last-write-wins would silently drop a
branch's contribution, so those need a structural merge (merge-by-id,
max(), etc.) or must be confined to a single writer instead.
"""

from __future__ import annotations

from typing import TypeVar

_T = TypeVar("_T")


def reduce_converging_value(current: _T | None, update: _T | None) -> _T | None:
    """Last-write-wins-on-non-None merge for convergent state channels.

    Use for any channel whose concurrent writers all carry the same value
    (launcher-set context, benchmark-harness context, shared-store-derived
    summaries). Mirrors the semantics of ``opplan._reduce_engagement_name``
    / ``_reduce_workspace_path`` generically over the value type, so it also
    covers ``dict`` / ``list`` channels. Returns ``update`` unless it is
    ``None``, in which case the prior value is preserved.
    """
    return update if update is not None else current
