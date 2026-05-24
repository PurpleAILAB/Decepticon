"""decepticon-sdk surface tests.

Verifies the single-import contract from spec §6.3: a complete plugin
can be written importing only from ``decepticon_sdk``. Tests that
the 23 stable symbols are exposed and that the testing fakes satisfy
their respective Protocols.
"""

from __future__ import annotations


def test_protocols_importable() -> None:
    """All 7 protocols are reachable via the single SDK import."""
    from decepticon_sdk import (
        AgentProtocol,
        BackendProtocol,
        CallbackProtocol,
        LLMProtocol,
        MiddlewareProtocol,
        SandboxProtocol,
        ToolProtocol,
    )

    # Every protocol is a runtime-checkable abstract — instantiation
    # itself is meaningless, but the class must be importable.
    for proto in (
        AgentProtocol,
        BackendProtocol,
        CallbackProtocol,
        LLMProtocol,
        MiddlewareProtocol,
        SandboxProtocol,
        ToolProtocol,
    ):
        assert proto is not None
        assert proto.__name__.endswith("Protocol")


def test_contributions_importable() -> None:
    """All 5 contribution dataclasses reachable via single SDK import.

    The four role-scoped contributions (Tool / Middleware / Prompt /
    SubAgent) now enforce explicit ``roles=`` / ``parent_agents=`` at
    construction time (spec §8 gap #6 — implicit all-roles forbidden).
    SafetyDeclaration has no role-scope field and constructs freely.
    """
    import pytest

    from decepticon_sdk import (
        MiddlewareContribution,
        PromptContribution,
        SafetyDeclaration,
        SubAgentContribution,
        ToolContribution,
    )

    # Constructing role-scoped contributions WITHOUT roles= raises (gap #6).
    for cls in (ToolContribution, MiddlewareContribution, PromptContribution):
        with pytest.raises(ValueError, match=r"roles="):
            cls()
    with pytest.raises(ValueError, match=r"parent_agents="):
        SubAgentContribution()

    # SafetyDeclaration has no role scope; default construction OK.
    assert SafetyDeclaration().tools == ()

    # Explicit roles= constructs successfully + defaults apply.
    assert PromptContribution(roles=("recon",)).mode == "append"
    assert ToolContribution(roles=("recon",)).items == ()
    assert MiddlewareContribution(roles=("recon",)).items == ()
    assert SubAgentContribution(parent_agents=("decepticon",)).items == ()


def test_fake_backend_satisfies_protocol() -> None:
    from decepticon_sdk import BackendProtocol
    from decepticon_sdk.testing import FakeBackend

    fb = FakeBackend({"/skills/test/hello.md": "hi"})
    assert isinstance(fb, BackendProtocol)
    assert fb.read("/skills/test/hello.md") == "hi"
    assert fb.exists("/skills/test/hello.md")
    assert not fb.exists("/skills/test/missing.md")


def test_fake_llm_satisfies_protocol() -> None:
    from decepticon_sdk import LLMProtocol
    from decepticon_sdk.testing import FakeLLM

    flm = FakeLLM(responses=["first", "second"])
    assert isinstance(flm, LLMProtocol)
    assert flm.invoke("anything") == "first"
    assert flm.invoke("anything") == "second"


def test_fake_sandbox_satisfies_protocol() -> None:
    from decepticon_sdk import SandboxProtocol
    from decepticon_sdk.testing import FakeSandbox

    fsb = FakeSandbox(responses=["root\n"])
    assert isinstance(fsb, SandboxProtocol)
    output = fsb.execute_command("whoami")
    assert output == "root\n"
    assert fsb.commands == ["whoami"]


def test_role_registry_idempotent() -> None:
    """Spec §16.4 #3 — re-registration with identical parameters is a no-op."""
    from decepticon_sdk import MiddlewareSlot, RoleRegistry

    RoleRegistry.register("test_idem", slots=frozenset({MiddlewareSlot.SKILLS}))
    RoleRegistry.register("test_idem", slots=frozenset({MiddlewareSlot.SKILLS}))
    spec = RoleRegistry.get("test_idem")
    assert spec is not None
    assert spec.name == "test_idem"


def test_skill_source_registry_validates() -> None:
    from decepticon_sdk import SkillSourceRegistry

    SkillSourceRegistry.register("/skills/test_validates/", "test-pkg")
    try:
        SkillSourceRegistry.register("/workspace/bad", "test-pkg")
    except ValueError:
        return
    raise AssertionError("expected ValueError for path missing /skills/ prefix")
