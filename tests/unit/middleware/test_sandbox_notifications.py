"""SandboxNotificationMiddleware injects <system-reminder> for completed jobs."""
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from decepticon.backends.docker_sandbox import BackgroundJobTracker
from decepticon.middleware.sandbox_notifications import (
    SandboxNotificationMiddleware,
)


def _state(*messages):
    return {"messages": list(messages)}


def _sandbox_with_tracker():
    sandbox = MagicMock()
    sandbox._jobs = BackgroundJobTracker()
    sandbox.poll_completion = MagicMock(side_effect=lambda s: sandbox._jobs.get(s))
    return sandbox


def test_no_pending_completions_returns_no_update():
    sandbox = _sandbox_with_tracker()
    mw = SandboxNotificationMiddleware(sandbox=sandbox)

    update = mw.before_model(_state(HumanMessage(content="hi")), runtime=None)

    assert update is None or not update.get("messages")


def test_pending_completion_appends_human_system_reminder():
    sandbox = _sandbox_with_tracker()
    sandbox._jobs.register("scan", command="nmap target", initial_markers=1)
    sandbox._jobs.mark_complete("scan", exit_code=0)
    mw = SandboxNotificationMiddleware(sandbox=sandbox)

    update = mw.before_model(_state(HumanMessage(content="hi"), AIMessage(content="ok")),
                             runtime=None)

    assert update is not None
    new_messages = update["messages"]
    msg = new_messages[0]
    assert isinstance(msg, HumanMessage)
    assert "<system-reminder>" in msg.content
    assert "scan" in msg.content
    assert "exit 0" in msg.content


def test_already_notified_completions_are_not_re_emitted():
    sandbox = _sandbox_with_tracker()
    sandbox._jobs.register("scan", command="nmap", initial_markers=1)
    sandbox._jobs.mark_complete("scan", exit_code=0)
    mw = SandboxNotificationMiddleware(sandbox=sandbox)

    mw.before_model(_state(HumanMessage(content="hi")), runtime=None)
    update2 = mw.before_model(_state(HumanMessage(content="hi")), runtime=None)

    assert update2 is None or not update2.get("messages")


def test_consumed_jobs_are_not_notified():
    sandbox = _sandbox_with_tracker()
    sandbox._jobs.register("scan", command="nmap", initial_markers=1)
    sandbox._jobs.mark_complete("scan", exit_code=0)
    sandbox._jobs.mark_consumed("scan")
    mw = SandboxNotificationMiddleware(sandbox=sandbox)

    update = mw.before_model(_state(HumanMessage(content="hi")), runtime=None)

    assert update is None or not update.get("messages")


def test_multiple_completions_aggregate_into_one_message():
    sandbox = _sandbox_with_tracker()
    sandbox._jobs.register("a", command="cmd-a", initial_markers=1)
    sandbox._jobs.register("b", command="cmd-b", initial_markers=1)
    sandbox._jobs.mark_complete("a", exit_code=0)
    sandbox._jobs.mark_complete("b", exit_code=2)
    mw = SandboxNotificationMiddleware(sandbox=sandbox)

    update = mw.before_model(_state(HumanMessage(content="hi")), runtime=None)

    assert update is not None
    msgs = update["messages"]
    assert len(msgs) == 1
    content = msgs[0].content
    assert "a" in content and "b" in content
    assert content.count("<system-reminder>") == 1
