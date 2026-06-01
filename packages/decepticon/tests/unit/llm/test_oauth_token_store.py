"""Unit tests for the shared OAuth token store helper module.

The module under test lives at ``config/oauth_token_store.py`` and is
mounted into the LiteLLM container — it is not part of the ``decepticon``
package, so we import it via ``importlib.util.spec_from_file_location``
the same way ``test_litellm_dynamic_config.py`` does.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

# ``oauth_token_store`` lives in the LiteLLM container's ``/app`` and imports
# ``litellm`` at module level for ``AuthenticationError``. The dev test env
# does not install LiteLLM (it's a runtime container dep), so we inject a
# minimal stub before loading the module.
if "litellm" not in sys.modules:
    sys.modules["litellm"] = types.ModuleType("litellm")

import litellm  # noqa: E402  — resolved via the stub above when LiteLLM is absent


class _StubAuthenticationError(Exception):
    def __init__(self, message: str = "", model: str = "", llm_provider: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.model = model
        self.llm_provider = llm_provider


if not hasattr(litellm, "AuthenticationError"):
    litellm.AuthenticationError = _StubAuthenticationError

_MODULE_PATH = Path(__file__).resolve().parents[5] / "config" / "oauth_token_store.py"
_spec = importlib.util.spec_from_file_location("decepticon_oauth_token_store", _MODULE_PATH)
assert _spec is not None
assert _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

read_json_file = _module.read_json_file
write_json_atomic = _module.write_json_atomic
FileBackedCache = _module.FileBackedCache
decode_jwt_payload = _module.decode_jwt_payload
is_jwt_expired = _module.is_jwt_expired
is_timestamp_expired = _module.is_timestamp_expired
oauth_refresh_request = _module.oauth_refresh_request
with_retry_on_401 = _module.with_retry_on_401
DEFAULT_REFRESH_BUFFER_SECONDS = _module.DEFAULT_REFRESH_BUFFER_SECONDS


# ── read_json_file ──────────────────────────────────────────────────────


def test_read_json_file_returns_dict_on_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"access": "abc", "n": 1}))
    assert read_json_file(path) == {"access": "abc", "n": 1}


def test_read_json_file_returns_none_on_missing_file(tmp_path: Path) -> None:
    assert read_json_file(tmp_path / "absent.json") is None


def test_read_json_file_returns_none_on_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json")
    assert read_json_file(path) is None


def test_read_json_file_returns_none_when_top_level_is_not_dict(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]))
    assert read_json_file(path) is None


# ── write_json_atomic ──────────────────────────────────────────────────


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode 0o600 is not enforced on Windows")
def test_write_json_atomic_writes_payload_with_secure_mode(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    payload = {"access": "abc"}
    assert write_json_atomic(path, payload) is True
    assert json.loads(path.read_text()) == payload
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_write_json_atomic_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "subdir" / "tokens.json"
    assert write_json_atomic(path, {"a": 1}) is True
    assert path.exists()


def test_write_json_atomic_uses_atomic_temp_then_rename(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    write_json_atomic(path, {"v": "first"})
    write_json_atomic(path, {"v": "second"})
    # Every temp sibling must be cleaned up after the rename.
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
    assert json.loads(path.read_text()) == {"v": "second"}


def test_write_json_atomic_uses_unique_temp_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # B8: two LiteLLM workers refreshing the same OAuth file must NOT share a
    # temp path, or their writes collide and corrupt the token. Each call must
    # allocate a process-unique temp file (tempfile.mkstemp) before renaming.
    path = tmp_path / "tokens.json"
    seen: list[str] = []
    real_replace = os.replace

    def spy_replace(src: Any, dst: Any) -> None:
        seen.append(Path(src).name)
        real_replace(src, dst)

    monkeypatch.setattr(_module.os, "replace", spy_replace)
    assert write_json_atomic(path, {"v": 1}) is True
    assert write_json_atomic(path, {"v": 2}) is True

    assert len(seen) == 2
    assert seen[0] != seen[1]  # unique temp per write — no shared-path collision
    for name in seen:
        assert name.startswith(f".{path.name}.")
        assert name.endswith(".tmp")
    assert json.loads(path.read_text()) == {"v": 2}


@pytest.mark.skipif(os.name == "nt", reason="chmod-based directory locking is a no-op on Windows")
def test_write_json_atomic_returns_false_when_target_dir_unwritable(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)  # read+exec, no write
    try:
        assert write_json_atomic(locked / "tokens.json", {"a": 1}) is False
    finally:
        locked.chmod(0o700)


# ── FileBackedCache ────────────────────────────────────────────────────


def _loader_counter() -> tuple[Any, list[int]]:
    calls = [0]

    def loader(path: Path) -> dict[str, Any] | None:
        calls[0] += 1
        if not path.exists():
            return None
        return json.loads(path.read_text())

    return loader, calls


def test_file_backed_cache_returns_loader_result_on_first_get(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"v": 1}))
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    assert cache.get() == {"v": 1}
    assert calls[0] == 1


def test_file_backed_cache_skips_loader_on_unchanged_file(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"v": 1}))
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    cache.get()
    cache.get()
    cache.get()
    assert calls[0] == 1


def test_file_backed_cache_reloads_when_mtime_changes(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"v": 1}))
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    assert cache.get() == {"v": 1}

    # Bump mtime + size to defeat any 1-second filesystem resolution.
    path.write_text(json.dumps({"v": 2, "filler": "x" * 64}))
    new_mtime = path.stat().st_mtime + 5
    os.utime(path, (new_mtime, new_mtime))

    assert cache.get() == {"v": 2, "filler": "x" * 64}
    assert calls[0] == 2


def test_file_backed_cache_returns_loader_result_when_file_missing(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    assert cache.get() is None
    assert calls[0] == 1
    # Each missing-file access re-invokes the loader; the loader can decide.
    assert cache.get() is None
    assert calls[0] == 2


def test_file_backed_cache_replace_avoids_reread_on_next_get(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"v": "original"}))
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    cache.get()  # priming load

    cache.replace({"v": "refreshed"})
    assert cache.get() == {"v": "refreshed"}
    # replace stamped the cache key; no extra loader call required.
    assert calls[0] == 1


def test_file_backed_cache_invalidate_forces_reread(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"v": 1}))
    loader, calls = _loader_counter()
    cache = FileBackedCache(path, loader)
    cache.get()
    cache.invalidate()
    cache.get()
    assert calls[0] == 2


# ── decode_jwt_payload / is_jwt_expired ────────────────────────────────


def _jwt(payload: dict[str, Any]) -> str:
    body = urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"header.{body}.signature"


def test_decode_jwt_payload_returns_dict_for_well_formed_token() -> None:
    token = _jwt({"sub": "u1", "exp": 123})
    assert decode_jwt_payload(token) == {"sub": "u1", "exp": 123}


def test_decode_jwt_payload_returns_empty_dict_for_malformed_token() -> None:
    assert decode_jwt_payload("not-a-jwt") == {}
    assert decode_jwt_payload("a.b") == {}


def test_decode_jwt_payload_returns_empty_dict_for_non_string_input() -> None:
    assert decode_jwt_payload(None) == {}
    assert decode_jwt_payload(12345) == {}  # type: ignore[arg-type]


def test_is_jwt_expired_false_for_future_exp() -> None:
    token = _jwt({"exp": int(time.time()) + 3600})
    assert is_jwt_expired(token) is False


def test_is_jwt_expired_true_when_exp_within_skew() -> None:
    token = _jwt({"exp": int(time.time()) + 30})
    assert is_jwt_expired(token, skew_seconds=60) is True


def test_is_jwt_expired_true_when_exp_missing() -> None:
    token = _jwt({"sub": "u1"})
    assert is_jwt_expired(token) is True


# ── is_timestamp_expired ──────────────────────────────────────────────


def test_is_timestamp_expired_treats_zero_as_never() -> None:
    assert is_timestamp_expired(0) is False
    assert is_timestamp_expired(None) is False


def test_is_timestamp_expired_handles_seconds_input() -> None:
    assert is_timestamp_expired(time.time() + 3600, buffer_seconds=300) is False
    assert is_timestamp_expired(time.time() + 60, buffer_seconds=300) is True


def test_is_timestamp_expired_auto_detects_milliseconds() -> None:
    future_ms = (time.time() + 3600) * 1000
    assert is_timestamp_expired(future_ms, buffer_seconds=300) is False
    near_ms = (time.time() + 60) * 1000
    assert is_timestamp_expired(near_ms, buffer_seconds=300) is True


def test_is_timestamp_expired_uses_default_buffer() -> None:
    # Default buffer is 5 min; exp 4 min in the future should be treated as expired.
    assert is_timestamp_expired(time.time() + 4 * 60) is True
    assert is_timestamp_expired(time.time() + 6 * 60) is False
    assert DEFAULT_REFRESH_BUFFER_SECONDS == 5 * 60


# ── oauth_refresh_request ─────────────────────────────────────────────


def _httpx_response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://example.test/oauth/token"),
    )


def test_oauth_refresh_request_returns_parsed_payload_on_success() -> None:
    expected = {"access_token": "new", "expires_in": 3600}
    with patch.object(
        _module, "_http_post", return_value=_httpx_response(200, expected)
    ) as mock_post:
        result = oauth_refresh_request(
            "https://example.test/oauth/token",
            {"grant_type": "refresh_token", "refresh_token": "r"},
            provider_label="provider-x",
        )
    assert result == expected
    args, kwargs = mock_post.call_args
    assert args[0] == "https://example.test/oauth/token"
    assert kwargs.get("json") == {"grant_type": "refresh_token", "refresh_token": "r"}


def test_oauth_refresh_request_supports_form_body() -> None:
    with patch.object(
        _module, "_http_post", return_value=_httpx_response(200, {"a": 1})
    ) as mock_post:
        oauth_refresh_request(
            "https://example.test/oauth/token",
            {"k": "v"},
            json_body=False,
        )
    _, kwargs = mock_post.call_args
    assert kwargs.get("data") == {"k": "v"}
    assert "json" not in kwargs


def test_oauth_refresh_request_raises_on_4xx_with_body_in_message() -> None:
    bad = _httpx_response(400, {"error": "bad_grant"})
    with patch.object(_module, "_http_post", return_value=bad):
        with pytest.raises(litellm.AuthenticationError) as exc:
            oauth_refresh_request(
                "https://example.test/oauth/token",
                {"grant_type": "refresh_token"},
                provider_label="provider-x",
            )
    assert "provider-x" in str(exc.value)


def test_oauth_refresh_request_raises_when_response_is_not_object() -> None:
    not_object = httpx.Response(
        status_code=200,
        content=b'"raw-string"',
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://example.test/oauth/token"),
    )
    with patch.object(_module, "_http_post", return_value=not_object):
        with pytest.raises(litellm.AuthenticationError) as exc:
            oauth_refresh_request(
                "https://example.test/oauth/token",
                {"k": "v"},
                provider_label="provider-x",
            )
    assert "provider-x" in str(exc.value)


# ── with_retry_on_401 ─────────────────────────────────────────────────


def _stub_response(status_code: int) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=b"{}",
        request=httpx.Request("POST", "https://example.test/api"),
    )


def test_with_retry_on_401_returns_immediately_on_success() -> None:
    calls: list[bool] = []

    def send(force_refresh: bool) -> httpx.Response:
        calls.append(force_refresh)
        return _stub_response(200)

    resp = with_retry_on_401(send)
    assert resp.status_code == 200
    assert calls == [False]


def test_with_retry_on_401_replays_with_force_refresh_on_first_401() -> None:
    calls: list[bool] = []

    def send(force_refresh: bool) -> httpx.Response:
        calls.append(force_refresh)
        return _stub_response(401 if not force_refresh else 200)

    resp = with_retry_on_401(send)
    assert resp.status_code == 200
    assert calls == [False, True]


def test_with_retry_on_401_returns_last_401_after_exhausting_attempts() -> None:
    calls: list[bool] = []

    def send(force_refresh: bool) -> httpx.Response:
        calls.append(force_refresh)
        return _stub_response(401)

    resp = with_retry_on_401(send, max_attempts=2)
    assert resp.status_code == 401
    assert calls == [False, True]


def test_with_retry_on_401_does_not_retry_other_4xx() -> None:
    calls: list[bool] = []

    def send(force_refresh: bool) -> httpx.Response:
        calls.append(force_refresh)
        return _stub_response(403)

    resp = with_retry_on_401(send)
    assert resp.status_code == 403
    assert calls == [False]
