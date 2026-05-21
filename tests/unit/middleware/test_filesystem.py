from __future__ import annotations

from deepagents.backends.protocol import (
    FileDownloadResponse,
    FileInfo,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.middleware.filesystem import FilesystemMiddleware as BaseFilesystemMiddleware

from decepticon.middleware.filesystem import EngagementFilesystemBackend, FilesystemMiddleware


class RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ls_info(self, path: str) -> list[FileInfo]:
        self.calls.append(("ls_info", path))
        return [{"path": f"{path}/plan/roe.json", "is_dir": False}]

    def ls(self, path: str) -> LsResult:
        return LsResult(entries=self.ls_info(path))

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        self.calls.append(("read", (file_path, offset, limit)))
        return ReadResult(file_data={"content": f"read:{file_path}", "encoding": "utf-8"})

    def write(self, file_path: str, content: str) -> WriteResult:
        self.calls.append(("write", (file_path, content)))
        return WriteResult(path=file_path)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        self.calls.append(("glob_info", (pattern, path)))
        return [{"path": "plan/roe.json", "is_dir": False}]

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        return GlobResult(matches=self.glob_info(pattern, path))

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None):
        self.calls.append(("grep_raw", (pattern, path, glob)))
        suffix = "roe.json" if (path or "").endswith("/plan") else "plan/roe.json"
        return [{"path": f"{path}/{suffix}", "line": 1, "text": "target"}]

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        return GrepResult(matches=self.grep_raw(pattern, path, glob))

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        self.calls.append(("download_files", paths))
        return [FileDownloadResponse(path=paths[0], content=b"image")]


def test_maps_virtual_workspace_paths_to_engagement_root() -> None:
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/test")

    result = scoped.read("/workspace/plan/roe.json")

    assert result.file_data == {
        "content": "read:/workspace/test/plan/roe.json",
        "encoding": "utf-8",
    }
    assert backend.calls[-1] == ("read", ("/workspace/test/plan/roe.json", 0, 2000))


def test_real_path_is_accepted_idempotently() -> None:
    """Passing the already-real engagement path must not double the slug.

    Regression: agent prompts historically advertised the real per-engagement
    path (e.g. ``/workspace/test``) and instructed sub-agents to use it as
    their workspace root. The agent then passed
    ``/workspace/test/exploit/x.txt`` to filesystem tools. Without
    idempotency, ``_real()`` re-prefixed ``self._root`` and produced
    ``/workspace/test/test/exploit/x.txt`` — a duplicated nested directory
    visible on the host as ``~/.decepticon/workspace/test/test/...``. The
    backend now detects "already inside ``self._root``" and returns the
    path unchanged, so both virtual (``/workspace/...``) and real
    (``/workspace/test/...``) inputs converge on the same on-disk file.
    """
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/test")

    result = scoped.read("/workspace/test/plan/roe.json")

    assert result.file_data == {
        "content": "read:/workspace/test/plan/roe.json",
        "encoding": "utf-8",
    }
    # Critical: the real-path input is not re-prefixed into
    # /workspace/test/test/plan/roe.json.
    assert backend.calls[-1] == ("read", ("/workspace/test/plan/roe.json", 0, 2000))


def test_returns_virtual_paths_to_agent() -> None:
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/test")

    assert scoped.ls("/workspace").entries == [
        {"path": "/workspace/plan/roe.json", "is_dir": False}
    ]
    write_result = scoped.write("/workspace/findings/FIND-001.md", "x")

    assert write_result.path == "/workspace/findings/FIND-001.md"


def test_scopes_glob_and_grep_without_exposing_real_engagement_path() -> None:
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/test")

    assert scoped.glob("/workspace/**/*.json").matches == [
        {"path": "/workspace/plan/roe.json", "is_dir": False}
    ]
    assert backend.calls[-1] == ("glob_info", ("**/*.json", "/workspace/test"))

    assert scoped.grep("target", path="/workspace").matches == [
        {"path": "/workspace/plan/roe.json", "line": 1, "text": "target"}
    ]
    assert backend.calls[-1] == ("grep_raw", ("target", "/workspace/test", None))


def test_filesystem_middleware_removes_execute_without_rewriting_descriptions() -> None:
    base = BaseFilesystemMiddleware(backend=RecordingBackend())
    middleware = FilesystemMiddleware(backend=RecordingBackend())
    base_descriptions = {tool.name: tool.description for tool in base.tools}
    descriptions = {tool.name: tool.description for tool in middleware.tools}

    assert "execute" not in descriptions
    assert descriptions == {
        name: description for name, description in base_descriptions.items() if name != "execute"
    }


def test_missing_engagement_workspace_fails_closed() -> None:
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, None)

    assert scoped.ls("/workspace").error is not None
    assert scoped.read("/workspace/plan/roe.json").error is not None
    assert scoped.glob("**/*.json").error is not None
    assert scoped.grep("target", path="/workspace").error is not None
    assert backend.calls == []


def test_root_workspace_accepted_as_engagement_root() -> None:
    """Launcher mode binds the engagement directory directly at ``/workspace``.

    The bare root must be accepted as a valid engagement root so filesystem
    tools work without a slug prefix. ``ls /workspace`` must hit the backend
    at ``/workspace`` (no doubling) and surface entries unchanged.
    """
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace")

    result = scoped.ls("/workspace")

    assert result.error is None
    assert result.entries == [{"path": "/workspace/plan/roe.json", "is_dir": False}]
    assert backend.calls[-1] == ("ls_info", "/workspace")


def test_root_workspace_no_prefix_doubling_under_engagement_root() -> None:
    """Reads under ``/workspace`` in launcher mode must not get prefixed twice."""
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace")

    scoped.read("/workspace/plan/roe.json")

    assert backend.calls[-1] == ("read", ("/workspace/plan/roe.json", 0, 2000))


def test_root_workspace_accepts_trailing_slash() -> None:
    """``/workspace/`` (trailing slash) is the same engagement root."""
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/")

    result = scoped.ls("/workspace")

    assert result.error is None
    assert backend.calls[-1] == ("ls_info", "/workspace")


def test_traversal_path_fails_closed_does_not_silently_coerce() -> None:
    """``..`` traversal must fail closed rather than collapse to ``/workspace``.

    Without the ``os.path.normpath`` guard the slug regex would accept the
    component, which would then resolve to a path outside the engagement.
    """
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/workspace/../etc")

    assert scoped.ls("/workspace").error is not None
    assert backend.calls == []


def test_invalid_path_outside_workspace_fails_closed() -> None:
    """Anything not under ``/workspace`` must fail closed (no silent coerce)."""
    backend = RecordingBackend()
    scoped = EngagementFilesystemBackend(backend, "/etc")

    assert scoped.ls("/workspace").error is not None
    assert backend.calls == []
