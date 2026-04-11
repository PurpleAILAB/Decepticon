"""Tests for HTTP history helpers."""

from __future__ import annotations

from decepticon.tools.web.http import HTTPHistory, HTTPRequest, HTTPResponse


def _request(req_id: str, *, url: str = "https://example.test") -> HTTPRequest:
    return HTTPRequest(
        id=req_id,
        method="GET",
        url=url,
        headers={},
        body=b"",
        timestamp=1.0,
    )


def _response(request_id: str, *, status: int = 200) -> HTTPResponse:
    return HTTPResponse(
        id=f"resp-{request_id}",
        request_id=request_id,
        status=status,
        headers={},
        body=b"ok",
        elapsed_ms=5.0,
        timestamp=2.0,
    )


def test_get_by_id_uses_latest_recorded_pair() -> None:
    history = HTTPHistory(maxlen=4)
    req = _request("req-1")
    resp = _response("req-1")

    history.record(req, resp)

    assert history.get_by_id("req-1") == (req, resp)


def test_get_by_id_evicts_oldest_entry_when_history_rolls_over() -> None:
    history = HTTPHistory(maxlen=2)
    first = _request("req-1", url="https://one.test")
    second = _request("req-2", url="https://two.test")
    third = _request("req-3", url="https://three.test")

    history.record(first, _response("req-1"))
    history.record(second, _response("req-2"))
    history.record(third, _response("req-3"))

    assert history.get_by_id("req-1") is None
    assert history.get_by_id("req-2") is not None
    assert history.get_by_id("req-3") is not None
    assert [req.id for req, _ in history] == ["req-2", "req-3"]
