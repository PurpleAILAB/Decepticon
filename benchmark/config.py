from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class BenchmarkConfig(BaseModel):
    """Global benchmark runner configuration."""

    timeout: int = Field(default=1800, description="Timeout in seconds (30 min)")
    batch_size: int = 10
    results_dir: Path = Path("benchmark/results")
    langgraph_url: str = "http://localhost:2024"
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
