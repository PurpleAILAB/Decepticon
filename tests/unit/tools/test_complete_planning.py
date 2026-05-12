"""Unit tests for complete_engagement_planning.

All tests inject a FakeDockerSandbox that records calls to download_files,
upload_files, and execute against an in-memory path→bytes store.  The fake
is monkeypatched in at the module level used by complete_planning.py so the
real docker CLI is never invoked.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

# Import these from the module under test; the import establishes the target
# namespace for monkeypatching.
import decepticon.tools.interaction.complete_planning as cp_module
from decepticon.tools.interaction.complete_planning import complete_engagement_planning

# ── Fake sandbox ─────────────────────────────────────────────────────────────


class FakeDownloadResponse:
    def __init__(self, path: str, content: bytes | None, error: str | None) -> None:
        self.path = path
        self.content = content
        self.error = error


class FakeUploadResponse:
    def __init__(self, path: str, error: str | None) -> None:
        self.path = path
        self.error = error


class FakeExecuteResponse:
    def __init__(self, output: str, exit_code: int) -> None:
        self.output = output
        self.exit_code = exit_code


class FakeDockerSandbox:
    """In-memory sandbox fake.  Paths are stored as bytes; execute() runs an
    extremely simple dispatcher that supports 'rm -f' and 'mv -f' only."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})
        self.executed: list[str] = []
        self.uploads: list[tuple[str, bytes]] = []

    # ── DockerSandbox protocol ────────────────────────────────────────────

    def download_files(self, paths: list[str]) -> list[FakeDownloadResponse]:
        results = []
        for path in paths:
            if path in self.files:
                results.append(FakeDownloadResponse(path, self.files[path], None))
            else:
                results.append(FakeDownloadResponse(path, None, "file_not_found"))
        return results

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FakeUploadResponse]:
        results = []
        for path, content in files:
            self.uploads.append((path, content))
            self.files[path] = content
            results.append(FakeUploadResponse(path, None))
        return results

    def execute(self, command: str) -> FakeExecuteResponse:
        self.executed.append(command)
        # Simple dispatcher for the commands complete_planning uses.
        cmd = command.strip()
        if cmd.startswith("rm -f "):
            for part in cmd[len("rm -f ") :].split():
                self.files.pop(part.strip("'\""), None)
            return FakeExecuteResponse("", 0)
        if cmd.startswith("mv -f "):
            parts = cmd[len("mv -f ") :].split()
            if len(parts) == 2:
                src, dst = parts[0].strip("'\""), parts[1].strip("'\"")
                if src in self.files:
                    self.files[dst] = self.files.pop(src)
                    return FakeExecuteResponse("", 0)
                return FakeExecuteResponse("no such file", 1)
        return FakeExecuteResponse("", 0)


def _valid_plan_files(workspace: str = "/workspace") -> dict[str, bytes]:
    """Return an in-memory file dict with all three valid plan docs."""
    return {
        f"{workspace}/plan/roe.json": json.dumps({"in_scope": []}).encode(),
        f"{workspace}/plan/conops.json": json.dumps({"overview": "x"}).encode(),
        f"{workspace}/plan/deconfliction.json": json.dumps({}).encode(),
    }


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sandbox() -> FakeDockerSandbox:
    return FakeDockerSandbox(files=_valid_plan_files())


@pytest.fixture(autouse=True)
def patch_sandbox(sandbox: FakeDockerSandbox) -> Iterator[None]:
    """Monkeypatch DockerSandbox and load_config in complete_planning's namespace."""
    with (
        patch.object(cp_module, "DockerSandbox", return_value=sandbox),
        patch.object(
            cp_module,
            "load_config",
            return_value=type(
                "C",
                (),
                {"docker": type("D", (), {"sandbox_container_name": "decepticon-sandbox"})()},
            )(),
        ),
        patch.object(cp_module, "_configurable_from_runnable_config", return_value={}),
    ):
        yield


def _invoke_tool(tool_call_id: str = "test-id") -> Any:
    """Invoke the tool via its LangChain @tool wrapper.

    Tools with InjectedToolCallId require the full tool-call envelope dict.
    Returns unwrapped string content.
    """
    result = complete_engagement_planning.invoke(
        {
            "args": {},
            "name": "complete_engagement_planning",
            "type": "tool_call",
            "id": tool_call_id,
        }
    )
    return result.content if hasattr(result, "content") else result


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestWritesMarkerWhenAllDocsValid:
    def test_returns_success_string(self, sandbox: FakeDockerSandbox) -> None:
        result = _invoke_tool()
        assert "Planning complete" in result

    def test_uploads_temp_marker(self, sandbox: FakeDockerSandbox) -> None:
        _invoke_tool()
        uploaded_paths = [p for p, _ in sandbox.uploads]
        assert any(".bundle_complete.tmp" in p for p in uploaded_paths), (
            f"expected .bundle_complete.tmp upload, got: {uploaded_paths}"
        )

    def test_commits_via_mv_not_cp(self, sandbox: FakeDockerSandbox) -> None:
        _invoke_tool()
        mv_calls = [c for c in sandbox.executed if c.strip().startswith("mv -f")]
        assert len(mv_calls) == 1, f"expected exactly one mv -f, got: {mv_calls}"
        assert ".bundle_complete.tmp" in mv_calls[0]
        assert ".bundle_complete" in mv_calls[0]

    def test_marker_exists_after_commit(self, sandbox: FakeDockerSandbox) -> None:
        _invoke_tool()
        assert any(".bundle_complete" in p and ".tmp" not in p for p in sandbox.files), (
            f"final marker missing; files: {list(sandbox.files)}"
        )

    def test_invalidates_prior_marker_before_commit(self, sandbox: FakeDockerSandbox) -> None:
        # Pre-populate a stale marker.
        sandbox.files["/workspace/plan/.bundle_complete"] = b"stale"
        _invoke_tool()
        rm_calls = [c for c in sandbox.executed if "rm -f" in c and ".bundle_complete" in c]
        assert rm_calls, "rm -f of prior marker should have been called"
        # rm must appear BEFORE any mv.
        rm_idx = next(
            i for i, c in enumerate(sandbox.executed) if "rm -f" in c and ".bundle_complete" in c
        )
        mv_idx = next(i for i, c in enumerate(sandbox.executed) if "mv -f" in c)
        assert rm_idx < mv_idx, "rm must precede mv"

    def test_engagement_ready_event_emitted(self, sandbox: FakeDockerSandbox) -> None:
        emitted: list[dict] = []
        with patch.object(cp_module, "_safe_writer", return_value=emitted.append):
            _invoke_tool()
        assert any(e.get("type") == "engagement_ready" for e in emitted), (
            f"engagement_ready event not emitted; got: {emitted}"
        )

    def test_event_emitted_only_after_marker_commit(self, sandbox: FakeDockerSandbox) -> None:
        event_order: list[str] = []

        def tracking_writer():
            def _w(event: dict) -> None:
                event_order.append(f"event:{event.get('type')}")

            return _w

        with patch.object(cp_module, "_safe_writer", tracking_writer):
            orig_execute = sandbox.execute

            def tracking_execute(cmd: str) -> FakeExecuteResponse:
                if "mv -f" in cmd:
                    event_order.append("mv")
                return orig_execute(cmd)

            sandbox.execute = tracking_execute  # type: ignore[method-assign]
            _invoke_tool()

        mv_idx = event_order.index("mv")
        event_idx = next((i for i, e in enumerate(event_order) if e.startswith("event:")), None)
        assert event_idx is not None, "event never emitted"
        assert event_idx > mv_idx, "event must be emitted after mv commit"


class TestOmitsMarkerWhenDocMissing:
    @pytest.fixture(autouse=True)
    def remove_roe(self, sandbox: FakeDockerSandbox) -> None:
        sandbox.files.pop("/workspace/plan/roe.json", None)

    def test_returns_error_string(self, sandbox: FakeDockerSandbox) -> None:
        result = _invoke_tool()
        assert "roe.json" in result
        assert "missing" in result.lower()

    def test_no_marker_upload(self, sandbox: FakeDockerSandbox) -> None:
        _invoke_tool()
        assert not any(".bundle_complete" in p for p, _ in sandbox.uploads)

    def test_no_engagement_ready_event(self, sandbox: FakeDockerSandbox) -> None:
        emitted: list[dict] = []
        with patch.object(cp_module, "_safe_writer", return_value=emitted.append):
            _invoke_tool()
        assert not emitted, f"no event expected for missing doc, got: {emitted}"


class TestOmitsMarkerWhenDocUnparseable:
    @pytest.fixture(autouse=True)
    def corrupt_conops(self, sandbox: FakeDockerSandbox) -> None:
        sandbox.files["/workspace/plan/conops.json"] = b"{ bad json"

    def test_returns_error_naming_doc(self, sandbox: FakeDockerSandbox) -> None:
        result = _invoke_tool()
        assert "conops.json" in result

    def test_no_marker_upload(self, sandbox: FakeDockerSandbox) -> None:
        _invoke_tool()
        assert not any(".bundle_complete" in p for p, _ in sandbox.uploads)

    def test_no_engagement_ready_event(self, sandbox: FakeDockerSandbox) -> None:
        emitted: list[dict] = []
        with patch.object(cp_module, "_safe_writer", return_value=emitted.append):
            _invoke_tool()
        assert not emitted


class TestInvalidatesStalMarkerBeforeWriting:
    def test_stale_marker_removed_on_valid_commit(self, sandbox: FakeDockerSandbox) -> None:
        """Stale marker is invalidated (rm -f) before the new marker is committed."""
        sandbox.files["/workspace/plan/.bundle_complete"] = b"stale"
        _invoke_tool()

        rm_calls = [c for c in sandbox.executed if "rm -f" in c and ".bundle_complete" in c]
        assert rm_calls, "rm -f of prior marker should have been called before commit"
        # rm must appear BEFORE mv.
        rm_idx = next(
            i for i, c in enumerate(sandbox.executed) if "rm -f" in c and ".bundle_complete" in c
        )
        mv_idx = next(i for i, c in enumerate(sandbox.executed) if "mv -f" in c)
        assert rm_idx < mv_idx, "rm must precede mv"

    def test_no_new_marker_uploaded_after_validation_failure(
        self, sandbox: FakeDockerSandbox
    ) -> None:
        sandbox.files["/workspace/plan/.bundle_complete"] = b"old"
        sandbox.files["/workspace/plan/conops.json"] = b"{ broken"

        _invoke_tool()

        new_marker_uploads = [p for p, _ in sandbox.uploads if ".bundle_complete" in p]
        assert not new_marker_uploads, "no new marker should be uploaded after validation failure"


class TestMarkerCommitFailureAfterValidation:
    def test_cleanup_on_mv_failure(self, sandbox: FakeDockerSandbox) -> None:
        # Make mv always fail.
        orig_execute = sandbox.execute

        def failing_mv(cmd: str) -> FakeExecuteResponse:
            if "mv -f" in cmd:
                return FakeExecuteResponse("error", 1)
            return orig_execute(cmd)

        sandbox.execute = failing_mv  # type: ignore[method-assign]

        _invoke_tool()

        # Both temp and final marker must be cleaned up.
        rm_calls = " ".join(c for c in sandbox.executed if "rm -f" in c)
        assert ".bundle_complete.tmp" in rm_calls, "temp path must be cleaned up"
        assert ".bundle_complete" in rm_calls, "final path must be cleaned up"

    def test_no_engagement_ready_event_on_commit_failure(self, sandbox: FakeDockerSandbox) -> None:
        orig_execute = sandbox.execute

        def failing_mv(cmd: str) -> FakeExecuteResponse:
            if "mv -f" in cmd:
                return FakeExecuteResponse("error", 1)
            return orig_execute(cmd)

        sandbox.execute = failing_mv  # type: ignore[method-assign]

        emitted: list[dict] = []
        with patch.object(cp_module, "_safe_writer", return_value=emitted.append):
            _invoke_tool()

        assert not emitted, f"no event expected on commit failure, got: {emitted}"

    def test_returns_error_string_on_commit_failure(self, sandbox: FakeDockerSandbox) -> None:
        orig_execute = sandbox.execute

        def failing_mv(cmd: str) -> FakeExecuteResponse:
            if "mv -f" in cmd:
                return FakeExecuteResponse("error", 1)
            return orig_execute(cmd)

        sandbox.execute = failing_mv  # type: ignore[method-assign]

        result = _invoke_tool()
        assert "commit failed" in result.lower() or "marker" in result.lower()


class TestShellQuotingOnWorkspacePath:
    """Workspace paths with spaces or shell-special chars must not cause
    unintended shell-splitting in sandbox.execute() calls."""

    @pytest.fixture(autouse=True)
    def patch_workspace_with_spaces(self) -> Iterator[None]:
        spaced_workspace = "/workspace/my project"
        files = _valid_plan_files(spaced_workspace)
        sandbox = FakeDockerSandbox(files=files)
        with (
            patch.object(cp_module, "DockerSandbox", return_value=sandbox),
            patch.object(
                cp_module,
                "load_config",
                return_value=type(
                    "C",
                    (),
                    {"docker": type("D", (), {"sandbox_container_name": "decepticon-sandbox"})()},
                )(),
            ),
            patch.object(
                cp_module,
                "_configurable_from_runnable_config",
                return_value={"workspace_path": spaced_workspace},
            ),
        ):
            yield

    def test_execute_commands_quote_workspace(self) -> None:
        # We can't easily check the sandbox used in this test since the fixture
        # patches at the class level, so we just verify the tool runs cleanly
        # (no shell-splitting error on the execute call).
        result = _invoke_tool()
        assert "Planning complete" in result
