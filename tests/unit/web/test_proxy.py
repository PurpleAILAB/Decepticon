"""Tests for the HTTP proxy session (record/replay/tamper/diff)."""

from __future__ import annotations

import json

import httpx
import pytest

from decepticon.tools.web.proxy import ProxyEntry, ProxySession

# ── helpers ──────────────────────────────────────────────────────


def _stub_responder(handler):
    """Wrap a callable into the ``sender`` callable ProxySession expects.

    The handler takes an httpx.Request and returns either a dict
    ``{status, headers, body}`` or an httpx.Response directly.
    """

    def sender(req: httpx.Request) -> httpx.Response:
        result = handler(req)
        if isinstance(result, httpx.Response):
            return result
        body = result.get("body", "")
        if isinstance(body, dict):
            body = json.dumps(body)
        return httpx.Response(
            status_code=result.get("status", 200),
            headers=result.get("headers", {}),
            content=body.encode("utf-8") if isinstance(body, str) else body,
            request=req,
        )

    return sender


# ── record ───────────────────────────────────────────────────────


def test_record_sends_and_captures_response():
    sent = {}

    def handler(req):
        sent["url"] = str(req.url)
        sent["method"] = req.method
        return {"status": 201, "body": "created"}

    sess = ProxySession(sender=_stub_responder(handler))
    entry = sess.record(
        "create",
        method="POST",
        url="https://api.example.com/widgets",
        headers={"X-Test": "1"},
        body='{"name":"x"}',
    )
    assert entry.response_status == 201
    assert entry.response_body == "created"
    assert sent["method"] == "POST"
    assert sent["url"] == "https://api.example.com/widgets"


def test_record_dry_run_with_send_false():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    entry = sess.record(
        "stage",
        method="GET",
        url="https://example.com",
        send=False,
    )
    assert entry.response_status is None
    assert entry.response_body == ""


def test_record_rejects_blank_name():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    with pytest.raises(ValueError, match="record name is required"):
        sess.record("", method="GET", url="https://x")


def test_record_rejects_duplicate_name():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("a", method="GET", url="https://x")
    with pytest.raises(ValueError, match="already exists"):
        sess.record("a", method="GET", url="https://y")


def test_record_max_entries_cap():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}), max_entries=2)
    sess.record("a", method="GET", url="https://x")
    sess.record("b", method="GET", url="https://y")
    with pytest.raises(RuntimeError, match="full"):
        sess.record("c", method="GET", url="https://z")


# ── list / get ───────────────────────────────────────────────────


def test_list_returns_insertion_order():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("first", method="GET", url="https://x")
    sess.record("second", method="GET", url="https://y")
    assert sess.list() == ["first", "second"]


def test_get_unknown_raises():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    with pytest.raises(KeyError):
        sess.get("missing")


# ── replay ──────────────────────────────────────────────────────


def test_replay_sends_modified_request():
    seen_urls = []

    def handler(req):
        seen_urls.append(str(req.url))
        return {"status": 200, "body": str(req.url)}

    sess = ProxySession(sender=_stub_responder(handler))
    sess.record("orig", method="GET", url="https://example.com/a")
    replayed = sess.replay("orig", url="https://example.com/b")
    assert "https://example.com/b" in replayed.response_body
    # Original entry not mutated
    assert sess.get("orig").url == "https://example.com/a"
    # Replay sent both requests
    assert seen_urls == ["https://example.com/a", "https://example.com/b"]


def test_replay_auto_names_when_unspecified():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("orig", method="GET", url="https://x")
    r1 = sess.replay("orig")
    r2 = sess.replay("orig")
    assert r1.name == "orig-replay-1"
    assert r2.name == "orig-replay-2"


def test_replay_overlays_headers():
    captured = {}

    def handler(req):
        captured["auth"] = req.headers.get("authorization")
        return {"status": 200}

    sess = ProxySession(sender=_stub_responder(handler))
    sess.record(
        "orig",
        method="GET",
        url="https://x",
        headers={"Authorization": "Bearer original"},
    )
    sess.replay("orig", headers={"Authorization": "Bearer rotated"})
    assert captured["auth"] == "Bearer rotated"


def test_replay_with_explicit_as_name():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("orig", method="GET", url="https://x")
    out = sess.replay("orig", as_name="custom")
    assert out.name == "custom"
    assert sess.get("custom") is out


# ── tamper ──────────────────────────────────────────────────────


def test_tamper_default_does_not_send():
    sent = []

    def handler(req):
        sent.append(str(req.url))
        return {"status": 200}

    sess = ProxySession(sender=_stub_responder(handler))
    sess.record("orig", method="POST", url="https://x", body='{"a":1}')
    mutated = sess.tamper("orig", body_overrides='{"a":2}')
    assert mutated.body == '{"a":2}'
    assert mutated.response_status is None
    # Only the original record fired the network call.
    assert sent == ["https://x"]


def test_tamper_with_send_true_dispatches():
    sent_bodies = []

    def handler(req):
        sent_bodies.append(req.content.decode("utf-8") if req.content else "")
        return {"status": 200, "body": "ok"}

    sess = ProxySession(sender=_stub_responder(handler))
    sess.record("orig", method="POST", url="https://x", body='{"a":1}', send=False)
    mutated = sess.tamper("orig", body_overrides='{"a":2}', send=True)
    assert mutated.response_status == 200
    assert sent_bodies == ['{"a":2}']


def test_tamper_overlays_headers_and_params():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("orig", method="GET", url="https://x", headers={"X": "1"}, params={"q": "a"})
    mutated = sess.tamper(
        "orig",
        header_overrides={"X-Forwarded-For": "127.0.0.1"},
        param_overrides={"q": "evil"},
    )
    assert mutated.headers["X"] == "1"
    assert mutated.headers["X-Forwarded-For"] == "127.0.0.1"
    assert mutated.params["q"] == "evil"


def test_tamper_auto_increments_sequence():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("orig", method="GET", url="https://x")
    sess.tamper("orig", header_overrides={"A": "1"})
    sess.tamper("orig", header_overrides={"A": "2"})
    assert "orig-tampered-1" in sess.list()
    assert "orig-tampered-2" in sess.list()


# ── diff ────────────────────────────────────────────────────────


def test_diff_returns_unified_diff():
    sess = ProxySession(
        sender=_stub_responder(lambda r: {"status": 200, "body": "first body\nshared\n"})
    )
    sess.record("a", method="GET", url="https://x")
    sess.get("a").response_body = "alpha\nbeta\ngamma\n"
    sess.get("a").__dict__["response_body"] = "alpha\nbeta\ngamma\n"
    sess.record("b", method="GET", url="https://y")
    sess.get("b").response_body = "alpha\nBETA\ngamma\n"
    diff = sess.diff("a", "b")
    assert "-beta" in diff
    assert "+BETA" in diff


def test_diff_returns_no_difference_when_identical():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200, "body": "same"}))
    sess.record("a", method="GET", url="https://x")
    sess.record("b", method="GET", url="https://y")
    assert sess.diff("a", "b").startswith("(no difference")


def test_diff_truncates_huge_outputs():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200}))
    sess.record("a", method="GET", url="https://x")
    sess.record("b", method="GET", url="https://y")
    sess.get("a").response_body = "\n".join(f"line-{i}" for i in range(500))
    sess.get("b").response_body = "\n".join(f"LINE-{i}" for i in range(500))
    out = sess.diff("a", "b", max_lines=20)
    assert "truncated" in out


# ── lifecycle ───────────────────────────────────────────────────


def test_session_supports_context_manager():
    closed = {"called": False}

    class _RecordingClient(httpx.Client):
        def close(self) -> None:  # type: ignore[override]
            closed["called"] = True
            super().close()

    with ProxySession(client=_RecordingClient()):
        pass
    assert closed["called"]


def test_to_dict_serialises_entries():
    sess = ProxySession(sender=_stub_responder(lambda r: {"status": 200, "body": "ok"}))
    sess.record("a", method="GET", url="https://x")
    payload = sess.to_dict()
    assert payload["entries"][0]["name"] == "a"
    assert payload["entries"][0]["response_status"] == 200


def test_proxy_entry_clone_does_not_mutate_original():
    e = ProxyEntry(name="a", method="GET", url="https://x", headers={"X": "1"})
    c = e.clone(name="b", headers={"X": "2"})
    assert e.headers == {"X": "1"}
    assert c.headers == {"X": "2"}


def test_proxy_entry_clone_rejects_unknown_field():
    e = ProxyEntry(name="a", method="GET", url="https://x")
    with pytest.raises(AttributeError):
        e.clone(does_not_exist="x")
