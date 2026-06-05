"""Unit tests for the AI-surface classifiers (ADR-0007).

``technology_for_port`` / ``technology_for_path`` turn a scanned port or a
probed URL path into a typed ``Technology`` node + a ``RUNS`` edge the
owning service carries, so the ``llm-redteam`` plugin can find an exposed
AI runtime recon already saw.
"""

from __future__ import annotations

from decepticon.middleware.kg_internal.ai_surface import (
    DETECTED_BY_BANNER,
    DETECTED_BY_HEADER,
    DETECTED_BY_PATH,
    DETECTED_BY_PORT,
    DETECTED_BY_TITLE,
    technology_for_banner,
    technology_for_headers,
    technology_for_path,
    technology_for_port,
    technology_for_title,
)
from decepticon_core.types.kg import TechnologyCategory, technology_key


def test_dedicated_port_is_confident_technology() -> None:
    result = technology_for_port(11434, "nmap")
    assert result is not None
    node, edge = result
    assert node["kind"] == "Technology"
    assert (
        node["key"]
        == technology_key(TechnologyCategory.AI_RUNTIME, "ollama")
        == "ai-runtime:ollama"
    )
    assert node["props"]["detected_by"] == DETECTED_BY_PORT
    # Dedicated ports are NOT guesses — they can anchor an exploit chain.
    assert "guess" not in node["props"]
    assert edge == {
        "to_key": "ai-runtime:ollama",
        "kind": "RUNS",
        "props": {"detected_by": DETECTED_BY_PORT},
    }


def test_shared_port_is_corroborating_guess_only() -> None:
    result = technology_for_port(7860, "nmap")
    assert result is not None
    node, _edge = result
    # Shared ports are flagged guess=True so they cannot drive a chain alone.
    assert node["props"]["guess"] is True
    assert node["key"] == "ai-framework:gradio"


def test_unknown_port_is_not_classified() -> None:
    assert technology_for_port(22, "nmap") is None
    assert technology_for_port(443, "nmap") is None


def test_edge_to_key_matches_node_key() -> None:
    node, edge = technology_for_port(11434, "nmap")  # type: ignore[misc]
    assert edge["to_key"] == node["key"]


def test_ollama_native_path_is_classified() -> None:
    node, edge = technology_for_path("/api/tags", 200, "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-runtime:ollama"
    assert node["props"]["detected_by"] == DETECTED_BY_PATH
    assert edge["to_key"] == "ai-runtime:ollama"


def test_openai_compatible_path_is_classified() -> None:
    node, _ = technology_for_path("/v1/chat/completions", 405, "httpx")  # type: ignore[misc]
    # 405 (GET on a POST-only route) still proves the endpoint exists.
    assert node["key"] == "ai-runtime:openai-compatible-api"


def test_path_prefix_match_for_subrouted_api() -> None:
    node, _ = technology_for_path("/sdapi/v1/txt2img", 200, "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-framework:automatic1111"


def test_path_with_trailing_slash_and_query_normalizes() -> None:
    assert technology_for_path("/api/tags/?pretty=1", 200, "httpx") is not None


def test_404_path_is_not_classified() -> None:
    # The route was probed and is absent — not a detection.
    assert technology_for_path("/v1/chat/completions", 404, "httpx") is None


def test_non_ai_path_is_not_classified() -> None:
    assert technology_for_path("/", 200, "httpx") is None
    assert technology_for_path("/admin/login", 200, "httpx") is None


def test_ai_ui_title_is_corroborating_guess() -> None:
    node, edge = technology_for_title("ComfyUI", "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-framework:comfyui"
    assert node["props"]["detected_by"] == DETECTED_BY_TITLE
    # A title is operator-controllable -> always guess-only (ADR-0007).
    assert node["props"]["guess"] is True
    assert edge["to_key"] == "ai-framework:comfyui"


def test_ai_ui_title_matches_substring_case_insensitively() -> None:
    node, _ = technology_for_title("My Open WebUI - chat", "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-framework:open-webui"


def test_empty_or_unknown_title_is_not_classified() -> None:
    assert technology_for_title(None, "httpx") is None
    assert technology_for_title("", "httpx") is None
    assert technology_for_title("Welcome to nginx!", "httpx") is None


def test_banner_naming_runtime_is_confident() -> None:
    node, edge = technology_for_banner("Ollama 0.1.32", "nmap")  # type: ignore[misc]
    assert node["key"] == "ai-runtime:ollama"
    assert node["props"]["detected_by"] == DETECTED_BY_BANNER
    # A banner naming the product is strong evidence — not a guess.
    assert "guess" not in node["props"]
    assert edge["to_key"] == "ai-runtime:ollama"


def test_banner_proxy_category() -> None:
    node, _ = technology_for_banner("LiteLLM proxy", "nmap")  # type: ignore[misc]
    assert node["key"] == "ai-proxy:litellm"


def test_banner_matches_on_token_boundary_only() -> None:
    # "ollama" must not fire inside an unrelated token.
    assert technology_for_banner("follamatic 1.0", "nmap") is None
    # but punctuation-delimited is a real hit.
    assert technology_for_banner("server: ollama/0.1", "nmap") is not None


def test_empty_or_unmatched_banner_is_not_classified() -> None:
    assert technology_for_banner(None, "nmap") is None
    assert technology_for_banner("", "nmap") is None
    assert technology_for_banner("nginx 1.18", "nmap") is None


def test_litellm_proxy_header_is_corroborating_guess() -> None:
    headers = {
        "server": "uvicorn",
        "x_litellm_version": "1.40.0",
        "content_type": "application/json",
    }
    node, edge = technology_for_headers(headers, "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-proxy:litellm"
    assert node["props"]["detected_by"] == DETECTED_BY_HEADER
    # A header is proxy-injectable -> guess-only (ADR-0007).
    assert node["props"]["guess"] is True
    assert edge["to_key"] == "ai-proxy:litellm"


def test_tgi_compute_header_is_classified() -> None:
    node, _ = technology_for_headers({"x_compute_type": "gpu", "x_prompt_tokens": "12"}, "httpx")  # type: ignore[misc]
    assert node["key"] == "ai-runtime:text-generation-inference"


def test_headers_without_ai_marker_are_not_classified() -> None:
    assert technology_for_headers({"server": "nginx", "content_type": "text/html"}, "httpx") is None


def test_empty_or_non_dict_headers_are_not_classified() -> None:
    assert technology_for_headers(None, "httpx") is None
    assert technology_for_headers({}, "httpx") is None
    assert technology_for_headers("server: nginx", "httpx") is None  # type: ignore[arg-type]
