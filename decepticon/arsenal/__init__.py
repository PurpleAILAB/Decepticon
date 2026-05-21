"""Arsenal — single MCP server exposing pentest binaries as typed tools.

Inspired by hexstrike-ai's FastMCP pattern: instead of writing a per-tool
Python wrapper for every CLI in Kali's arsenal, expose them all through
one MCP server with declarative tool descriptors. Decepticon agents call
nmap, ffuf, sqlmap, nuclei, etc. as typed MCP tools without per-tool
maintenance.

The arsenal is **declarative** — each tool is a ToolSpec describing its
command-line, arg schema, output parser, and success criteria. The runner
shells out via the existing DockerSandbox (so tools execute in the
container, not the host).

Usage::

    from decepticon.arsenal import build_arsenal_server, REGISTRY
    server = build_arsenal_server(sandbox)
    server.run()  # FastMCP server, picks up STDIO transport by default

Or for direct integration into Decepticon's agent middleware stack,
import REGISTRY and adapt each ToolSpec into a LangChain @tool.
"""

from __future__ import annotations

from decepticon.arsenal.registry import REGISTRY, ToolSpec, build_arsenal_server

__all__ = ["REGISTRY", "ToolSpec", "build_arsenal_server"]
