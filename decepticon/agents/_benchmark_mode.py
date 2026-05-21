import os


def benchmark_skill_sources() -> list[str]:
    """Return extra skill source paths when BENCHMARK_MODE is active."""
    if os.environ.get("BENCHMARK_MODE", "").strip().lower() not in {"", "0", "false", "no", "off"}:
        return ["/skills/benchmark/"]
    return []
