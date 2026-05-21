"""Tests for SkillsMiddleware defensive paths (issue #157 regressions).

The base ``SkillsMiddleware`` is exercised through deepagents' own tests,
but the decepticon subclass adds workflow-loading, a custom prompt
template, and isinstance gates on backend results that aren't covered
by the base test surface. This file pins those defensive paths so the
fixes that landed for the audit findings cannot silently regress.

Findings covered:
  - MED #7: ``data.get("content", "")`` is gated by ``isinstance(data, dict)``
    in both ``_read_workflow_for_source`` and ``_aread_workflow_for_source``.
    Pre-fix, a backend returning a truthy non-dict (e.g. a raw string in
    error paths) crashed the middleware on ``.get``.
  - MED #8: ``self.system_prompt_template.format(...)`` is wrapped in
    ``except (KeyError, IndexError)``. Pre-fix, a template edit that
    introduced a placeholder mismatch would crash every model step from
    that point on; the fix logs and falls through to the original system
    message instead.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import SystemMessage

from decepticon.middleware.skills import SkillsMiddleware

# ── Backend stand-ins ───────────────────────────────────────────────────


class _BackendResult:
    """Minimal duck-typed stand-in for backend read results.

    Real backend results expose ``.error`` (str | None) and ``.file_data``
    (dict | None). We construct edge-case shapes (non-dict file_data) on
    purpose to exercise the isinstance gate.
    """

    def __init__(self, *, error: str | None = None, file_data: Any = None) -> None:
        self.error = error
        self.file_data = file_data


class _StringFileDataBackend:
    """Backend whose ``read``/``aread`` return a result whose
    ``file_data`` is a raw string instead of a dict.

    Pre-fix this triggered ``AttributeError: 'str' object has no attribute 'get'``
    inside ``_read_workflow_for_source``; the fix gates on
    ``isinstance(data, dict)`` and returns None.
    """

    def __init__(self, file_data: Any) -> None:
        self._file_data = file_data

    def read(self, _path: str) -> _BackendResult:
        return _BackendResult(error=None, file_data=self._file_data)

    async def aread(self, _path: str) -> _BackendResult:
        return _BackendResult(error=None, file_data=self._file_data)


class _DictFileDataBackend:
    """Backend that returns a properly-shaped dict for the happy path."""

    def __init__(self, content: str) -> None:
        self._content = content

    def read(self, _path: str) -> _BackendResult:
        return _BackendResult(file_data={"content": self._content})

    async def aread(self, _path: str) -> _BackendResult:
        return _BackendResult(file_data={"content": self._content})


class _RaisingBackend:
    """Backend whose ``read`` raises — exercises the outer try/except in
    ``_read_workflow_for_source``."""

    def read(self, _path: str) -> _BackendResult:
        raise RuntimeError("backend not connected")

    async def aread(self, _path: str) -> _BackendResult:
        raise RuntimeError("backend not connected")


# ── Request stand-in ────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal duck-typed request — same pattern as test_engagement.py."""

    def __init__(
        self,
        state: dict[str, Any] | None = None,
        system_message: SystemMessage | None = None,
    ) -> None:
        self.state = state or {}
        self.system_message = system_message

    def override(self, system_message: SystemMessage) -> "_FakeRequest":
        new = _FakeRequest(state=self.state, system_message=system_message)
        return new


def _make_middleware(backend: Any) -> SkillsMiddleware:
    """Build a SkillsMiddleware against a stub backend with one source."""
    return SkillsMiddleware(backend=backend, sources=["/skills/standard/recon/"])


# ── MED #7 — isinstance gate on backend result ─────────────────────────


class TestWorkflowLoaderRejectsNonDictFileData:
    """``_read_workflow_for_source`` and its async sibling must return
    None when the backend hands back a non-dict ``file_data``. The
    isinstance gate at line 169/186 of skills.py is the explicit
    contract — pre-fix this crashed on ``.get``.
    """

    def test_string_file_data_returns_none(self) -> None:
        backend = _StringFileDataBackend(file_data="raw text not a dict")
        mw = _make_middleware(backend)

        result = mw._read_workflow_for_source(backend, "/skills/standard/recon/")

        assert result is None, (
            "non-dict file_data must short-circuit to None — see issue #157 MED #7"
        )

    def test_list_file_data_returns_none(self) -> None:
        backend = _StringFileDataBackend(file_data=["line1", "line2"])
        mw = _make_middleware(backend)

        assert mw._read_workflow_for_source(backend, "/skills/standard/recon/") is None

    def test_none_file_data_returns_none(self) -> None:
        backend = _StringFileDataBackend(file_data=None)
        mw = _make_middleware(backend)

        assert mw._read_workflow_for_source(backend, "/skills/standard/recon/") is None

    def test_dict_with_content_returns_string(self) -> None:
        """Happy-path positive control: a properly-shaped dict still works."""
        backend = _DictFileDataBackend(content="# Recon Workflow\nDo this then that.")
        mw = _make_middleware(backend)

        result = mw._read_workflow_for_source(backend, "/skills/standard/recon/")
        assert result == "# Recon Workflow\nDo this then that."

    def test_backend_read_exception_returns_none(self) -> None:
        """Outer try/except catches arbitrary backend errors."""
        backend = _RaisingBackend()
        mw = _make_middleware(backend)

        assert mw._read_workflow_for_source(backend, "/skills/standard/recon/") is None

    # ── async siblings ──────────────────────────────────────────────────

    def test_async_string_file_data_returns_none(self) -> None:
        backend = _StringFileDataBackend(file_data="raw text not a dict")
        mw = _make_middleware(backend)

        result = asyncio.run(mw._aread_workflow_for_source(backend, "/skills/standard/recon/"))
        assert result is None

    def test_async_dict_with_content_returns_string(self) -> None:
        backend = _DictFileDataBackend(content="# Recon Workflow")
        mw = _make_middleware(backend)

        result = asyncio.run(mw._aread_workflow_for_source(backend, "/skills/standard/recon/"))
        assert result == "# Recon Workflow"

    def test_async_backend_read_exception_returns_none(self) -> None:
        backend = _RaisingBackend()
        mw = _make_middleware(backend)

        result = asyncio.run(mw._aread_workflow_for_source(backend, "/skills/standard/recon/"))
        assert result is None

    def test_empty_string_content_returns_none(self) -> None:
        """Empty content collapses to None — keeps the prompt clean.

        Implementation detail of the helper, but pinning it here so a
        future refactor that emits an empty string banner does not
        accidentally inject visible whitespace into the system prompt.
        """
        backend = _DictFileDataBackend(content="   ")
        mw = _make_middleware(backend)

        assert mw._read_workflow_for_source(backend, "/skills/standard/recon/") is None


# ── MED #8 — template format failures are swallowed ────────────────────


class TestModifyRequestTemplateFormatFailures:
    """``modify_request`` wraps ``self.system_prompt_template.format(...)``
    in ``except (KeyError, IndexError)``. A user/subclass that overrides
    the template with a bad placeholder must not crash every model step.
    """

    def test_keyerror_falls_through_to_original_request(self) -> None:
        """Template referencing an unknown placeholder must not raise.

        The contract: log a warning, return the original request
        untouched, so the agent step continues with the baked-in system
        message rather than failing the whole inference.
        """
        backend = _DictFileDataBackend(content="x")
        mw = _make_middleware(backend)
        # Inject a bad template — references a placeholder we never pass.
        mw.system_prompt_template = "broken {nonexistent_placeholder}"

        original_msg = SystemMessage(content="original system msg")
        request = _FakeRequest(
            state={"skills_metadata": [], "workflow_content": ""},
            system_message=original_msg,
        )

        out = mw.modify_request(request)

        # On format failure, the contract is to return the request as-is.
        # ``out is request`` is the literal "untouched" guarantee.
        assert out is request, (
            "format failure must return request unchanged — see issue #157 MED #8"
        )

    def test_indexerror_also_caught(self) -> None:
        """Positional placeholder ``{0}`` is also a format-bomb path —
        Python raises IndexError here, not KeyError, so the except clause
        must cover both.
        """
        backend = _DictFileDataBackend(content="x")
        mw = _make_middleware(backend)
        mw.system_prompt_template = "broken {0}"

        original_msg = SystemMessage(content="original")
        request = _FakeRequest(
            state={"skills_metadata": [], "workflow_content": ""},
            system_message=original_msg,
        )

        out = mw.modify_request(request)
        assert out is request

    def test_valid_template_still_overrides_system_message(self) -> None:
        """Positive control: a working template still does its job —
        otherwise the swallow-on-error contract would mask all failures.
        """
        backend = _DictFileDataBackend(content="x")
        mw = _make_middleware(backend)
        # Use a minimal template that only references the standard placeholders.
        mw.system_prompt_template = (
            "skills_locations={skills_locations}|workflow={workflow}|skills_list={skills_list}"
        )

        request = _FakeRequest(
            state={
                "skills_metadata": [],
                "workflow_content": "WORKFLOW_BODY",
            },
            system_message=SystemMessage(content="original"),
        )

        out = mw.modify_request(request)

        # The override path was taken: out is a *new* request with a
        # different system_message that includes our marker.
        assert out is not request
        # Narrow the type for the type checker — the override path always
        # populates system_message; the Optional shape is only there for
        # callers that pass system_message=None on input.
        assert out.system_message is not None
        # The new system message contains our marker, proving format() ran.
        content = out.system_message.content
        flattened = (
            content
            if isinstance(content, str)
            else "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        )
        assert "WORKFLOW_BODY" in flattened
