"""Role registry — pluggable agent-role catalog.

OSS roles are pre-registered at framework boot from
``decepticon_core.contracts.slots.SLOTS_PER_ROLE``. Plugins register
custom roles via the new ``decepticon.roles`` entry-point group;
this closes gap §8 #5 (SaaS ``apt`` previously had to abuse
``default_role="decepticon"`` in ``LLMFactory``).

Per spec §16.4 #3 ``register()`` is idempotent on identical parameters:
multi-process workers each register on startup without conflict.
"""

from __future__ import annotations

from dataclasses import dataclass

from decepticon_core.contracts.slots import MiddlewareSlot


@dataclass(frozen=True)
class RoleSpec:
    """Frozen description of one registered role.

    Stored in ``RoleRegistry``; used by the framework's middleware
    assembler and LLM factory at boot.
    """

    name: str
    slots: frozenset[MiddlewareSlot]
    skill_sources: tuple[str, ...] = ()
    llm_role_fallback: str | None = None


class RoleRegistry:
    """Process-wide singleton role catalog.

    Stays inside the contract layer so plugin authors can register
    roles without importing the framework. The framework's
    ``LLMFactory`` and middleware assembler consume this registry at
    boot (wired in Phase 2).
    """

    _entries: dict[str, RoleSpec] = {}

    @classmethod
    def register(
        cls,
        name: str,
        *,
        slots: frozenset[MiddlewareSlot],
        skill_sources: tuple[str, ...] = (),
        llm_role_fallback: str | None = None,
    ) -> None:
        """Register a role (idempotent on identical parameters).

        Re-registering with different parameters raises ``ValueError`` —
        callers should explicitly call ``unregister()`` first if they
        intend to replace.

        Idempotency check (spec §16.4 #3): if ``name`` already exists
        and the proposed ``RoleSpec`` is equal to the stored one, the
        call returns silently. Multi-process workers all calling
        ``register()`` on startup is therefore safe.
        """
        proposed = RoleSpec(
            name=name,
            slots=slots,
            skill_sources=skill_sources,
            llm_role_fallback=llm_role_fallback,
        )
        existing = cls._entries.get(name)
        if existing is not None:
            if existing == proposed:
                return
            raise ValueError(
                f"role {name!r} already registered with different parameters; "
                f"call RoleRegistry.unregister({name!r}) first if intentional"
            )
        cls._entries[name] = proposed

    @classmethod
    def get(cls, name: str) -> RoleSpec | None:
        """Return the ``RoleSpec`` for ``name``, or ``None`` if unknown."""
        return cls._entries.get(name)

    @classmethod
    def list(cls) -> tuple[RoleSpec, ...]:
        """Return all registered specs in name-sorted order."""
        return tuple(cls._entries[name] for name in sorted(cls._entries))

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove ``name`` from the registry. No-op if not registered."""
        cls._entries.pop(name, None)
