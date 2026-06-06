"""``decepticon-mcp`` / ``python -m decepticon.mcp_server`` entrypoint.

The MCP SDK is an optional dependency, so the import of the server module is
deferred and guarded: a missing ``mcp`` package yields a one-line install hint
and a clean non-zero exit rather than a traceback.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from decepticon.mcp_server.config import ServerConfig, load_config

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
    parser.add_argument(
        "--auth",
        choices=["none", "shared-secret", "jwt"],
        default=None,
        help=(
            "Auth mode for the streamable-http transport. Unset → inferred: "
            "DECEPTICON_MCP_TOKEN ⇒ shared-secret; --issuer + key ⇒ jwt; else none. "
            "The shared-secret value is read only from DECEPTICON_MCP_TOKEN, never argv."
        ),
    )
    parser.add_argument("--issuer", default=None, help="JWT issuer (iss) to require.")
    parser.add_argument("--audience", default=None, help="JWT audience (aud) to require.")
    parser.add_argument("--jwks-uri", default=None, help="JWKS endpoint for the JWT signing key.")
    parser.add_argument(
        "--auth-public-key",
        default=None,
        help="Static JWT public key (filesystem path or inline PEM).",
    )
    parser.add_argument(
        "--resource-url",
        default=None,
        help="Public URL of this bridge (OAuth resource id); defaults to host:port.",
    )
    parser.add_argument(
        "--required-scope",
        action="append",
        default=None,
        metavar="SCOPE",
        help="Scope a JWT must carry to be authorized (repeatable).",
    )
    return parser


def _apply_cli(config: ServerConfig, args: argparse.Namespace) -> ServerConfig:
    """Overlay CLI flags onto the env-derived config (CLI wins when set)."""
    updates: dict[str, object] = {}
    if args.langgraph_url:
        updates["langgraph_url"] = args.langgraph_url
    if args.auth:
        updates["auth_mode"] = args.auth
    if args.issuer:
        updates["issuer"] = args.issuer
    if args.audience:
        updates["audience"] = args.audience
    if args.jwks_uri:
        updates["jwks_uri"] = args.jwks_uri
    if args.auth_public_key:
        updates["public_key"] = args.auth_public_key
    if args.resource_url:
        updates["resource_url"] = args.resource_url
    if args.required_scope:
        updates["required_scopes"] = tuple(args.required_scope)
    return replace(config, **updates) if updates else config


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        from decepticon.mcp_server.auth import open_bind_error, resolve_auth_mode
        from decepticon.mcp_server.server import build_server
    except ImportError:
        print(_INSTALL_HINT, file=sys.stderr)
        return 2

    config = _apply_cli(load_config(), args)
    err = open_bind_error(resolve_auth_mode(config), args.transport, args.host)
    if err:
        print(err, file=sys.stderr)
        return 2

    try:
        server = build_server(config, host=args.host, port=args.port)
    except ValueError as exc:
        print(f"decepticon-mcp: {exc}", file=sys.stderr)
        return 2
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
