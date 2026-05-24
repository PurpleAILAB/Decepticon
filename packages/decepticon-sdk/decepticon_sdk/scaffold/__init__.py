"""Plugin scaffolding CLI — ``decepticon-sdk plugin new --kind=...``.

Phase 3 of the core/framework/sdk split (per
``docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md``)
ships a typer-based generator so plugin authors run one command and
get a buildable plugin package: pyproject.toml, src/<name>/__init__.py
wired to the right entry-point group, and a short README.

Six plugin kinds covered: ``tool``, ``middleware``, ``agent``,
``callback``, ``skill``, ``prompt``.

Usage:

    decepticon-sdk plugin new --kind=middleware --name=my-plugin --path=./my-plugin
"""

from __future__ import annotations

from decepticon_sdk.scaffold.cli import app

__all__ = ["app"]
