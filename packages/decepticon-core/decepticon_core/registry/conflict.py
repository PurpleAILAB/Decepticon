"""Plugin conflict warning.

Issued when ``PluginRegistry.detect_collisions()`` sees two plugins
registering the same key. Per spec §16.4 #6 the warning carries an
``owner`` attribute identifying the contributor so audit log
attribution works.
"""

from __future__ import annotations


class PluginConflictWarning(UserWarning):
    """Two plugins registered the same key (tool / slot / role / skill path).

    The warning is non-fatal by default — last-write-wins resolution
    keeps the registry usable. Strict mode (``DECEPTICON_STRICT_REGISTRY=1``)
    converts these warnings to exceptions in Phase 2 framework boot.

    Attributes:
        key: the conflicting key (e.g. tool name, slot name, role name).
        owner: the plugin package name that issued the conflicting
            registration (the loser under last-write-wins). Required
            for audit log attribution per spec §16.4 #6.
        previous_owner: the plugin already registered for ``key``.
        kind: discriminator — ``"tool"`` / ``"middleware"`` / ``"role"``
            / ``"skill_source"``.
    """

    def __init__(
        self,
        message: str,
        *,
        key: str,
        owner: str,
        previous_owner: str,
        kind: str,
    ) -> None:
        super().__init__(message)
        self.key = key
        self.owner = owner
        self.previous_owner = previous_owner
        self.kind = kind
