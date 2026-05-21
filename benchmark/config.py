from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def _default_langgraph_url() -> str:
    """Resolve LangGraph URL: explicit BENCHMARK_LANGGRAPH_URL > derive from LANGGRAPH_PORT > default."""
    url = os.environ.get("BENCHMARK_LANGGRAPH_URL")
    if url:
        return url
    port = os.environ.get("LANGGRAPH_PORT", "2024")
    return f"http://localhost:{port}"


def _default_litellm_url() -> str:
    """Resolve LiteLLM URL: explicit BENCHMARK_LITELLM_URL > derive from LITELLM_PORT > default."""
    url = os.environ.get("BENCHMARK_LITELLM_URL")
    if url:
        return url
    port = os.environ.get("LITELLM_PORT", "4000")
    return f"http://localhost:{port}"


class BenchmarkConfig(BaseModel):
    """Global benchmark runner configuration."""

    timeout: int = Field(default=1800, description="Timeout in seconds (30 min)")
    batch_size: int = 10
    results_dir: Path = Path("benchmark/results")
    langgraph_url: str = Field(default_factory=_default_langgraph_url)
    litellm_url: str = Field(default_factory=_default_litellm_url)
    max_iterations: int = 10
    docker_network: str = "sandbox-net"
    cleanup_workspaces: bool = True
    provider: str = "xbow"
    # ExploitBench provider knobs. ``exploitbench_config_path`` points at
    # an ExploitBench-style YAML (see ``benchmark/configs/exploitbench-*.yaml``);
    # ``exploitbench_bridge_runtime`` selects the stdio→TCP bridge binary
    # (``mcp-proxy`` default, ``socat`` fallback for hosts without Node).
    exploitbench_config_path: Path | None = None
    exploitbench_bridge_runtime: str = "mcp-proxy"
    # MHBench provider only: absolute or repo-relative path to the upstream
    # MHBench ``config.json`` carrying OpenStack credentials, external_ip,
    # and Elastic/C2 settings. Required when ``provider == "mhbench"``.
    mhbench_config_path: Path | None = None
