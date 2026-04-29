"""Pipe-pane log moved to /workspace/.sessions/, manager dict is lock-protected."""
from unittest.mock import patch
from decepticon.backends.docker_sandbox import TmuxSessionManager


def test_initialize_pipes_pane_to_workspace_sessions_log():
    mgr = TmuxSessionManager("scan-1", "decepticon-sandbox")
    TmuxSessionManager._initialized.discard("scan-1")

    with patch.object(mgr, "_docker_tmux") as mock_tmux, \
         patch("decepticon.backends.docker_sandbox.subprocess.run") as mock_run, \
         patch("time.sleep"):
        mock_tmux.side_effect = [
            RuntimeError("session not found"),
            "", "", "", "", "", "",
        ]
        mock_run.return_value.returncode = 0
        mgr.initialize()

    pipe_pane_call = next(
        c for c in mock_tmux.call_args_list if c.args[0][0] == "pipe-pane"
    )
    args = pipe_pane_call.args[0]
    cmd_arg = args[args.index("-o") + 1]
    assert cmd_arg == "cat >> /workspace/.sessions/scan-1.log"


def test_initialize_creates_sessions_directory_inside_container():
    mgr = TmuxSessionManager("scan-2", "decepticon-sandbox")
    TmuxSessionManager._initialized.discard("scan-2")

    with patch.object(mgr, "_docker_tmux") as mock_tmux, \
         patch("decepticon.backends.docker_sandbox.subprocess.run") as mock_run, \
         patch("time.sleep"):
        mock_tmux.side_effect = [RuntimeError("session not found"),
                                 "", "", "", "", "", ""]
        mock_run.return_value.returncode = 0
        mgr.initialize()

    mkdir_calls = [c for c in mock_run.call_args_list
                   if "mkdir" in (c.args[0] if c.args else [])]
    assert mkdir_calls, "Expected a docker exec mkdir call"
    cmd = mkdir_calls[0].args[0]
    assert "/workspace/.sessions" in cmd


import logging
from subprocess import CalledProcessError


def test_initialize_warns_when_mkdir_fails(caplog):
    mgr = TmuxSessionManager("scan-3", "decepticon-sandbox")
    TmuxSessionManager._initialized.discard("scan-3")

    decepticon_logger = logging.getLogger("decepticon")
    original_propagate = decepticon_logger.propagate
    decepticon_logger.propagate = True
    try:
        with patch.object(mgr, "_docker_tmux") as mock_tmux, \
             patch("decepticon.backends.docker_sandbox.subprocess.run") as mock_run, \
             patch("time.sleep"):
            mock_tmux.side_effect = [RuntimeError("session not found"),
                                     "", "", "", "", "", ""]
            mock_run.side_effect = CalledProcessError(1, ["docker", "exec"])
            with caplog.at_level(logging.WARNING):
                mgr.initialize()
    finally:
        decepticon_logger.propagate = original_propagate

    assert any("pipe-pane setup failed" in r.message for r in caplog.records), \
        f"Expected warning log; got {[r.message for r in caplog.records]}"


import threading
from decepticon.backends.docker_sandbox import (
    BackgroundJobTracker,
    DockerSandbox,
)


def test_get_manager_concurrent_returns_same_instance():
    sandbox = DockerSandbox(container_name="test")
    seen: list[int] = []
    seen_lock = threading.Lock()

    def worker():
        mgr = sandbox._get_manager("shared")
        with seen_lock:
            seen.append(id(mgr))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(set(seen)) == 1, "All threads must see the same manager instance"


def test_sandbox_has_jobs_tracker():
    sandbox = DockerSandbox(container_name="test")
    assert isinstance(sandbox._jobs, BackgroundJobTracker)


def test_sandbox_has_log_offsets_dict():
    sandbox = DockerSandbox(container_name="test")
    assert isinstance(sandbox._log_offsets, dict)
    assert sandbox._log_offsets == {}


from deepagents.backends.protocol import FileDownloadResponse


def _file_response(path: str, content: bytes) -> FileDownloadResponse:
    return FileDownloadResponse(path=path, content=content, error=None)


def test_read_session_log_diff_returns_full_log_on_first_call():
    sandbox = DockerSandbox(container_name="test")

    with patch.object(sandbox, "download_files") as mock_dl:
        mock_dl.return_value = [
            _file_response("/workspace/.sessions/scan.log", b"line1\nline2\nline3\n"),
        ]
        diff = sandbox.read_session_log_diff("scan")

    assert "line1" in diff and "line3" in diff


def test_read_session_log_diff_returns_only_new_bytes_on_second_call():
    sandbox = DockerSandbox(container_name="test")

    with patch.object(sandbox, "download_files") as mock_dl:
        mock_dl.return_value = [_file_response("/workspace/.sessions/scan.log", b"old\n")]
        sandbox.read_session_log_diff("scan")

        mock_dl.return_value = [_file_response("/workspace/.sessions/scan.log", b"old\nnew\n")]
        diff = sandbox.read_session_log_diff("scan")

    assert "old" not in diff and "new" in diff


def test_read_session_log_diff_empty_when_no_new_bytes():
    sandbox = DockerSandbox(container_name="test")

    with patch.object(sandbox, "download_files") as mock_dl:
        mock_dl.return_value = [_file_response("/workspace/.sessions/scan.log", b"data\n")]
        sandbox.read_session_log_diff("scan")
        diff = sandbox.read_session_log_diff("scan")

    assert diff == ""


def test_read_session_log_diff_recovers_when_file_truncated():
    sandbox = DockerSandbox(container_name="test")

    with patch.object(sandbox, "download_files") as mock_dl:
        mock_dl.return_value = [_file_response("/workspace/.sessions/scan.log", b"a" * 100)]
        sandbox.read_session_log_diff("scan")

        # File shrank (rotation / external truncation)
        mock_dl.return_value = [_file_response("/workspace/.sessions/scan.log", b"x" * 5)]
        diff = sandbox.read_session_log_diff("scan")

    assert diff == "xxxxx"


def test_reset_session_log_offset_clears_state():
    sandbox = DockerSandbox(container_name="test")
    sandbox._log_offsets["scan"] = 42
    sandbox.reset_session_log_offset("scan")
    assert "scan" not in sandbox._log_offsets


def test_read_session_log_diff_returns_empty_when_file_missing():
    sandbox = DockerSandbox(container_name="test")
    with patch.object(sandbox, "download_files") as mock_dl:
        mock_dl.return_value = [
            FileDownloadResponse(
                path="/workspace/.sessions/scan.log",
                content=None,
                error="file_not_found",
            ),
        ]
        diff = sandbox.read_session_log_diff("scan")
    assert diff == ""


def test_read_session_log_diff_concurrent_does_not_double_count():
    """20 threads reading the same session log must collectively consume
    each byte exactly once — no overlap, no gaps."""
    sandbox = DockerSandbox(container_name="test")
    payload = b"x" * 1000

    def fake_download(paths):
        return [_file_response(paths[0], payload)]

    with patch.object(sandbox, "download_files", side_effect=fake_download):
        barrier = threading.Barrier(20)
        results: list[str] = []
        results_lock = threading.Lock()

        def worker():
            barrier.wait()
            r = sandbox.read_session_log_diff("scan")
            with results_lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()

    # Exactly one thread sees the full payload; the other 19 see ""
    full_reads = [r for r in results if r]
    empty_reads = [r for r in results if not r]
    assert len(full_reads) == 1
    assert len(empty_reads) == 19
    assert full_reads[0] == "x" * 1000
    assert sandbox._log_offsets["scan"] == 1000
