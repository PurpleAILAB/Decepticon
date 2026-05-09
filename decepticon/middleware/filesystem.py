"""FilesystemMiddleware without `execute`, scoped to the active engagement."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import validate_path
from deepagents.middleware.filesystem import FilesystemMiddleware as BaseFilesystemMiddleware

from decepticon.backends.docker_sandbox import DockerSandbox

WORKSPACE = "/workspace"
NO_WORKSPACE_ERROR = (
    "No engagement workspace is set. Filesystem tools are scoped to the active "
    "engagement and cannot access the shared /workspace root."
)


def _normalize_engagement_workspace(workspace_path: str | None) -> str | None:
    """Strict 4-case contract for resolving the engagement workspace root.

    - Empty / None → ``None`` (fail closed; no engagement configured).
    - ``/workspace`` → ``/workspace`` (launcher mode: the bind-mount IS the
      engagement root, so the literal root is a valid workspace).
    - ``/workspace/<safe-slug>`` → normalized path (web mode: shared root with
      per-engagement subdirectories).
    - Anything else (traversal like ``/workspace/../etc``, characters outside
      the slug regex, etc.) → ``None``. Invalid paths are NOT silently coerced
      to ``/workspace``.
    """
    path = (workspace_path or "").strip()
    if not path:
        return None
    if path == WORKSPACE:
        return WORKSPACE
    if not path.startswith(f"{WORKSPACE}/"):
        return None
    expected = path.rstrip("/")
    if os.path.normpath(expected) != expected:
        return None
    normalized = DockerSandbox._normalize_workspace_path(path)
    return normalized if normalized == expected else None


class EngagementFilesystemBackend(BackendProtocol):
    """Map virtual /workspace paths to /workspace/<engagement> internally."""

    def __init__(self, backend: BackendProtocol, workspace_path: str | None) -> None:
        self._backend = backend
        self._root = _normalize_engagement_workspace(workspace_path)

    def _real(self, path: str | None) -> str:
        if self._root is None:
            raise ValueError(NO_WORKSPACE_ERROR)
        virtual = validate_path(path or WORKSPACE)
        if virtual in {"/", WORKSPACE}:
            return self._root
        # Idempotent: if the path already points inside ``self._root`` it is
        # already a real engagement path — return as-is. Without this guard
        # the path gets re-prefixed and the engagement slug doubles, e.g.
        # ``/workspace/benchmark-XBEN-006-24/exploit/x.txt`` would resolve to
        # ``/workspace/benchmark-XBEN-006-24/benchmark-XBEN-006-24/exploit/x.txt``.
        # Caller-side prompts no longer need to teach agents about virtual vs
        # real paths — the backend accepts both.
        if virtual == self._root or virtual.startswith(f"{self._root}/"):
            return virtual
        rel = virtual.removeprefix(f"{WORKSPACE}/").lstrip("/")
        return f"{self._root}/{rel}" if rel else self._root

    def _virtual(self, path: str) -> str | None:
        if self._root is None:
            return None
        normalized = path.replace("\\", "/").rstrip("/")
        if normalized and not normalized.startswith("/"):
            normalized = f"{self._root}/{normalized}"
        if normalized == self._root:
            return WORKSPACE
        if normalized.startswith(f"{self._root}/"):
            return f"{WORKSPACE}/{normalized[len(self._root) + 1 :]}"
        return None

    def _glob(self, pattern: str) -> str:
        if self._root is None:
            raise ValueError(NO_WORKSPACE_ERROR)
        if not pattern.startswith("/"):
            return pattern
        virtual = validate_path(pattern)
        if virtual in {"/", WORKSPACE}:
            return "**/*"
        return virtual.removeprefix(f"{WORKSPACE}/").lstrip("/")

    def _info(self, info: FileInfo) -> FileInfo | None:
        path = self._virtual(info.get("path", ""))
        return {**info, "path": path} if path else None

    def ls(self, path: str) -> LsResult:
        try:
            real_path = self._real(path)
        except ValueError as e:
            return LsResult(error=str(e))
        result = self._backend.ls(real_path)
        if result.error:
            return result
        return LsResult(
            entries=[mapped for item in result.entries or [] if (mapped := self._info(item))]
        )

    def ls_info(self, path: str) -> list[FileInfo]:
        result = self.ls(path)
        return result.entries or []

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            return self._backend.read(self._real(file_path), offset=offset, limit=limit)
        except ValueError as e:
            return ReadResult(error=str(e))

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            result = self._backend.write(self._real(file_path), content)
        except ValueError as e:
            return WriteResult(error=str(e))
        path = self._virtual(result.path or "") if result.path else None
        return replace(result, path=path) if path else result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            result = self._backend.edit(self._real(file_path), old_string, new_string, replace_all)
        except ValueError as e:
            return EditResult(error=str(e))
        path = self._virtual(result.path or "") if result.path else None
        return replace(result, path=path) if path else result

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        try:
            real_path = self._real(path)
        except ValueError as e:
            return GrepResult(error=str(e))
        result = self._backend.grep(pattern, path=real_path, glob=glob)
        if result.error:
            return result
        return GrepResult(
            matches=[
                {**match, "path": mapped}
                for match in result.matches or []
                if (mapped := self._virtual(match.get("path", "")))
            ]
        )

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        result = self.grep(pattern, path=path, glob=glob)
        return result.error if result.error else result.matches or []

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        try:
            real_pattern = self._glob(pattern)
            real_path = self._real(path)
        except ValueError as e:
            return GlobResult(error=str(e))
        result = self._backend.glob(real_pattern, path=real_path)
        if result.error:
            return result
        return GlobResult(
            matches=[mapped for item in result.matches or [] if (mapped := self._info(item))]
        )

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        result = self.glob(pattern, path=path)
        return result.matches or []

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        try:
            real_paths = [self._real(path) for path in paths]
        except ValueError:
            return [
                FileDownloadResponse(path=path, content=None, error="invalid_path")
                for path in paths
            ]
        result = self._backend.download_files(real_paths)
        return [
            FileDownloadResponse(path=paths[i], content=response.content, error=response.error)
            for i, response in enumerate(result)
        ]


def _workspace_from_runtime(runtime: Any) -> str | None:
    state = getattr(runtime, "state", {}) or {}
    if hasattr(state, "get") and state.get("workspace_path"):
        return str(state["workspace_path"])
    configurable = (getattr(runtime, "config", {}) or {}).get("configurable", {})
    if isinstance(configurable, dict) and configurable.get("workspace_path"):
        return str(configurable["workspace_path"])
    return None


class FilesystemMiddleware(BaseFilesystemMiddleware):
    """FilesystemMiddleware with Decepticon's bash tool as the only executor."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.tools = [tool for tool in self.tools if tool.name != "execute"]

    def _get_backend(self, runtime) -> BackendProtocol:
        return EngagementFilesystemBackend(
            super()._get_backend(runtime), _workspace_from_runtime(runtime)
        )
