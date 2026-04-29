"""Background job tracker — pure-Python unit tests + start/poll integration."""
from unittest.mock import MagicMock, patch
from decepticon.backends.docker_sandbox import (
    BackgroundJob,
    BackgroundJobTracker,
    DockerSandbox,
)


def test_register_records_command_and_marker_count():
    tracker = BackgroundJobTracker()
    job = tracker.register("scan-1", command="nmap target", initial_markers=3)

    assert job.session == "scan-1"
    assert job.command == "nmap target"
    assert job.initial_markers == 3
    assert job.status == "running"
    assert job.exit_code is None
    assert job.consumed is False


def test_mark_complete_records_exit_code():
    tracker = BackgroundJobTracker()
    tracker.register("scan-1", command="nmap target", initial_markers=3)
    tracker.mark_complete("scan-1", exit_code=0)
    job = tracker.get("scan-1")
    assert job.status == "done"
    assert job.exit_code == 0
    assert job.completed_at is not None
    assert job.consumed is False


def test_mark_consumed_after_output_retrieval():
    tracker = BackgroundJobTracker()
    tracker.register("scan-1", command="nmap target", initial_markers=3)
    tracker.mark_complete("scan-1", exit_code=0)
    tracker.mark_consumed("scan-1")
    assert tracker.get("scan-1").consumed is True


def test_pending_completions_returns_done_unconsumed_only():
    tracker = BackgroundJobTracker()
    tracker.register("a", command="x", initial_markers=1)
    tracker.register("b", command="y", initial_markers=1)
    tracker.register("c", command="z", initial_markers=1)
    tracker.mark_complete("a", exit_code=0)
    tracker.mark_complete("b", exit_code=1)
    tracker.mark_consumed("a")
    pending = tracker.pending_completions()
    assert [j.session for j in pending] == ["b"]


def test_register_replaces_previous_job_in_same_session():
    tracker = BackgroundJobTracker()
    tracker.register("scan", command="first", initial_markers=1)
    tracker.mark_complete("scan", exit_code=0)
    tracker.register("scan", command="second", initial_markers=2)
    job = tracker.get("scan")
    assert job.command == "second"
    assert job.status == "running"


def test_remove_drops_session_entry():
    tracker = BackgroundJobTracker()
    tracker.register("scan", command="x", initial_markers=1)
    tracker.remove("scan")
    assert tracker.get("scan") is None


def test_start_background_registers_job_with_initial_marker_count():
    sandbox = DockerSandbox(container_name="test")
    fake_baseline = "[DCPTN:0:/workspace] "

    with patch.object(sandbox, "_get_manager") as mock_get:
        mgr = MagicMock()
        mgr._capture.return_value = fake_baseline
        mgr.initialize.return_value = None
        mgr._send.return_value = None
        mock_get.return_value = mgr

        sandbox.start_background("nmap target", session="scan")

    job = sandbox._jobs.get("scan")
    assert job is not None
    assert job.command == "nmap target"
    assert job.initial_markers == 1
    assert job.status == "running"


def test_poll_completion_marks_done_when_new_marker_appears():
    sandbox = DockerSandbox(container_name="test")
    sandbox._jobs.register("scan", command="nmap target", initial_markers=1)

    with patch.object(sandbox, "_get_manager") as mock_get:
        mgr = MagicMock()
        mgr._capture.return_value = (
            "[DCPTN:0:/workspace] nmap target\n"
            "nmap output...\n"
            "[DCPTN:0:/workspace] "
        )
        mock_get.return_value = mgr

        sandbox.poll_completion("scan")

    job = sandbox._jobs.get("scan")
    assert job.status == "done"
    assert job.exit_code == 0


def test_poll_completion_keeps_running_without_new_marker():
    sandbox = DockerSandbox(container_name="test")
    sandbox._jobs.register("scan", command="nmap target", initial_markers=1)

    with patch.object(sandbox, "_get_manager") as mock_get:
        mgr = MagicMock()
        mgr._capture.return_value = "[DCPTN:0:/workspace] nmap target\nstill running\n"
        mock_get.return_value = mgr

        sandbox.poll_completion("scan")

    assert sandbox._jobs.get("scan").status == "running"


def test_poll_completion_returns_none_for_unknown_session():
    sandbox = DockerSandbox(container_name="test")
    assert sandbox.poll_completion("never-seen") is None


def test_poll_completion_handles_capture_failure_gracefully():
    sandbox = DockerSandbox(container_name="test")
    sandbox._jobs.register("scan", command="x", initial_markers=1)

    with patch.object(sandbox, "_get_manager") as mock_get:
        mgr = MagicMock()
        mgr._capture.side_effect = RuntimeError("no server running")
        mock_get.return_value = mgr

        result = sandbox.poll_completion("scan")

    assert result.status == "running"
