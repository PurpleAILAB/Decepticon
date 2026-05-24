"""decepticon-core — contract layer for the Decepticon agent framework.

Pure types, protocols, plugin contracts, and registry primitives. This
package never imports ``langchain``, ``langgraph``, ``deepagents``,
``httpx``, or ``fastapi`` — see the design spec at
``docs/superpowers/specs/2026-05-23-core-framework-sdk-split-design.md``.

Phase 1.A status: ``types`` submodule extracted from the framework
(engagement / llm / kg). Subsequent commits add ``protocols``,
``contracts``, ``registry``, and ``utils`` per spec §6.1.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from decepticon_core import (
    contracts,
    plugin_loader,
    protocols,
    registry,
    types,
    utils,
)

try:
    # pyproject carries a "0.0.0" sentinel; release.yml stamps the real
    # tag into the wheel metadata at build time, and importlib.metadata
    # reads it back here. Local checkouts read 0.0.0.
    __version__ = _version("decepticon-core")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "contracts",
    "plugin_loader",
    "protocols",
    "registry",
    "types",
    "utils",
]
