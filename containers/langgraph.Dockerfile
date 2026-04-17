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

# Copy project files
COPY pyproject.toml langgraph.json README.md ./
COPY decepticon/ decepticon/
COPY skills/ skills/

# Install Python dependencies (editable — synced source changes via docker compose watch
# are immediately reflected without reinstall)
RUN uv pip install --system -e "." && \
    uv pip install --system "langgraph-cli[inmem]>=0.2.0"

EXPOSE 2024

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:2024/ok >/dev/null 2>&1 || exit 1

CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser"]
