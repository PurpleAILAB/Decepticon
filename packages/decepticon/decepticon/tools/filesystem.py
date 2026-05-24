"""Filesystem tool-surface helpers for Decepticon middleware."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def filesystem_tools_without_execute(tools: Sequence[Any]) -> list[Any]:
    """Return filesystem tools with the generic execute tool removed.

    Decepticon routes command execution through its dedicated bash tools, while
    Deep Agents' filesystem middleware owns file operations. Keeping this
    selection helper in ``decepticon.tools`` makes the public tool surface
    explicit and keeps middleware focused on backend scoping.
    """
    return [tool for tool in tools if getattr(tool, "name", None) != "execute"]


__all__ = ["filesystem_tools_without_execute"]
