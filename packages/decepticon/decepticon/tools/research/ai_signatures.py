"""AI attack-surface signal catalogs (proposal items 1-4, ADR-0007).

Cheap, deterministic classifiers that recognise AI runtimes, proxies, and
frameworks from data recon already captures — response headers, open ports,
``nmap -sV`` banners, and page titles. Each match resolves to a
:class:`~decepticon_core.types.kg.TechnologyCategory` so the ``kg_ingest_*``
fan-in can MERGE a typed ``Technology`` node the chain planner and the
``llm-redteam`` plugin route on, instead of walking past an exposed
Ollama / vLLM / MLflow / ComfyUI service blind.

Ported as pure-Python regex catalogs from RedAmon's
``recon/helpers/ai_signal_catalog.py`` — the imperative pipeline plumbing is
deliberately left behind (see ``docs/proposals/redamon-feature-integration.md``).

Confidence policy (ADR-0007): distinctive **headers** and high-confidence
vendor **ports** are ``"high"`` and may drive routing on their own; **title**
and **banner** matches are ``"low"`` — recorded as corroborating-only so a
guess cannot, by itself, drive an exploit chain.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from decepticon_core.types.kg import TechnologyCategory, technology_key

__all__ = [
    "AI_PORTS",
    "TechMatch",
    "classify_ai_endpoint",
    "dedup_matches",
    "lookup_ai_port",
    "match_ai_banner",
    "match_ai_headers",
    "match_ai_title",
]

_HIGH = "high"
_LOW = "low"


@dataclass(frozen=True)
class TechMatch:
    """A resolved AI-technology detection.

    ``name`` is the canonical product label, ``category`` its closed-vocabulary
    bucket, ``confidence`` is ``"high"`` (routable alone) or ``"low"``
    (corroborating-only), and ``detected_by`` is the provenance channel stored
    on the ``Technology`` node.
    """

    name: str
    category: TechnologyCategory
    confidence: str
    detected_by: str
    version: str | None = None


# ── HTTP response-header signatures (high confidence) ────────────────────
#
# Header *names* uniquely emitted by an AI runtime / proxy / framework. These
# are strong, active-response signals — a server that sets ``anthropic-version``
# or ``x-litellm-*`` *is* that stack, not merely a page that talks to it.
_HEADER_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str, TechnologyCategory], ...] = (
    (
        re.compile(r"^openai-(?:organization|version|processing-ms)$"),
        "OpenAI API",
        TechnologyCategory.AI_RUNTIME,
    ),
    (
        re.compile(r"^anthropic-(?:version|ratelimit-.+)$"),
        "Anthropic API",
        TechnologyCategory.AI_RUNTIME,
    ),
    (re.compile(r"^x-litellm(?:-.+)?$"), "LiteLLM", TechnologyCategory.AI_PROXY),
    (re.compile(r"^cf-aig-.+$"), "Cloudflare AI Gateway", TechnologyCategory.AI_PROXY),
    (re.compile(r"^x-amzn-bedrock-.+$"), "AWS Bedrock", TechnologyCategory.AI_PROXY),
    (re.compile(r"^x-vllm(?:-.+)?$"), "vLLM", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"^x-ollama(?:-.+)?$"), "Ollama", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"^x-triton(?:-.+)?$"), "Triton Inference Server", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"^x-bentoml(?:-.+)?$"), "BentoML", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"^x-modal(?:-.+)?$"), "Modal", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"^x-mlflow(?:-.+)?$"), "MLflow", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"^x-lang(?:serve|chain)(?:-.+)?$"), "LangServe", TechnologyCategory.AI_FRAMEWORK),
    (
        re.compile(r"^mcp-(?:session-id|protocol-version)$"),
        "MCP Server",
        TechnologyCategory.AI_FRAMEWORK,
    ),
)

# ``Server`` header *value* tokens. Substring (not full-match) so
# ``Server: uvicorn`` noise is ignored while ``Server: vLLM/0.5.0`` matches.
_SERVER_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str, TechnologyCategory], ...] = (
    (re.compile(r"\bvllm\b"), "vLLM", TechnologyCategory.AI_RUNTIME),
    (
        re.compile(r"text-generation-inference|\btgi\b"),
        "Text Generation Inference",
        TechnologyCategory.AI_RUNTIME,
    ),
    (re.compile(r"\bollama\b"), "Ollama", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"triton"), "Triton Inference Server", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"litellm"), "LiteLLM", TechnologyCategory.AI_PROXY),
    (re.compile(r"comfyui"), "ComfyUI", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"localai"), "LocalAI", TechnologyCategory.AI_RUNTIME),
)


# ── Port catalog (two-tier disambiguation) ──────────────────────────────
#
# High-confidence vendor ports auto-promote to a Technology node. Generic
# ports (8000/8080/3000/…) are recorded as ``_LOW`` so the masscan/nmap
# ingest can *gate* them — it only MERGEs a node for ``"high"`` matches, and
# waits for an HTTP header/title to corroborate the generic ones.
AI_PORTS: dict[int, TechMatch] = {
    # High-confidence — a single vendor owns this default port.
    11434: TechMatch("Ollama", TechnologyCategory.AI_RUNTIME, _HIGH, "port-catalog"),
    1234: TechMatch("LM Studio", TechnologyCategory.AI_RUNTIME, _HIGH, "port-catalog"),
    4891: TechMatch("GPT4All", TechnologyCategory.AI_RUNTIME, _HIGH, "port-catalog"),
    6333: TechMatch("Qdrant", TechnologyCategory.DATABASE, _HIGH, "port-catalog"),
    6334: TechMatch("Qdrant", TechnologyCategory.DATABASE, _HIGH, "port-catalog"),
    19530: TechMatch("Milvus", TechnologyCategory.DATABASE, _HIGH, "port-catalog"),
    8188: TechMatch("ComfyUI", TechnologyCategory.AI_FRAMEWORK, _HIGH, "port-catalog"),
    8265: TechMatch("Ray Dashboard", TechnologyCategory.AI_FRAMEWORK, _HIGH, "port-catalog"),
    # Low-confidence — port is *frequently* an AI stack but widely reused.
    8000: TechMatch("vLLM", TechnologyCategory.AI_RUNTIME, _LOW, "port-catalog"),
    8001: TechMatch("Triton Inference Server", TechnologyCategory.AI_RUNTIME, _LOW, "port-catalog"),
    7860: TechMatch("Gradio", TechnologyCategory.AI_FRAMEWORK, _LOW, "port-catalog"),
    8501: TechMatch("Streamlit", TechnologyCategory.AI_FRAMEWORK, _LOW, "port-catalog"),
    4000: TechMatch("LiteLLM", TechnologyCategory.AI_PROXY, _LOW, "port-catalog"),
}


# ── Page-title signatures (low confidence — corroborating only) ──────────
_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], str, TechnologyCategory], ...] = (
    (re.compile(r"open\s*webui", re.I), "Open WebUI", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"librechat", re.I), "LibreChat", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"flowise", re.I), "Flowise", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"langflow", re.I), "Langflow", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"comfyui", re.I), "ComfyUI", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"\bmlflow\b", re.I), "MLflow", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"\bdify\b", re.I), "Dify", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"ray dashboard", re.I), "Ray Dashboard", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"anythingllm", re.I), "AnythingLLM", TechnologyCategory.AI_FRAMEWORK),
    (
        re.compile(r"text generation web ?ui|oobabooga", re.I),
        "text-generation-webui",
        TechnologyCategory.AI_FRAMEWORK,
    ),
    (
        re.compile(r"stable diffusion|automatic1111", re.I),
        "Stable Diffusion WebUI",
        TechnologyCategory.AI_FRAMEWORK,
    ),
    (re.compile(r"label studio", re.I), "Label Studio", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"kubeflow", re.I), "Kubeflow", TechnologyCategory.AI_FRAMEWORK),
    (re.compile(r"\blocalai\b", re.I), "LocalAI", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"\bollama\b", re.I), "Ollama", TechnologyCategory.AI_RUNTIME),
)


# ── nmap -sV banner signatures (low confidence — corroborating only) ─────
_BANNER_PATTERNS: tuple[tuple[re.Pattern[str], str, TechnologyCategory], ...] = (
    (re.compile(r"\bollama\b", re.I), "Ollama", TechnologyCategory.AI_RUNTIME),
    (re.compile(r"\bvllm\b", re.I), "vLLM", TechnologyCategory.AI_RUNTIME),
    (
        re.compile(r"text-generation-inference|\btgi\b", re.I),
        "Text Generation Inference",
        TechnologyCategory.AI_RUNTIME,
    ),
    (re.compile(r"triton", re.I), "Triton Inference Server", TechnologyCategory.AI_RUNTIME),
    (
        re.compile(r"llama[\.\- ]?cpp|llama-server", re.I),
        "llama.cpp",
        TechnologyCategory.AI_RUNTIME,
    ),
    (re.compile(r"litellm", re.I), "LiteLLM", TechnologyCategory.AI_PROXY),
    (re.compile(r"lm ?studio", re.I), "LM Studio", TechnologyCategory.AI_RUNTIME),
)


# ── AI endpoint interface-type classifier ────────────────────────────────
#
# Stamps a crawled URL with the AI interface it exposes so the orchestrator
# routes a hit into the matching ``llm-redteam`` sub-skill. Ordered: the first
# pattern that matches the path wins; ``"non-llm"`` is the default.
_ENDPOINT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/v1/chat/completions|/v1/messages|/v1/responses|/api/chat$"), "chat"),
    (re.compile(r"/chat/completions"), "chat"),  # Azure /openai/deployments/<d>/chat/completions
    (re.compile(r"/v1/completions|/api/generate$|/invocations$"), "completion"),
    (re.compile(r"/v1/embeddings|/api/embed(?:dings)?$"), "embedding"),
    (re.compile(r"/v1/rerank|/rerank$"), "rerank"),
    (re.compile(r"/v1/models$|/api/tags$|/v1/models/"), "models"),
    (re.compile(r"/(?:predict|infer)$|/v2/models/.+/infer"), "inference"),
    (re.compile(r"/sse$|/events$|/stream$"), "sse"),
    (re.compile(r"/\.well-known/mcp|/mcp(?:/|$)"), "mcp"),
    (re.compile(r"/graphql"), "graphql"),
)


def _normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {str(k).strip().lower(): str(v) for k, v in headers.items()}


def match_ai_headers(headers: Mapping[str, str] | None) -> list[TechMatch]:
    """Match AI signatures over a response-header map (high confidence).

    Returns one :class:`TechMatch` per distinct product detected, deduped by
    ``(name, category)`` so a runtime that sets several namespaced headers
    (and also names itself in ``Server``) yields a single result.
    """
    norm = _normalize_headers(headers)
    if not norm:
        return []

    seen: set[tuple[str, str]] = set()
    matches: list[TechMatch] = []

    def _add(name: str, category: TechnologyCategory, detected_by: str) -> None:
        marker = (name, category.value)
        if marker in seen:
            return
        seen.add(marker)
        matches.append(TechMatch(name, category, _HIGH, detected_by))

    for header_name in norm:
        for pattern, name, category in _HEADER_NAME_PATTERNS:
            if pattern.match(header_name):
                _add(name, category, "httpx-ai-header")
                break

    server = norm.get("server", "").lower()
    if server:
        for pattern, name, category in _SERVER_VALUE_PATTERNS:
            if pattern.search(server):
                _add(name, category, "httpx-ai-header")

    return matches


def lookup_ai_port(port: int) -> TechMatch | None:
    """Resolve a port to a catalogued AI technology, or ``None``.

    The returned match's ``confidence`` is the caller's two-tier gate: ``"high"``
    vendor ports may MERGE a node alone; ``"low"`` generic ports should wait for
    HTTP corroboration.
    """
    return AI_PORTS.get(port)


def match_ai_title(title: str | None) -> TechMatch | None:
    """Match an AI product from a page title (low confidence, corroborating)."""
    if not title:
        return None
    for pattern, name, category in _TITLE_PATTERNS:
        if pattern.search(title):
            return TechMatch(name, category, _LOW, "title-regex")
    return None


def match_ai_banner(
    product: str | None,
    version: str | None = None,
    extrainfo: str | None = None,
) -> TechMatch | None:
    """Match an AI runtime from an ``nmap -sV`` banner (low confidence).

    Joins the service-element ``product``/``version``/``extrainfo`` fields and
    runs the banner catalog; the matched product's ``version`` (when nmap
    captured one) is carried onto the result.
    """
    banner = " ".join(p for p in (product, version, extrainfo) if p).strip()
    if not banner:
        return None
    for pattern, name, category in _BANNER_PATTERNS:
        if pattern.search(banner):
            return TechMatch(name, category, _LOW, "nmap-banner", version=version or None)
    return None


def classify_ai_endpoint(path: str) -> str:
    """Classify a URL path into an AI interface type.

    Returns one of ``chat`` / ``completion`` / ``embedding`` / ``rerank`` /
    ``models`` / ``inference`` / ``sse`` / ``mcp`` / ``graphql``, or
    ``non-llm`` when the path matches no AI interface.
    """
    if not path:
        return "non-llm"
    candidate = path.rstrip("/") or path
    for pattern, interface in _ENDPOINT_PATTERNS:
        if pattern.search(candidate):
            return interface
    return "non-llm"


def dedup_matches(matches: Iterable[TechMatch]) -> list[TechMatch]:
    """Collapse matches resolving to the same ``Technology`` node.

    Two channels (a high-confidence port and a low-confidence banner) can name
    the same product. Keep the highest-confidence match per
    ``technology_key`` so a corroborating guess never downgrades a routable
    detection, while still carrying a version captured by either channel.
    Insertion order is preserved.
    """
    rank = {_HIGH: 1, _LOW: 0}
    best: dict[str, TechMatch] = {}
    order: list[str] = []
    for match in matches:
        key = technology_key(match.category, match.name)
        current = best.get(key)
        if current is None:
            best[key] = match
            order.append(key)
            continue
        winner = match if rank[match.confidence] > rank[current.confidence] else current
        version = winner.version or current.version or match.version
        best[key] = winner if winner.version == version else replace(winner, version=version)
    return [best[key] for key in order]
