"""Plugin registry — central read-only view of discovered plugins.

Closes gaps §8 #4 (collision detection) and §8 #7 (introspection API).
``PluginRegistry.load()`` walks the eight Decepticon entry-point
groups, snapshots every contribution, and exposes the result to
introspection consumers (audit pipelines, plugin-author guides,
the future B2B Enterprise API tier).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from decepticon_core.registry.conflict import PluginConflictWarning
from decepticon_core.registry.resolution import RoleResolution

logger = logging.getLogger(__name__)

# When set to a truthy value (``1`` / ``true`` / ``yes``),
# ``PluginRegistry.load()`` raises ``PluginConflictWarning`` (as an
# exception via ``warnings.warn(..., stacklevel=2)`` + filter) on the
# first collision instead of accumulating warnings. Production
# deployments that don't want last-write-wins resolution flip this on.
_STRICT_REGISTRY_ENV = "DECEPTICON_STRICT_REGISTRY"


def _strict_registry_enabled() -> bool:
    return os.environ.get(_STRICT_REGISTRY_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass(frozen=True)
class PluginInfo:
    """Static description of one discovered plugin.

    Returned by ``PluginRegistry.list_plugins()``. ``groups`` carries
    every entry-point group the plugin is registered under so callers
    can attribute extensions to their owning package (audit trails,
    collision attribution).
    """

    name: str
    package: str
    bundle: str | None
    groups: tuple[str, ...] = field(default_factory=tuple)


# The eight entry-point groups the framework consumes. Keep in lockstep
# with ``decepticon_core.plugin_loader``'s *_GROUP constants — the
# registry walk is the audit-time mirror of the framework's actual
# discovery pipeline.
_PLUGIN_GROUPS: tuple[str, ...] = (
    "decepticon.tools",
    "decepticon.middleware",
    "decepticon.agents",
    "decepticon.subagents",
    "decepticon.callbacks",
    "decepticon.skills",
    "decepticon.bundles",
    "decepticon.roles",
    "decepticon.prompts",
)


class PluginRegistry:
    """Read-only view of all plugins loaded into the current process.

    Built by ``load()`` at framework boot — walks the entry-point
    groups, records every contribution as a ``PluginInfo``, and
    surfaces same-key collisions across owners as
    ``PluginConflictWarning`` instances. Subsequent imports of this
    module re-use the cached singleton.

    Spec §16.4 #2: introspection methods (``list_plugins``,
    ``detect_collisions``, ``introspect_role``) are **read-only** —
    they never mutate registry state. Audit pipelines memoize the
    return values keyed on run ID.
    """

    _instance: PluginRegistry | None = None
    _plugins: tuple[PluginInfo, ...] = ()
    _collisions: tuple[PluginConflictWarning, ...] = ()
    # Populated by the framework's _boot.run() — core itself can't
    # build RoleResolution (no access to SLOTS_PER_ROLE composition
    # or skills_sources_for), so the framework pushes the snapshot
    # in after registering OSS roles.
    _resolutions: dict[str, RoleResolution] = {}

    @classmethod
    def load(cls) -> PluginRegistry:
        """Return the singleton, building it on first call.

        Walks every Decepticon entry-point group via
        ``importlib.metadata.entry_points`` and snapshots the result.
        Same-key contributions from different packages produce
        ``PluginConflictWarning`` entries surfaced via
        ``detect_collisions()``; resolution at the framework layer is
        last-write-wins.
        """
        if cls._instance is None:
            cls._instance = cls._build_singleton()
        return cls._instance

    @classmethod
    def _build_singleton(cls) -> PluginRegistry:
        """Walk entry-point groups once and stash the snapshot."""
        # (name, group) -> owning package name. Used to spot same-key
        # collisions across packages.
        seen: dict[tuple[str, str], str] = {}
        collisions: list[PluginConflictWarning] = []
        # (name, package) -> set of groups the plugin appears in. One
        # PluginInfo per (name, package) — a single plugin may register
        # under multiple groups (tools + middleware + callbacks).
        by_owner: dict[tuple[str, str], set[str]] = {}

        for group in _PLUGIN_GROUPS:
            try:
                eps = list(entry_points(group=group))
            except Exception:  # pragma: no cover — importlib quirks
                logger.exception("PluginRegistry: entry-point lookup failed for group %s", group)
                continue

            for ep in eps:
                package = ep.dist.name if ep.dist is not None and ep.dist.name else "<unknown>"
                key = (ep.name, group)
                previous = seen.get(key)
                if previous is not None and previous != package:
                    conflict = PluginConflictWarning(
                        f"entry-point {ep.name!r} in group {group!r} registered "
                        f"by both {previous!r} and {package!r}",
                        key=ep.name,
                        owner=package,
                        previous_owner=previous,
                        kind=group,
                    )
                    if _strict_registry_enabled():
                        # Strict mode (DECEPTICON_STRICT_REGISTRY=1): a
                        # collision is fatal. Production deployments
                        # that want deterministic plugin resolution
                        # flip this so misconfigured installs fail at
                        # boot instead of last-write-wins resolution.
                        raise conflict
                    collisions.append(conflict)
                seen[key] = package
                by_owner.setdefault((ep.name, package), set()).add(group)

        plugins = tuple(
            PluginInfo(
                name=name,
                package=package,
                bundle=None,
                groups=tuple(sorted(groups)),
            )
            for (name, package), groups in sorted(by_owner.items())
        )

        instance = cls()
        cls._plugins = plugins
        cls._collisions = tuple(collisions)
        return instance

    @classmethod
    def reset(cls) -> None:
        """Discard the cached singleton (test-only convenience).

        Re-loading from scratch is normally undesirable in production
        — the entry-point graph is fixed at install time — but tests
        that monkey-patch entry_points or simulate plugin packages
        need a way to rebuild the snapshot.
        """
        cls._instance = None
        cls._plugins = ()
        cls._collisions = ()
        cls._resolutions = {}

    @classmethod
    def set_role_resolution(cls, role: str, resolution: RoleResolution) -> None:
        """Framework boot hook — stash a ``RoleResolution`` for ``role``.

        Called by ``decepticon._boot.run()`` after registering OSS
        roles. ``decepticon-core`` itself can't compose the resolution
        (no access to ``DEFAULT_SLOT_FACTORIES`` or
        ``skills_sources_for``); the framework pushes the snapshot in
        through this hook so introspection consumers read it back
        without any framework-side imports.

        Idempotent. Calling with the same ``role`` overwrites the
        previous resolution.
        """
        cls._resolutions[role] = resolution

    def list_plugins(self) -> tuple[PluginInfo, ...]:
        """Return every discovered plugin in (name, package)-sorted order."""
        return self._plugins

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Return the ``PluginInfo`` for ``name``, or ``None`` if absent.

        If two packages register the same ``name``, the first match in
        sorted order wins. Callers needing disambiguation should
        iterate ``list_plugins()`` and filter by ``package``.
        """
        for info in self._plugins:
            if info.name == name:
                return info
        return None

    def detect_collisions(self) -> tuple[PluginConflictWarning, ...]:
        """Return every collision surfaced during ``load()``.

        Strict mode (``DECEPTICON_STRICT_REGISTRY=1``) is left to the
        framework boot path to enforce — the registry surface itself
        stays non-fatal so introspection consumers don't blow up on a
        misconfigured plugin set.
        """
        return self._collisions

    def introspect_role(self, role: str) -> RoleResolution | None:
        """Return the resolved ``RoleResolution`` for ``role``.

        Returns the snapshot pushed in by
        ``decepticon._boot.run()`` (or by any caller using
        ``PluginRegistry.set_role_resolution``). ``None`` when the
        role was never registered — audit pipelines should treat
        that as "role not active in this process."

        Spec §16.4 #2: read-only. No registry mutation here, ever.
        The returned ``RoleResolution`` is a frozen dataclass with
        tuple-typed collections so audit systems can memoize it on
        ``(run_id, role)``.
        """
        return self._resolutions.get(role)
