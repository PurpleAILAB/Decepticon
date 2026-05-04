"""FilesystemMiddleware without `execute`, scoped to the active engagement."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    GrepMatch,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import validate_path
from deepagents.middleware.filesystem import FilesystemMiddleware as BaseFilesystemMiddleware

from decepticon.backends.docker_sandbox import DockerSandbox

WORKSPACE = "/workspace"


class EngagementFilesystemBackend(BackendProtocol):
    """Map virtual /workspace paths to /workspace/<engagement> internally."""

    def __init__(self, backend: BackendProtocol, workspace_path: str) -> None:
        self._backend = backend
        self._root = DockerSandbox._normalize_workspace_path(workspace_path)

    def _real(self, path: str | None) -> str:
        if self._root == WORKSPACE:
            return validate_path(path or WORKSPACE)
        virtual = validate_path(path or WORKSPACE)
        if virtual in {"/", WORKSPACE}:
            return self._root
        rel = virtual.removeprefix(f"{WORKSPACE}/").lstrip("/")
        return f"{self._root}/{rel}" if rel else self._root

    def _virtual(self, path: str) -> str | None:
        if self._root == WORKSPACE:
            return path
        normalized = path.replace("\\", "/").rstrip("/")
        if normalized and not normalized.startswith("/"):
            normalized = f"{self._root}/{normalized}"
        if normalized == self._root:
            return WORKSPACE
        if normalized.startswith(f"{self._root}/"):
            return f"{WORKSPACE}/{normalized[len(self._root) + 1 :]}"
        return None

    def _glob(self, pattern: str) -> str:
        if not pattern.startswith("/"):
            return pattern
        virtual = validate_path(pattern)
        if virtual in {"/", WORKSPACE}:
            return "**/*"
        return virtual.removeprefix(f"{WORKSPACE}/").lstrip("/")

    def _info(self, info: FileInfo) -> FileInfo | None:
        path = self._virtual(info.get("path", ""))
        return {**info, "path": path} if path else None

    def ls_info(self, path: str) -> list[FileInfo]:
        return [
            mapped
            for item in self._backend.ls_info(self._real(path))
            if (mapped := self._info(item))
        ]

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._backend.read(self._real(file_path), offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        result = self._backend.write(self._real(file_path), content)
        path = self._virtual(result.path or "") if result.path else None
        return replace(result, path=path) if path else result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self._backend.edit(self._real(file_path), old_string, new_string, replace_all)
        path = self._virtual(result.path or "") if result.path else None
        return replace(result, path=path) if path else result

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        result = self._backend.grep_raw(pattern, path=self._real(path), glob=glob)
        if isinstance(result, str):
            return result
        return [
            {**match, "path": mapped}
            for match in result
            if (mapped := self._virtual(match.get("path", "")))
        ]

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return [
            mapped
            for item in self._backend.glob_info(self._glob(pattern), path=self._real(path))
            if (mapped := self._info(item))
        ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        result = self._backend.download_files([self._real(path) for path in paths])
        return [
            FileDownloadResponse(path=paths[i], content=response.content, error=response.error)
            for i, response in enumerate(result)
        ]


def _workspace_from_runtime(runtime: Any) -> str:
    state = getattr(runtime, "state", {}) or {}
    if hasattr(state, "get") and state.get("workspace_path"):
        return str(state["workspace_path"])
    configurable = (getattr(runtime, "config", {}) or {}).get("configurable", {})
    return (
        str(configurable.get("workspace_path", WORKSPACE))
        if isinstance(configurable, dict)
        else WORKSPACE
    )


class FilesystemMiddleware(BaseFilesystemMiddleware):
    """FilesystemMiddleware with Decepticon's bash tool as the only executor."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.tools = [tool for tool in self.tools if tool.name != "execute"]

    def _get_backend(self, runtime) -> BackendProtocol:
        return EngagementFilesystemBackend(
            super()._get_backend(runtime), _workspace_from_runtime(runtime)
        )
