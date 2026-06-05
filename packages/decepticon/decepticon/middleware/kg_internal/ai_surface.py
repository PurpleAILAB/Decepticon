"""AI-attack-surface classification for recon ingest (ADR-0007).

The ``llm-redteam`` plugin can attack an exposed Ollama / framework
endpoint, but recon historically had no way to *recognize* one — an open
``11434`` landed as a ``Service`` with ``service=unknown``. This maps the
port the scanner already saw to a typed ``Technology`` node so the plugin
and the chain planner can route on it.

Port detection is the cheapest, most deterministic signal; the header /
banner / title classifiers (separate ingest passes) corroborate it and
add provenance. Two confidence tiers:

  * ``dedicated=True``  — a single-purpose AI default port (Ollama's
    11434). Recorded as a first-class detection.
  * ``dedicated=False`` — AI-associated but shared with generic services
    (Gradio / Ray dashboards also host non-AI apps). Recorded with
    ``guess=True`` so it cannot, on its own, drive an exploit chain
    (ADR-0007 corroborating-only rule).

The catalog is intentionally conservative — only ports whose AI default
is well documented — to keep precision high; banner/header passes widen
recall.
"""

from __future__ import annotations

import re
from typing import Any

from decepticon_core.types.kg import TechnologyCategory, technology_key

DETECTED_BY_PORT = "port-catalog"
DETECTED_BY_PATH = "endpoint-path"
DETECTED_BY_TITLE = "frontend-title"
DETECTED_BY_BANNER = "nmap-banner"
DETECTED_BY_HEADER = "http-header"

# Distinctive HTTP *response-header* name markers (matched against httpx's
# normalized header keys, e.g. ``x-litellm-version`` -> ``x_litellm_version``).
# These are the vendor-documented headers each product emits — LiteLLM's
# ``x-litellm-*`` proxy headers and text-generation-inference's
# ``x-compute-*`` / ``x-prompt-tokens`` telemetry. A header can be added by
# a fronting proxy, so every hit is corroborating-only (guess=True): it
# flags a likely AI backend for the port/banner passes to confirm.
# key-substring (normalized) -> (category, product).
_AI_HEADER_CATALOG: tuple[tuple[str, TechnologyCategory, str], ...] = (
    ("litellm", TechnologyCategory.AI_PROXY, "litellm"),
    ("x_compute_type", TechnologyCategory.AI_RUNTIME, "text-generation-inference"),
    ("x_prompt_tokens", TechnologyCategory.AI_RUNTIME, "text-generation-inference"),
)

# Word-boundary banner markers naming an AI runtime/proxy/framework in a
# service-fingerprint string (nmap product/version/name). A banner that
# names the product is strong evidence, so these are first-class (not
# guesses) — and they catch a runtime on a non-catalog port. Matched as
# whole tokens so "ollama" does not fire on "follama". marker ->
# (category, product).
_AI_BANNER_CATALOG: tuple[tuple[str, TechnologyCategory, str], ...] = (
    ("ollama", TechnologyCategory.AI_RUNTIME, "ollama"),
    ("vllm", TechnologyCategory.AI_RUNTIME, "vllm"),
    ("text-generation-inference", TechnologyCategory.AI_RUNTIME, "text-generation-inference"),
    ("llama.cpp", TechnologyCategory.AI_RUNTIME, "llama.cpp"),
    ("litellm", TechnologyCategory.AI_PROXY, "litellm"),
    ("mlflow", TechnologyCategory.AI_FRAMEWORK, "mlflow"),
)

# Distinctive HTML <title> substrings of AI web front-ends. A page title
# is operator-controllable, so every title hit is recorded guess=True
# (corroborating-only, ADR-0007) — it flags a likely AI UI for the
# header/port passes to confirm, never anchors an exploit chain alone.
# lowercase-substring -> (category, product).
_AI_TITLE_CATALOG: tuple[tuple[str, TechnologyCategory, str], ...] = (
    ("comfyui", TechnologyCategory.AI_FRAMEWORK, "comfyui"),
    ("open webui", TechnologyCategory.AI_FRAMEWORK, "open-webui"),
    ("text generation web ui", TechnologyCategory.AI_FRAMEWORK, "text-generation-webui"),
    ("stable diffusion", TechnologyCategory.AI_FRAMEWORK, "stable-diffusion"),
)

# port -> (category, product, dedicated)
_AI_PORT_CATALOG: dict[int, tuple[TechnologyCategory, str, bool]] = {
    11434: (TechnologyCategory.AI_RUNTIME, "ollama", True),
    7860: (TechnologyCategory.AI_FRAMEWORK, "gradio", False),
    8265: (TechnologyCategory.AI_FRAMEWORK, "ray", False),
}

# Exact request paths that name an AI inference interface. Ollama's REST
# routes are product-specific; the OpenAI-compatible routes are the
# de-facto standard vLLM / LiteLLM / LocalAI / text-generation-webui all
# expose, so they identify the *interface* even when the product is not
# yet pinned. path -> (category, product, dedicated).
_AI_PATH_CATALOG: dict[str, tuple[TechnologyCategory, str, bool]] = {
    "/api/tags": (TechnologyCategory.AI_RUNTIME, "ollama", True),
    "/api/version": (TechnologyCategory.AI_RUNTIME, "ollama", True),
    "/api/generate": (TechnologyCategory.AI_RUNTIME, "ollama", True),
    "/api/chat": (TechnologyCategory.AI_RUNTIME, "ollama", True),
    "/v1/chat/completions": (TechnologyCategory.AI_RUNTIME, "openai-compatible-api", True),
    "/v1/completions": (TechnologyCategory.AI_RUNTIME, "openai-compatible-api", True),
    "/v1/embeddings": (TechnologyCategory.AI_RUNTIME, "openai-compatible-api", True),
    "/v1/models": (TechnologyCategory.AI_RUNTIME, "openai-compatible-api", True),
}

# Path prefixes (sub-routed APIs).
_AI_PATH_PREFIXES: tuple[tuple[str, TechnologyCategory, str, bool], ...] = (
    ("/sdapi/v1", TechnologyCategory.AI_FRAMEWORK, "automatic1111", True),
)


def _classification(
    category: TechnologyCategory, product: str, *, detected_by: str, source: str, dedicated: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the ``(Technology node, RUNS edge)`` observation pair."""
    key = technology_key(category, product)
    props: dict[str, Any] = {
        "name": product,
        "category": category.value,
        "detected_by": detected_by,
        "source": source,
    }
    if not dedicated:
        props["guess"] = True
    node = {"kind": "Technology", "key": key, "label": product, "props": props}
    edge = {"to_key": key, "kind": "RUNS", "props": {"detected_by": detected_by}}
    return node, edge


def technology_for_port(port: int, source: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify a service port as an AI Technology.

    Returns ``(technology_node_observation, runs_edge)`` to append to the
    ingest batch — the edge belongs on the owning ``Service`` node's
    ``edges_out`` so it MERGEs as ``(Service)-[:RUNS]->(Technology)``.
    Returns ``None`` for any port not in the catalog.
    """
    entry = _AI_PORT_CATALOG.get(port)
    if entry is None:
        return None
    category, product, dedicated = entry
    return _classification(
        category, product, detected_by=DETECTED_BY_PORT, source=source, dedicated=dedicated
    )


def technology_for_path(
    path: str, status_code: int | None, source: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify a probed URL path as an AI inference interface.

    A ``404`` means the path was probed and is absent, so it is never
    classified; any other response (200/401/403/405 — auth or
    method-not-allowed still prove the route exists) is eligible.
    Returns the same ``(node, edge)`` pair shape as :func:`technology_for_port`.
    """
    if status_code == 404:
        return None
    normalized = path.split("?", 1)[0].rstrip("/").lower() or "/"
    entry = _AI_PATH_CATALOG.get(normalized)
    if entry is None:
        for prefix, category, product, dedicated in _AI_PATH_PREFIXES:
            if normalized.startswith(prefix):
                entry = (category, product, dedicated)
                break
    if entry is None:
        return None
    category, product, dedicated = entry
    return _classification(
        category, product, detected_by=DETECTED_BY_PATH, source=source, dedicated=dedicated
    )


def technology_for_title(
    title: str | None, source: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify an HTML page title as a likely AI web front-end.

    Always corroborating-only (``guess=True``): a title is operator
    controllable, so it flags an AI UI for a confirming pass, never
    anchors a chain. Returns ``None`` for an empty or unrecognized title.
    """
    if not title:
        return None
    normalized = title.strip().lower()
    for needle, category, product in _AI_TITLE_CATALOG:
        if needle in normalized:
            return _classification(
                category, product, detected_by=DETECTED_BY_TITLE, source=source, dedicated=False
            )
    return None


def technology_for_banner(
    banner: str | None, source: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify a service-fingerprint banner that names an AI runtime.

    A banner naming the product (nmap ``product``/``version``/``name``) is
    strong evidence, so hits are first-class — and they catch a runtime on
    a non-catalog port. Matched on token boundaries so ``ollama`` does not
    fire inside ``follama``. Returns ``None`` for an empty/unmatched banner.
    """
    if not banner:
        return None
    normalized = banner.strip().lower()
    for marker, category, product in _AI_BANNER_CATALOG:
        if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", normalized):
            return _classification(
                category, product, detected_by=DETECTED_BY_BANNER, source=source, dedicated=True
            )
    return None


def technology_for_headers(
    headers: dict[str, Any] | None, source: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Classify a response-header set that carries an AI product's headers.

    Always corroborating-only (``guess=True``): a header can be injected by
    a fronting proxy, so a hit flags a likely AI backend for the
    port/banner passes to confirm, never anchors a chain. ``headers`` is
    httpx's normalized name->value map; matching is on header *names*.
    Returns ``None`` for empty headers or no match.
    """
    if not isinstance(headers, dict) or not headers:
        return None
    keys = [str(k).lower() for k in headers]
    for marker, category, product in _AI_HEADER_CATALOG:
        if any(marker in key for key in keys):
            return _classification(
                category, product, detected_by=DETECTED_BY_HEADER, source=source, dedicated=False
            )
    return None
