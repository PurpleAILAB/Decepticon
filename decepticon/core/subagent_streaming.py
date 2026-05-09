"""Sub-agent streaming — live event emission during sub-agent execution.

When the Decepticon orchestrator delegates to a sub-agent via task(),
SubAgentMiddleware calls runnable.invoke() or runnable.ainvoke().

This module wraps the runnable so that both invoke() and ainvoke() use
stream()/astream() internally, emitting tool calls, results, and AI messages
through two channels:

  1. Renderer context var — for any Python-side renderer
  2. LangGraph stream writer — for LangGraph Platform HTTP API (custom events)

Architecture:
  StreamingRunnable wraps a compiled LangGraph agent
  → intercepts invoke()/ainvoke() → uses stream/astream(mode="values") internally
  → emits events via both channels
  → returns same result as invoke() for SubAgentMiddleware compatibility

IMPORTANT: LangGraph runs the agent graph asynchronously (all middleware uses
awrap_* methods). SubAgentMiddleware's atask() calls subagent.ainvoke(), so
the ainvoke() method MUST be implemented here — otherwise __getattr__ delegates
to the underlying runnable's ainvoke(), bypassing all streaming logic.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from typing import Any, Callable

from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolCall

log = logging.getLogger("decepticon.subagent_streaming")

# Context variable for the active renderer — set by StreamingEngine.run()
_active_renderer: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "subagent_renderer", default=None
)


def set_subagent_renderer(renderer: Any) -> contextvars.Token:
    """Set the active renderer for sub-agent streaming. Returns token for reset."""
    return _active_renderer.set(renderer)


def clear_subagent_renderer(token: contextvars.Token) -> None:
    """Reset the renderer context var."""
    _active_renderer.reset(token)


def _get_writer() -> Callable | None:
    """Get the LangGraph stream writer if available (for HTTP API streaming)."""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        log.debug("get_stream_writer() returned: %s", type(writer).__name__)
        return writer
    except Exception as e:
        log.warning("get_stream_writer() failed: %s: %s", type(e).__name__, e)
        return None


class StreamingRunnable:
    """Wraps a compiled LangGraph agent to stream events during invoke()/ainvoke().

    Drop-in replacement for the runnable field in CompiledSubAgent.

    Two streaming channels:
      - UIRenderer (contextvars): Used by Python-side renderers
      - get_stream_writer(): Used by LangGraph Platform HTTP API (custom events)

    If neither channel is available, falls back to plain invoke()/ainvoke().

    IMPORTANT: Both invoke() AND ainvoke() must be implemented because LangGraph
    runs agent graphs asynchronously — SubAgentMiddleware's atask() calls
    subagent.ainvoke(). Without ainvoke() here, __getattr__ would delegate to
    the underlying runnable's ainvoke(), bypassing all streaming event emission.
    """

    def __init__(self, runnable: Any, name: str):
        self._runnable = runnable
        self._name = name

    def _get_channels(self) -> tuple[Any, bool, Callable | None]:
        """Get renderer and writer channels. Returns (renderer, has_renderer, writer)."""
        renderer = _active_renderer.get(None)
        has_renderer = renderer is not None and hasattr(renderer, "on_subagent_start")
        writer = _get_writer()
        return renderer, has_renderer, writer

    def _extract_prompt(self, input: Any) -> str:
        """Extract human message prompt from input for display."""
        from langchain_core.messages import HumanMessage

        if isinstance(input, dict) and "messages" in input:
            msgs = input["messages"]
            if msgs and isinstance(msgs, list):
                for m in reversed(msgs):
                    if isinstance(m, HumanMessage):
                        return str(m.content)[:200]
        return ""

    def _emit_start(
        self, renderer: Any, has_renderer: bool, writer: Callable | None, prompt: str
    ) -> None:
        if has_renderer:
            renderer.on_subagent_start(self._name, prompt)
        if writer:
            writer({"type": "subagent_start", "agent": self._name, "prompt": prompt})

    def _emit_end(
        self,
        renderer: Any,
        has_renderer: bool,
        writer: Callable | None,
        elapsed: float,
        *,
        cancelled: bool = False,
        error: bool = False,
    ) -> None:
        if has_renderer:
            renderer.on_subagent_end(self._name, elapsed, cancelled=cancelled, error=error)
        if writer:
            writer(
                {
                    "type": "subagent_end",
                    "agent": self._name,
                    "elapsed": elapsed,
                    "cancelled": cancelled,
                    "error": error,
                }
            )

    def _process_messages(
        self,
        new_messages: list,
        active_tool_calls: dict[str, ToolCall],
        renderer: Any,
        has_renderer: bool,
        writer: Callable | None,
    ) -> None:
        """Process new messages and emit events to channels."""
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        for msg in new_messages:
            if isinstance(msg, HumanMessage):
                continue

            if isinstance(msg, AIMessage):
                text = msg.content
                if isinstance(text, list):
                    text = " ".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in text
                    ).strip()
                if text:
                    text = text.replace("<result>", "").replace("</result>", "").strip()
                    if text:
                        if has_renderer:
                            renderer.on_subagent_message(self._name, text)
                        if writer:
                            writer({"type": "subagent_message", "agent": self._name, "text": text})

                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        # ToolCall.id is `str | None` in the LangChain spec.
                        # Storing under a None key collides across multiple
                        # id-less calls and yields wrong-name lookups for the
                        # corresponding ToolMessage; skip and log instead so
                        # the result falls through to the "unknown" branch.
                        tc_id = tc.get("id")
                        if tc_id is None:
                            log.warning(
                                "subagent %r emitted tool call without id (tool=%s); "
                                "result will surface as 'unknown'",
                                self._name,
                                tc.get("name"),
                            )
                        else:
                            active_tool_calls[tc_id] = tc
                        tc_args = {
                            k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                            for k, v in tc["args"].items()
                        }
                        if has_renderer:
                            renderer.on_subagent_tool_call(self._name, tc["name"], tc["args"])
                        if writer:
                            writer(
                                {
                                    "type": "subagent_tool_call",
                                    "agent": self._name,
                                    "tool": tc["name"],
                                    "args": tc_args,
                                }
                            )

            elif isinstance(msg, ToolMessage):
                tc = active_tool_calls.get(msg.tool_call_id)
                tool_name = tc["name"] if tc else "unknown"
                tool_args = tc["args"] if tc else {}
                content = str(msg.content)
                status = getattr(msg, "status", "success") or "success"
                tc_args = {
                    k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                    for k, v in tool_args.items()
                }
                if has_renderer:
                    renderer.on_subagent_tool_result(self._name, tool_name, tool_args, content)
                if writer:
                    writer(
                        {
                            "type": "subagent_tool_result",
                            "agent": self._name,
                            "tool": tool_name,
                            "args": tc_args,
                            "content": content,
                            "status": status,
                        }
                    )

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        """Stream sub-agent execution (sync), emitting events to available channels."""
        log.info("[%s] invoke() called", self._name)
        renderer, has_renderer, writer = self._get_channels()
        log.info(
            "[%s] channels: has_renderer=%s, writer=%s",
            self._name,
            has_renderer,
            writer is not None,
        )

        if not has_renderer and writer is None:
            log.warning("[%s] No channels available — falling back to plain invoke()", self._name)
            return self._runnable.invoke(input, config, **kwargs)

        prompt = self._extract_prompt(input)
        self._emit_start(renderer, has_renderer, writer, prompt)

        start = time.monotonic()
        last_state = None
        last_count = 0
        active_tool_calls: dict[str, ToolCall] = {}

        try:
            for state in self._runnable.stream(
                input, config=config, stream_mode="values", **kwargs
            ):
                last_state = state
                messages = state.get("messages", [])
                new_messages = messages[last_count:]
                last_count = len(messages)
                self._process_messages(
                    new_messages, active_tool_calls, renderer, has_renderer, writer
                )

        except (KeyboardInterrupt, asyncio.CancelledError):
            log.info("[%s] invoke() cancelled", self._name)
            self._emit_end(renderer, has_renderer, writer, time.monotonic() - start, cancelled=True)
            raise
        except Exception as exc:
            log.error("[%s] invoke() failed: %s: %s", self._name, type(exc).__name__, exc)
            self._emit_end(renderer, has_renderer, writer, time.monotonic() - start, error=True)
            # Return error state instead of re-raising. Re-raising crashes the
            # ToolNode step, which prevents ToolMessages from being saved to the
            # thread state. On the next run, PatchToolCallsMiddleware finds the
            # dangling tool calls and injects "cancelled" messages, causing the
            # orchestrator to retry in an infinite loop.
            error_msg = f"Subagent '{self._name}' failed: {type(exc).__name__}: {exc}"
            if last_state is not None:
                last_state.setdefault("messages", []).append(AIMessage(content=error_msg))
                return last_state
            return {"messages": [AIMessage(content=error_msg)]}

        self._emit_end(renderer, has_renderer, writer, time.monotonic() - start)

        if last_state is None:
            # stream() yielded zero states. Re-invoking the sub-agent here
            # would double-execute every tool call (duplicate bash side
            # effects, duplicate graph writes). Surface the failure as a
            # synthetic error message on a fresh state so downstream
            # middleware sees a coherent "subagent ran, produced nothing"
            # instead of silently re-running the work.
            log.error("[%s] invoke() stream produced no state — returning error", self._name)
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"Subagent '{self._name}' produced no state from "
                            "stream(). Aborting rather than re-invoking to "
                            "avoid duplicate tool side effects."
                        )
                    )
                ]
            }

        return last_state

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        """Stream sub-agent execution (async), emitting events to available channels.

        This is the critical path — LangGraph runs the graph asynchronously,
        so SubAgentMiddleware's atask() calls subagent.ainvoke(). Without this
        method, streaming events would never be emitted to the CLI.
        """
        log.info("[%s] ainvoke() called", self._name)
        renderer, has_renderer, writer = self._get_channels()
        log.info(
            "[%s] channels: has_renderer=%s, writer=%s",
            self._name,
            has_renderer,
            writer is not None,
        )

        if not has_renderer and writer is None:
            log.warning("[%s] No channels available — falling back to plain ainvoke()", self._name)
            return await self._runnable.ainvoke(input, config, **kwargs)

        prompt = self._extract_prompt(input)
        self._emit_start(renderer, has_renderer, writer, prompt)

        start = time.monotonic()
        last_state = None
        last_count = 0
        active_tool_calls: dict[str, ToolCall] = {}

        try:
            async for state in self._runnable.astream(
                input, config=config, stream_mode="values", **kwargs
            ):
                last_state = state
                messages = state.get("messages", [])
                new_messages = messages[last_count:]
                last_count = len(messages)
                if new_messages:
                    log.debug(
                        "[%s] astream: %d new messages (total %d)",
                        self._name,
                        len(new_messages),
                        len(messages),
                    )
                self._process_messages(
                    new_messages, active_tool_calls, renderer, has_renderer, writer
                )

        except (KeyboardInterrupt, asyncio.CancelledError):
            log.info("[%s] ainvoke() cancelled", self._name)
            self._emit_end(renderer, has_renderer, writer, time.monotonic() - start, cancelled=True)
            raise
        except Exception as exc:
            log.error("[%s] ainvoke() failed: %s: %s", self._name, type(exc).__name__, exc)
            self._emit_end(renderer, has_renderer, writer, time.monotonic() - start, error=True)
            # Return error state instead of re-raising. Re-raising crashes the
            # ToolNode step, which prevents ToolMessages from being saved to the
            # thread state. On the next run, PatchToolCallsMiddleware finds the
            # dangling tool calls and injects "cancelled" messages, causing the
            # orchestrator to retry in an infinite loop.
            error_msg = f"Subagent '{self._name}' failed: {type(exc).__name__}: {exc}"
            if last_state is not None:
                last_state.setdefault("messages", []).append(AIMessage(content=error_msg))
                return last_state
            return {"messages": [AIMessage(content=error_msg)]}

        self._emit_end(renderer, has_renderer, writer, time.monotonic() - start)

        if last_state is None:
            # See the sync invoke() branch above: re-invoking here would
            # double-execute every tool. Return an explicit error state so
            # the orchestrator sees "subagent produced nothing" instead of
            # silently running the whole agent a second time.
            log.error("[%s] ainvoke() astream produced no state — returning error", self._name)
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"Subagent '{self._name}' produced no state from "
                            "astream(). Aborting rather than re-invoking to "
                            "avoid duplicate tool side effects."
                        )
                    )
                ]
            }

        return last_state

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access to the underlying runnable."""
        return getattr(self._runnable, name)
