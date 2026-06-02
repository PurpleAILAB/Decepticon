"""Unit tests for `_redact_url_credentials` proxy URL scrubbing."""

from __future__ import annotations

from decepticon.llm.factory import _redact_url_credentials


def test_redacts_user_and_password() -> None:
    assert _redact_url_credentials("http://user:secret@litellm:4000") == "http://***@litellm:4000"


def test_redacts_user_only() -> None:
    assert _redact_url_credentials("http://user@litellm:4000") == "http://***@litellm:4000"


def test_plain_url_unchanged() -> None:
    assert _redact_url_credentials("http://litellm:4000") == "http://litellm:4000"


def test_https_with_path_preserved() -> None:
    assert (
        _redact_url_credentials("https://u:p@host.example.com:443/v1/chat")
        == "https://***@host.example.com:443/v1/chat"
    )


def test_no_secret_substring_in_output() -> None:
    out = _redact_url_credentials("http://admin:hunter2@proxy:4000")
    assert "hunter2" not in out
    assert "admin" not in out


def test_non_url_input_returned_as_is() -> None:
    assert _redact_url_credentials("not a url") == "not a url"
    assert _redact_url_credentials("") == ""
