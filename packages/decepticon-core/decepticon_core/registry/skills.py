"""Skill source registry — path validation + collision detection.

Closes gap §8 #12 from the consumption audit: plugin-registered
``/skills/<bundle>/`` paths used to be silently accepted even when
malformed (``/workspace/foo``) or duplicated. ``SkillSourceRegistry``
validates format at registration time and emits a
``PluginConflictWarning`` when two owners register the same path.
"""

from __future__ import annotations

import warnings

from decepticon_core.registry.conflict import PluginConflictWarning


class SkillSourceRegistry:
    """Process-wide skill-source path registry.

    Validates each registered path matches the OSS convention
    (``/skills/<bundle>/`` — starts with ``/skills/``, ends with ``/``)
    and surfaces collisions as ``PluginConflictWarning`` so operators
    see them in test logs.
    """

    _entries: dict[str, str] = {}  # path -> owner

    @classmethod
    def register(cls, source: str, owner: str) -> None:
        """Register a skill source path under ``owner``.

        Raises ``ValueError`` if ``source`` violates the
        ``/skills/<bundle>/`` shape. Emits ``PluginConflictWarning``
        (non-fatal, last-write-wins) if ``source`` was already
        registered under a different owner.
        """
        if not source.startswith("/skills/"):
            raise ValueError(
                f"skill source must start with '/skills/'; got {source!r} from {owner!r}"
            )
        if not source.endswith("/"):
            raise ValueError(f"skill source must end with '/'; got {source!r} from {owner!r}")

        previous_owner = cls._entries.get(source)
        if previous_owner is not None and previous_owner != owner:
            warnings.warn(
                PluginConflictWarning(
                    f"skill source {source!r} already registered by {previous_owner!r}; "
                    f"{owner!r} is overwriting (last-write-wins)",
                    key=source,
                    owner=owner,
                    previous_owner=previous_owner,
                    kind="skill_source",
                ),
                stacklevel=2,
            )
        cls._entries[source] = owner

    @classmethod
    def owners(cls) -> tuple[tuple[str, str], ...]:
        """Return all (path, owner) pairs in path-sorted order."""
        return tuple((p, cls._entries[p]) for p in sorted(cls._entries))

    @classmethod
    def unregister(cls, source: str) -> None:
        """Drop ``source`` from the registry. No-op if not present."""
        cls._entries.pop(source, None)
