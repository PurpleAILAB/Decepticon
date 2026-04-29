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
