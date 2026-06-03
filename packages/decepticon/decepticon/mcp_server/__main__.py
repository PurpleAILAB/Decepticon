"""``decepticon-mcp`` / ``python -m decepticon.mcp_server`` entrypoint.

The MCP SDK is an optional dependency, so the import of the server module is
deferred and guarded: a missing ``mcp`` package yields a one-line install hint
and a clean non-zero exit rather than a traceback.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from decepticon.mcp_server.config import load_config

_INSTALL_HINT = (
    "decepticon-mcp requires the optional 'mcp' dependency. "
    "Install it with:  pip install 'decepticon[mcp]'"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="decepticon-mcp",
        description=(
            "Expose Decepticon engagement control over MCP "
            "(for OpenClaw, Hermes, or any MCP client)."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for the streamable-http transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port for the streamable-http transport.",
    )
    parser.add_argument(
        "--langgraph-url",
        default=None,
        help="Override the Decepticon LangGraph URL (default: $DECEPTICON_API_URL).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        from decepticon.mcp_server.server import build_server
    except ImportError:
        print(_INSTALL_HINT, file=sys.stderr)
        return 2

    config = load_config()
    if args.langgraph_url:
        config = replace(config, langgraph_url=args.langgraph_url)
    server = build_server(config, host=args.host, port=args.port)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
