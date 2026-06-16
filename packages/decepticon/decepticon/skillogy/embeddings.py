"""Embedding helper for skillogy hybrid retrieval (ADR-0011).

Used by BOTH boot-ingest (embed each ``:Skill`` once into Neo4j) and query-time
``find_skill`` (embed the query for the vector search). Embeddings go through
the **litellm proxy** the agents already use — the skillogy container must be
given ``DECEPTICON_LLM__PROXY_URL`` + ``DECEPTICON_LLM__PROXY_API_KEY`` (see
ADR-0011 §"Skillogy↔litellm coupling").

Degradation contract: this module **never raises** to its callers. When the
proxy is unconfigured or a request fails, ``embed_text`` returns ``None`` and
``find_skill`` falls back to the legacy substring path — semantic search is an
opt-in upgrade, not a hard dependency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# OSS default mirrors the KG layer's default (see kg_internal migration V002:
# "OpenAI text-embedding-3-small (1536) as the OSS default"). Override with
# DECEPTICON_SKILLOGY_EMBED_MODEL; set the matching dim if the model differs.
DEFAULT_EMBED_MODEL = "openai/text-embedding-3-small"
_KNOWN_DIMS: dict[str, int] = {
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "voyage-3": 1024,
    "voyage-3-lite": 512,
}
_DEFAULT_DIM = 1536

_REQUEST_TIMEOUT = 30.0


def embed_model() -> str:
    return os.environ.get("DECEPTICON_SKILLOGY_EMBED_MODEL", DEFAULT_EMBED_MODEL).strip()


def embed_dim() -> int:
    """Embedding dimension for the configured model (drives the vector index DDL).

    An explicit ``DECEPTICON_SKILLOGY_EMBED_DIM`` wins (for models not in the
    table); otherwise look the model up, else fall back to 1536.
    """
    raw = os.environ.get("DECEPTICON_SKILLOGY_EMBED_DIM", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return _KNOWN_DIMS.get(embed_model(), _DEFAULT_DIM)


def _proxy() -> tuple[str, str] | None:
    """``(base_url, api_key)`` for the litellm proxy, or ``None`` if unconfigured."""
    base = os.environ.get("DECEPTICON_LLM__PROXY_URL", "").strip()
    key = os.environ.get("DECEPTICON_LLM__PROXY_API_KEY", "").strip()
    if not base or not key:
        return None
    return base.rstrip("/"), key


def available() -> bool:
    """True when an embedding model is reachable (proxy configured)."""
    return _proxy() is not None


def _cache_dir() -> Path:
    raw = os.environ.get("DECEPTICON_SKILLOGY_EMBED_CACHE", "").strip()
    path = Path(raw) if raw else Path(tempfile.gettempdir()) / "decepticon-skillogy-embed"
    return path


def _cache_key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def _cache_get(model: str, text: str) -> list[float] | None:
    path = _cache_dir() / f"{_cache_key(model, text)}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_put(model: str, text: str, vector: list[float]) -> None:
    cache = _cache_dir()
    try:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{_cache_key(model, text)}.json").write_text(json.dumps(vector), encoding="utf-8")
    except OSError:  # cache is best-effort
        pass


def _request_embeddings(
    base_url: str, key: str, model: str, inputs: list[str]
) -> list[list[float]]:
    """POST to the proxy's OpenAI-compatible ``/v1/embeddings``. May raise."""
    resp = httpx.post(
        f"{base_url}/v1/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "input": inputs},
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    # OpenAI shape: {"data": [{"embedding": [...], "index": 0}, ...]}
    rows = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [list(r["embedding"]) for r in rows]


def embed_batch(texts: list[str]) -> list[list[float] | None]:
    """Embed many texts. Returns one vector per input, or ``None`` per input
    when embeddings are unavailable / the request fails. Never raises.

    Cached entries are served without a network call; only the cache misses
    are sent to the proxy in one batched request.
    """
    if not texts:
        return []
    model = embed_model()
    results: list[list[float] | None] = [None] * len(texts)

    # Serve cache hits first.
    misses: list[int] = []
    for i, text in enumerate(texts):
        cached = _cache_get(model, text)
        if cached is not None:
            results[i] = cached
        else:
            misses.append(i)
    if not misses:
        return results

    proxy = _proxy()
    if proxy is None:
        log.info("skillogy embeddings unavailable (no litellm proxy env); falling back")
        return results  # misses stay None → caller falls back

    base_url, key = proxy
    try:
        vectors = _request_embeddings(base_url, key, model, [texts[i] for i in misses])
    except Exception as exc:  # noqa: BLE001 - degrade, never raise to caller
        log.warning("skillogy embedding request failed (%s); falling back", type(exc).__name__)
        return results
    if len(vectors) != len(misses):
        log.warning("skillogy embedding count mismatch (%d != %d)", len(vectors), len(misses))
        return results
    for idx, vec in zip(misses, vectors, strict=True):
        results[idx] = vec
        _cache_put(model, texts[idx], vec)
    return results


def embed_text(text: str) -> list[float] | None:
    """Embed one text. ``None`` when unavailable / on failure (never raises)."""
    return embed_batch([text])[0]
