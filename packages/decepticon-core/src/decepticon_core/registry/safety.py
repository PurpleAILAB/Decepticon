"""Safety registry — plugin-extended safety-critical tool / middleware names.

Closes spec §16.4 #4. The framework's ``_check_safety_gate`` consults
this registry's merged accessors so plugin-declared safety-critical
names participate in the env-gated override check alongside the
OSS-hardcoded ``SAFETY_CRITICAL_TOOLS`` / ``SAFETY_CRITICAL_SLOTS``.

Contract: **additive only**. Plugins extend the safety-critical set;
they cannot remove safety on OSS-declared names. The registry stores
only plugin contributions — the framework merges them with the OSS
baseline at check time, so any attempt to "unregister" an OSS name
has no effect on the merged result.

Plugin authors register via the ``SafetyDeclaration`` contract:

    from decepticon_sdk import SafetyDeclaration, SafetyRegistry

    PLUGIN_SAFETY = SafetyDeclaration(
        tools=("my_dangerous_tool",),
        middleware=("my-policy-enforcement",),
    )
    SafetyRegistry.register(PLUGIN_SAFETY, owner="my-plugin")
"""

from __future__ import annotations

from decepticon_core.contracts.contributions import SafetyDeclaration


class SafetyRegistry:
    """Process-wide registry of plugin-declared safety-critical names.

    Class-level state (mirrors ``RoleRegistry`` / ``SkillSourceRegistry``
    pattern). Read by the framework's ``_check_safety_gate`` at agent-
    construction time; never mutated by introspection consumers.
    """

    _tools: dict[str, str] = {}  # tool name -> owner package
    _middleware: dict[str, str] = {}  # slot/middleware name -> owner package

    @classmethod
    def register(cls, declaration: SafetyDeclaration, *, owner: str) -> None:
        """Record a plugin's safety-critical declarations.

        Idempotent on identical (name, owner) pairs. If the same name is
        registered by two different owners, the second registration wins
        silently (last-write-wins on attribution); this is not a
        collision in the safety sense because both owners agree the
        name is safety-critical — only the attribution differs.

        Additive-only: there is intentionally no ``unregister`` for
        OSS-declared names. Plugins cannot weaken the safety story.
        """
        for tool in declaration.tools:
            cls._tools[tool] = owner
        for middleware in declaration.middleware:
            cls._middleware[middleware] = owner

    @classmethod
    def merged_critical_tools(cls, oss_baseline: frozenset[str]) -> frozenset[str]:
        """Return the union of the OSS baseline + every registered plugin tool name."""
        return frozenset(oss_baseline | cls._tools.keys())

    @classmethod
    def merged_critical_slots(cls, oss_baseline: frozenset[str]) -> frozenset[str]:
        """Return the union of the OSS baseline + every registered plugin slot name."""
        return frozenset(oss_baseline | cls._middleware.keys())

    @classmethod
    def plugin_tools(cls) -> tuple[tuple[str, str], ...]:
        """Return all (tool_name, owner) pairs in tool-name-sorted order."""
        return tuple((t, cls._tools[t]) for t in sorted(cls._tools))

    @classmethod
    def plugin_middleware(cls) -> tuple[tuple[str, str], ...]:
        """Return all (slot_name, owner) pairs in slot-name-sorted order."""
        return tuple((m, cls._middleware[m]) for m in sorted(cls._middleware))

    @classmethod
    def reset(cls) -> None:
        """Discard plugin registrations (test-only convenience).

        Has no effect on the OSS baseline since baseline lives in the
        framework, not here.
        """
        cls._tools = {}
        cls._middleware = {}
