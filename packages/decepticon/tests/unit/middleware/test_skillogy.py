"""Tests for decepticon.middleware.skillogy.

Covers env-flag parsing, base-URL / API-key resolution, the policy-prompt
injection into the system message, the @tool wrappers' error envelopes,
and the ``maybe_install_skillogy`` swap rule.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import SystemMessage

from decepticon.middleware import skillogy as sk
from decepticon.middleware.skillogy import (
    SkillogyMiddleware,
    _is_enabled,
    _make_list_skills_tool,
    _make_load_skill_tool,
    _resolve_api_key,
    _resolve_base_url,
    maybe_install_skillogy,
)
from decepticon.skillogy.proto import SkillEnvelope, SkillListResponse, SkillMeta

# ── _is_enabled ────────────────────────────────────────────────────────


class TestIsEnabled:
    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " On "])
    def test_truthy_values_enable(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("DECEPTICON_USE_SKILLOGY", val)
        assert _is_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
    def test_falsy_values_disable(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("DECEPTICON_USE_SKILLOGY", val)
        assert _is_enabled() is False

    def test_unset_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_USE_SKILLOGY", raising=False)
        assert _is_enabled() is False


# ── URL + API key resolution ───────────────────────────────────────────


class TestResolvers:
    def test_default_base_url_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_SKILLOGY_URL", raising=False)
        assert _resolve_base_url() == "http://skillogy:9100"

    def test_base_url_override_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_SKILLOGY_URL", "https://example/api")
        assert _resolve_base_url() == "https://example/api"

    def test_api_key_unset_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_SKILLOGY_API_KEY", raising=False)
        assert _resolve_api_key() is None

    def test_api_key_empty_string_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # `or None` coalesces empty-string to None.
        monkeypatch.setenv("DECEPTICON_SKILLOGY_API_KEY", "")
        assert _resolve_api_key() is None

    def test_api_key_value_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_SKILLOGY_API_KEY", "sk-test-123")
        assert _resolve_api_key() == "sk-test-123"


# ── tool wrappers (list_skills, load_skill) ────────────────────────────


class _StubClient:
    """Minimal client surface used by the @tool wrappers."""

    def __init__(
        self,
        list_resp: Any = None,
        load_resp: Any = None,
        list_exc: Exception | None = None,
        load_exc: Exception | None = None,
    ) -> None:
        self._list_resp = list_resp
        self._load_resp = load_resp
        self._list_exc = list_exc
        self._load_exc = load_exc
        self.list_calls: list[dict[str, Any]] = []
        self.load_calls: list[str] = []

    async def list_skills(
        self,
        *,
        subdomain_filter: list[str] | None = None,
        tag_filter: list[str] | None = None,
        mitre_filter: list[str] | None = None,
    ) -> Any:
        self.list_calls.append(
            {
                "subdomain_filter": subdomain_filter,
                "tag_filter": tag_filter,
                "mitre_filter": mitre_filter,
            }
        )
        if self._list_exc is not None:
            raise self._list_exc
        return self._list_resp

    async def load_skill(self, path: str) -> Any:
        self.load_calls.append(path)
        if self._load_exc is not None:
            raise self._load_exc
        return self._load_resp


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestListSkillsTool:
    def test_returns_json_with_total_count_and_skills(self) -> None:
        meta = SkillMeta(name="recon-banner", subdomain="recon", path="/skills/r/SKILL.md")
        resp = SkillListResponse(skills=[meta], total_count=1)
        client = _StubClient(list_resp=resp)
        tool = _make_list_skills_tool(client)

        out = _run(tool.ainvoke({"subdomain_filter": ["recon"]}))
        data = json.loads(out)
        assert data["total_count"] == 1
        assert data["skills"][0]["name"] == "recon-banner"
        assert data["skills"][0]["path"] == "/skills/r/SKILL.md"
        # client received the filter unchanged.
        assert client.list_calls == [
            {"subdomain_filter": ["recon"], "tag_filter": None, "mitre_filter": None}
        ]

    def test_exception_returned_as_error_envelope(self) -> None:
        client = _StubClient(list_exc=RuntimeError("boom"))
        tool = _make_list_skills_tool(client)

        out = _run(tool.ainvoke({}))
        data = json.loads(out)
        assert "error" in data
        assert "Skillogy list_skills failed" in data["error"]
        assert "boom" in data["error"]


class TestLoadSkillTool:
    def test_returns_meta_body_refs_scripts(self) -> None:
        env = SkillEnvelope(
            meta=SkillMeta(name="x", path="/skills/x/SKILL.md"),
            body="# body",
            references={"ref.md": b"ref-bytes"},
            scripts={"run.sh": b"#!/bin/sh\n"},
        )
        client = _StubClient(load_resp=env)
        tool = _make_load_skill_tool(client)

        out = _run(tool.ainvoke({"path": "/skills/x/SKILL.md"}))
        data = json.loads(out)
        assert data["meta"]["name"] == "x"
        assert data["body"] == "# body"
        assert data["references"] == {"ref.md": "ref-bytes"}
        assert data["scripts"] == {"run.sh": "#!/bin/sh\n"}
        assert client.load_calls == ["/skills/x/SKILL.md"]

    def test_exception_returned_as_error_envelope(self) -> None:
        client = _StubClient(load_exc=ValueError("nope"))
        tool = _make_load_skill_tool(client)
        out = _run(tool.ainvoke({"path": "/skills/missing"}))
        data = json.loads(out)
        assert "error" in data
        assert "Skillogy load_skill failed" in data["error"]
        assert "nope" in data["error"]


# ── SkillogyMiddleware construction + _inject ──────────────────────────


@dataclass
class _FakeRequest:
    system_message: SystemMessage | None
    overrides: dict[str, Any] = field(default_factory=dict)

    def override(self, *, system_message: SystemMessage) -> _FakeRequest:
        return _FakeRequest(system_message=system_message, overrides={"taken": True})


class TestMiddlewareConstruction:
    def test_constructor_registers_two_tools(self) -> None:
        mw = SkillogyMiddleware(client=_StubClient())
        names = [t.name for t in mw.tools]
        assert names == ["list_skills", "load_skill"]

    def test_from_env_builds_with_default_client_factory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel_client = _StubClient()
        monkeypatch.setattr(sk, "_client_factory", lambda: sentinel_client)
        mw = SkillogyMiddleware.from_env()
        assert mw._client is sentinel_client


class TestInjectPolicy:
    def test_no_existing_system_message_creates_one_with_policy(self) -> None:
        mw = SkillogyMiddleware(client=_StubClient())
        out = mw._inject(_FakeRequest(system_message=None))
        assert isinstance(out.system_message, SystemMessage)
        blocks = out.system_message.content
        assert isinstance(blocks, list)
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "[Skillogy access]" in blocks[0]["text"]

    def test_existing_system_message_blocks_preserved_and_policy_appended(self) -> None:
        mw = SkillogyMiddleware(client=_StubClient())
        original = SystemMessage(content="BASE_PROMPT")
        out = mw._inject(_FakeRequest(system_message=original))
        blocks = out.system_message.content
        assert isinstance(blocks, list)
        # The original content_blocks come first, then the policy text.
        assert blocks[-1]["text"].lstrip().startswith("[Skillogy access]")
        # original "BASE_PROMPT" text survives somewhere in earlier blocks.
        flat = json.dumps(blocks)
        assert "BASE_PROMPT" in flat

    def test_append_policy_false_returns_request_untouched(self) -> None:
        mw = SkillogyMiddleware(client=_StubClient(), append_policy_to_system=False)
        original = SystemMessage(content="BASE_PROMPT")
        req = _FakeRequest(system_message=original)
        out = mw._inject(req)
        assert out is req  # short-circuit: no override applied.


# ── maybe_install_skillogy swap ────────────────────────────────────────


class TestMaybeInstallSkillogy:
    def test_env_disabled_returns_stack_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DECEPTICON_USE_SKILLOGY", raising=False)
        from decepticon.middleware.skills import SkillsMiddleware

        fake_skills = MagicMock(spec=SkillsMiddleware)
        other = object()
        stack = [fake_skills, other]
        out = maybe_install_skillogy(stack)
        assert out is stack  # identity short-circuit

    def test_env_enabled_swaps_skills_for_skillogy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_USE_SKILLOGY", "1")
        # Avoid real client construction inside SkillogyMiddleware.from_env.
        monkeypatch.setattr(sk, "_client_factory", lambda: _StubClient())

        from decepticon.middleware.skills import SkillsMiddleware

        fake_skills = MagicMock(spec=SkillsMiddleware)
        other = object()
        stack = [other, fake_skills]

        out = maybe_install_skillogy(stack)
        assert len(out) == 2
        assert out[0] is other  # non-skills entries preserved
        assert isinstance(out[1], SkillogyMiddleware)

    def test_env_enabled_no_skills_does_not_append(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DECEPTICON_USE_SKILLOGY", "1")
        monkeypatch.setattr(sk, "_client_factory", lambda: _StubClient())

        other = object()
        stack = [other]
        out = maybe_install_skillogy(stack)
        # Swap-only: no SkillsMiddleware means no skillogy layer is added.
        assert out == [other]
        assert not any(isinstance(m, SkillogyMiddleware) for m in out)
