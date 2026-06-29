"""Plugin marketplace — discover, install, and manage community plugins.

Reads the canonical plugin registry (``registry.json`` shipped alongside this
module) and exposes a typed API for listing available plugins, resolving
dependencies, and activating bundles at runtime via the existing
``decepticon.graph_registry`` mechanism.

The marketplace is intentionally read-only in v1: plugins are listed and
their metadata surfaced, but actual installation is delegated to ``pip``
(or ``uv pip``) by the caller. A future iteration will add direct
install + integrity verification.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginStatus(str, Enum):
    """Installation state of a marketplace plugin."""

    AVAILABLE = "available"
    INSTALLED = "installed"
    ACTIVE = "active"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class PluginMeta:
    """Metadata for a single marketplace plugin."""

    name: str
    version: str
    description: str
    author: str
    license: str
    category: str
    entry_point: str
    min_decepticon_version: str = ""
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    sha256: str = ""


def _load_registry(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the plugin registry JSON.

    Args:
        path: Explicit path to ``registry.json``. When *None* (default),
            reads the file co-located with this module via
            ``importlib.resources``.

    Returns:
        List of raw plugin descriptor dicts.
    """
    if path is not None:
        text = path.read_text(encoding="utf-8")
    else:
        registry_file = files("decepticon.plugins").joinpath("registry.json")
        text = registry_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
    data = json.loads(text)
    if not isinstance(data, dict) or "plugins" not in data:
        raise ValueError("registry.json must contain a top-level 'plugins' array")
    return data["plugins"]


def _parse_plugin(raw: dict[str, Any]) -> PluginMeta:
    """Parse a raw registry dict into a typed ``PluginMeta``."""
    return PluginMeta(
        name=raw["name"],
        version=raw["version"],
        description=raw["description"],
        author=raw.get("author", ""),
        license=raw.get("license", ""),
        category=raw.get("category", "uncategorized"),
        entry_point=raw["entry_point"],
        min_decepticon_version=raw.get("min_decepticon_version", ""),
        dependencies=raw.get("dependencies", []),
        tags=raw.get("tags", []),
        homepage=raw.get("homepage", ""),
        sha256=raw.get("sha256", ""),
    )


class Marketplace:
    """Read-only plugin marketplace backed by ``registry.json``.

    Typical usage::

        mp = Marketplace()
        for plugin in mp.list_plugins():
            print(f"{plugin.name} ({plugin.version}): {plugin.description}")

        info = mp.get_plugin("vuln-enricher")
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._plugins: dict[str, PluginMeta] = {}
        self._load(registry_path)

    def _load(self, path: Path | None) -> None:
        """Parse the registry and populate the internal index."""
        try:
            raw_list = _load_registry(path)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            logger.warning("Failed to load plugin registry; marketplace empty")
            return
        for raw in raw_list:
            try:
                meta = _parse_plugin(raw)
                self._plugins[meta.name] = meta
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping malformed plugin entry: %s", exc)

    def list_plugins(self, *, category: str | None = None) -> list[PluginMeta]:
        """Return all known plugins, optionally filtered by category.

        Args:
            category: If set, return only plugins matching this category.

        Returns:
            Sorted list of ``PluginMeta`` instances.
        """
        plugins = list(self._plugins.values())
        if category is not None:
            plugins = [p for p in plugins if p.category == category]
        return sorted(plugins, key=lambda p: p.name)

    def get_plugin(self, name: str) -> PluginMeta | None:
        """Look up a single plugin by name.

        Args:
            name: Plugin name as declared in the registry.

        Returns:
            ``PluginMeta`` if found, else ``None``.
        """
        return self._plugins.get(name)

    def search(self, query: str) -> list[PluginMeta]:
        """Full-text search across name, description, and tags.

        Args:
            query: Case-insensitive search string.

        Returns:
            Matching plugins sorted by name.
        """
        q = query.lower()
        results: list[PluginMeta] = []
        for p in self._plugins.values():
            haystack = f"{p.name} {p.description} {' '.join(p.tags)}".lower()
            if q in haystack:
                results.append(p)
        return sorted(results, key=lambda p: p.name)

    def categories(self) -> list[str]:
        """Return sorted list of all plugin categories."""
        return sorted({p.category for p in self._plugins.values()})

    def check_status(self, name: str) -> PluginStatus:
        """Check the installation status of a plugin.

        Probes ``importlib`` to determine whether the plugin's entry point
        module is importable. Does not check version compatibility.

        Args:
            name: Plugin name.

        Returns:
            Current ``PluginStatus``.
        """
        meta = self._plugins.get(name)
        if meta is None:
            return PluginStatus.INCOMPATIBLE

        import importlib

        module_path = meta.entry_point.rsplit(":", 1)[0]
        try:
            importlib.import_module(module_path)
        except (ImportError, ModuleNotFoundError):
            return PluginStatus.AVAILABLE

        # Module is importable — check if its graphs are registered
        try:
            from decepticon.graph_registry import _BUNDLE_TO_GRAPHS

            for graphs in _BUNDLE_TO_GRAPHS.values():
                for _graph_name, spec in graphs.items():
                    mod = spec.rsplit(":", 1)[0].rsplit(".", 1)[-1]
                    if mod in module_path:
                        return PluginStatus.ACTIVE
        except ImportError:
            pass

        return PluginStatus.INSTALLED
