FROM python:3.13-slim

# Install Docker CLI (needed to exec into sandbox container)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv

# Copy project files (uv.lock included so the install is reproducible)
COPY pyproject.toml langgraph.json README.md uv.lock ./
COPY decepticon/ decepticon/

# Stamp the package version from the git tag at build time. Source-tree
# pyproject.toml carries a "0.0.0" sentinel; release.yml passes the real
# version via --build-arg so the installed package metadata matches the tag.
ARG VERSION=0.0.0
RUN sed -i 's/^version = "[^"]*"/version = "'"$VERSION"'"/' pyproject.toml

# Install Python dependencies. uv export --frozen derives the exact set from
# uv.lock (ignoring pyproject.toml's loose constraints), so the container
# always gets the same versions that were locked at commit time. The editable
# install uses --no-deps because all dependencies are already installed; source
# changes via docker compose watch are still reflected without reinstall.
#
# ``--extra neo4j`` is required here: neo4j is an optional extra so the PyPI SDK
# (``pip install decepticon``) stays lean, but the full langgraph image runs the
# Neo4j knowledge-graph feature and needs the driver. Without it the KG health
# check fails (no ``neo4j`` module in the container).
RUN uv export --no-dev --extra neo4j --frozen -o /tmp/requirements.txt && \
    uv pip install --system -r /tmp/requirements.txt && \
    uv pip install --system -e "." --no-deps

EXPOSE 2024

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:2024/ok >/dev/null 2>&1 || exit 1

# --n-jobs-per-worker explicitly set to 10 to match the CLI help's stated
# default. langgraph_api/cli.py:run_server falls back to N_JOBS_PER_WORKER=1
# when the flag is omitted (despite `--help` saying "Default: 10"), which
# caps the in-memory queue at 1 concurrent run and serialises any batch
# bigger than 1. Without this override our benchmark batches with
# `--parallel 5` queue 4 runs behind a single worker.
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser", "--n-jobs-per-worker", "10"]
