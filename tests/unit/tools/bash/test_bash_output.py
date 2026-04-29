"""bash_output / bash_kill / bash_status tool unit tests."""

import asyncio
from unittest.mock import MagicMock

from decepticon.backends.docker_sandbox import BackgroundJobTracker
from decepticon.tools.bash.bash import (
    bash_kill,
    bash_output,
    bash_status,
    set_sandbox,
)


def _fake_sandbox():
    sandbox = MagicMock()
    sandbox._jobs = BackgroundJobTracker()
    return sandbox


def test_bash_output_running_job_returns_running_marker():
    sandbox = _fake_sandbox()
    sandbox._jobs.register("scan", command="nmap", initial_markers=1)
    sandbox.poll_completion = MagicMock(side_effect=lambda s: sandbox._jobs.get(s))
    sandbox.read_session_log_diff = MagicMock(return_value="partial output")
    set_sandbox(sandbox)

    result = asyncio.run(bash_output.ainvoke({"session": "scan"}))

    assert "[RUNNING" in result
    assert "partial output" in result


def test_bash_output_done_job_marks_consumed_and_exposes_exit_code():
    sandbox = _fake_sandbox()
    sandbox._jobs.register("scan", command="nmap", initial_markers=1)
    sandbox._jobs.mark_complete("scan", exit_code=0)
    sandbox.poll_completion = MagicMock(side_effect=lambda s: sandbox._jobs.get(s))
    sandbox.read_session_log_diff = MagicMock(return_value="full nmap output")
    set_sandbox(sandbox)

    result = asyncio.run(bash_output.ainvoke({"session": "scan"}))

    assert "[DONE" in result
    assert "exit=0" in result
    assert sandbox._jobs.get("scan").consumed is True


def test_bash_output_idle_when_no_job_registered():
    sandbox = _fake_sandbox()
    sandbox.poll_completion = MagicMock(return_value=None)
    sandbox.read_session_log_diff = MagicMock(return_value="")
    set_sandbox(sandbox)

    result = asyncio.run(bash_output.ainvoke({"session": "never-seen"}))

    assert "[IDLE]" in result


def test_bash_kill_invokes_sandbox_kill_session():
    sandbox = _fake_sandbox()
    sandbox._jobs.register("scan", command="nmap", initial_markers=1)
    sandbox.kill_session = MagicMock()
    set_sandbox(sandbox)

    result = asyncio.run(bash_kill.ainvoke({"session": "scan"}))

    sandbox.kill_session.assert_called_once_with("scan")
    assert "[KILLED]" in result
    assert "scan" in result


def test_bash_status_lists_running_and_done_jobs():
    sandbox = _fake_sandbox()
    sandbox._jobs.register("scan", command="nmap target", initial_markers=1)
    sandbox._jobs.register("brute", command="hydra ...", initial_markers=1)
    sandbox._jobs.mark_complete("brute", exit_code=1)
    sandbox.poll_completion = MagicMock(side_effect=lambda s: sandbox._jobs.get(s))
    set_sandbox(sandbox)

    result = asyncio.run(bash_status.ainvoke({}))

    assert "scan" in result and "running" in result
    assert "brute" in result and "exit=1" in result


def test_bash_status_empty_returns_empty_marker():
    sandbox = _fake_sandbox()
    set_sandbox(sandbox)
    result = asyncio.run(bash_status.ainvoke({}))
    assert "[EMPTY]" in result
