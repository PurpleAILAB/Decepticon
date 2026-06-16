"""Unit tests for the skillogy embedding helper (ADR-0011).

The helper underpins hybrid retrieval but must degrade silently: with no
litellm proxy configured it returns ``None`` so ``find_skill`` falls back to
the legacy substring path. These tests pin that contract plus the cache and
batch behaviour, with the HTTP layer faked — no network, no real proxy.
"""

from __future__ import annotations

from typing import Any

import pytest

from decepticon.skillogy import embeddings


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no proxy and a private, empty disk cache."""
    monkeypatch.delenv("DECEPTICON_LLM__PROXY_URL", raising=False)
    monkeypatch.delenv("DECEPTICON_LLM__PROXY_API_KEY", raising=False)
    monkeypatch.delenv("DECEPTICON_SKILLOGY_EMBED_MODEL", raising=False)
    monkeypatch.delenv("DECEPTICON_SKILLOGY_EMBED_DIM", raising=False)
    monkeypatch.setenv("DECEPTICON_SKILLOGY_EMBED_CACHE", str(tmp_path / "embed-cache"))


def _set_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECEPTICON_LLM__PROXY_URL", "http://litellm:4000/")
    monkeypatch.setenv("DECEPTICON_LLM__PROXY_API_KEY", "sk-test")


# --- availability / config -------------------------------------------------


def test_unavailable_without_proxy() -> None:
    assert embeddings.available() is False
    assert embeddings.embed_text("anything") is None


def test_available_with_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)
    assert embeddings.available() is True


def test_embed_dim_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    assert embeddings.embed_model() == "text-embedding-3-small"
    assert embeddings.embed_dim() == 1536
    monkeypatch.setenv("DECEPTICON_SKILLOGY_EMBED_MODEL", "text-embedding-3-large")
    assert embeddings.embed_dim() == 3072
    # explicit dim wins for an unknown model
    monkeypatch.setenv("DECEPTICON_SKILLOGY_EMBED_MODEL", "some-private-model")
    monkeypatch.setenv("DECEPTICON_SKILLOGY_EMBED_DIM", "256")
    assert embeddings.embed_dim() == 256
    # unknown model, no explicit dim → fallback
    monkeypatch.delenv("DECEPTICON_SKILLOGY_EMBED_DIM")
    assert embeddings.embed_dim() == 1536


# --- happy path / batching -------------------------------------------------


def _fake_response(
    monkeypatch: pytest.MonkeyPatch, vectors_by_input: dict[str, list[float]]
) -> list[dict]:
    """Patch the HTTP call to echo deterministic vectors and record calls."""
    calls: list[dict] = []

    def fake_request(base_url: str, key: str, model: str, inputs: list[str]) -> list[list[float]]:
        calls.append({"base_url": base_url, "key": key, "model": model, "inputs": list(inputs)})
        return [vectors_by_input[text] for text in inputs]

    monkeypatch.setattr(embeddings, "_request_embeddings", fake_request)
    return calls


def test_embed_text_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)
    calls = _fake_response(monkeypatch, {"hello": [0.1, 0.2, 0.3]})
    assert embeddings.embed_text("hello") == [0.1, 0.2, 0.3]
    assert calls[0]["base_url"] == "http://litellm:4000"  # trailing slash stripped
    assert calls[0]["inputs"] == ["hello"]


def test_embed_batch_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)
    _fake_response(monkeypatch, {"a": [1.0], "b": [2.0], "c": [3.0]})
    assert embeddings.embed_batch(["a", "b", "c"]) == [[1.0], [2.0], [3.0]]


def test_embed_batch_empty() -> None:
    assert embeddings.embed_batch([]) == []


# --- cache -----------------------------------------------------------------


def test_cache_avoids_second_request(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)
    calls = _fake_response(monkeypatch, {"x": [9.0]})
    assert embeddings.embed_text("x") == [9.0]
    assert embeddings.embed_text("x") == [9.0]
    assert len(calls) == 1  # second call served from disk cache


def test_cache_only_misses_hit_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)
    calls = _fake_response(monkeypatch, {"a": [1.0], "b": [2.0]})
    embeddings.embed_text("a")  # warm cache for "a"
    calls.clear()
    assert embeddings.embed_batch(["a", "b"]) == [[1.0], [2.0]]
    assert calls[0]["inputs"] == ["b"]  # only the miss is requested


# --- degradation -----------------------------------------------------------


def test_request_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)

    def boom(*_a: Any, **_k: Any) -> list[list[float]]:
        raise RuntimeError("proxy down")

    monkeypatch.setattr(embeddings, "_request_embeddings", boom)
    assert embeddings.embed_text("y") is None
    assert embeddings.embed_batch(["y", "z"]) == [None, None]


def test_count_mismatch_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_proxy(monkeypatch)

    def short(base_url: str, key: str, model: str, inputs: list[str]) -> list[list[float]]:
        return [[1.0]]  # one vector for two inputs

    monkeypatch.setattr(embeddings, "_request_embeddings", short)
    assert embeddings.embed_batch(["one", "two"]) == [None, None]


def test_no_proxy_batch_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # proxy intentionally unset by the autouse fixture
    assert embeddings.embed_batch(["p", "q"]) == [None, None]


# --- response parsing ------------------------------------------------------


def test_request_parses_openai_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_request_embeddings`` sorts by ``index`` and unwraps embeddings."""
    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict:
            return {
                "data": [
                    {"embedding": [2.0], "index": 1},
                    {"embedding": [1.0], "index": 0},
                ]
            }

    def fake_post(url: str, **kwargs: Any) -> _Resp:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["headers"] = kwargs["headers"]
        return _Resp()

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    out = embeddings._request_embeddings("http://litellm:4000", "sk-test", "m", ["a", "b"])
    assert out == [[1.0], [2.0]]  # reordered by index
    assert captured["url"] == "http://litellm:4000/v1/embeddings"
    assert captured["json"] == {"model": "m", "input": ["a", "b"]}
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
