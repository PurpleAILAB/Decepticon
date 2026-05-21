# syntax=docker/dockerfile:1
# Pin digest for reproducible builds and stable GHA cache layers.
# To update: docker pull kalilinux/kali-rolling:latest && docker inspect --format='{{index .RepoDigests 0}}' kalilinux/kali-rolling:latest
FROM kalilinux/kali-rolling@sha256:ab7f9873e9d976d62f59e172350604dd980339f567bfb2eaa5c2bdfaa2dc42b7

# Consolidated package install — one RUN layer to maximize cache hits
# and minimize image size. Kali apt sandbox disabled so it doesn't fail
# trying to drop privileges to the _apt user.
#
# BuildKit cache mounts on /var/cache/apt and /var/lib/apt/lists keep
# .deb downloads + the apt index cached across builds (local rebuilds,
# GHA cache-from=type=gha). The Debian-style /etc/apt/apt.conf.d/docker-clean
# auto-purge is disabled inline so cached .debs survive between RUN steps,
# and the trailing apt-get clean is gone — the cache mount paths aren't
# part of the image layer, so leaving them populated costs zero image MB.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked,id=sandbox-apt-cache \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=sandbox-apt-lists \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo "APT::Sandbox::User \"root\";" > /etc/apt/apt.conf.d/10sandbox && \
    sed -i 's|https://|http://|g' /etc/apt/sources.list* 2>/dev/null; \
    find /etc/apt/sources.list.d/ -name '*.sources' -exec sed -i 's|https://|http://|g' {} + 2>/dev/null; \
    apt-get update && \
    apt-get install -y --no-install-recommends --no-install-suggests \
        ca-certificates && \
    update-ca-certificates && \
    sed -i 's|http://|https://|g' /etc/apt/sources.list* 2>/dev/null; \
    find /etc/apt/sources.list.d/ -name '*.sources' -exec sed -i 's|http://|https://|g' {} + 2>/dev/null; \
    apt-get update && \
    apt-get install -y --no-install-recommends --no-install-suggests \
        # ── Core runtime ──
        curl \
        wget \
        python3 \
        python3-pip \
        tmux \
        # ── Recon ──
        nmap \
        dnsutils \
        whois \
        netcat-openbsd \
        iputils-ping \
        subfinder \
        # ── Exploit & post-exploitation ──
        hydra \
        sqlmap \
        nikto \
        smbclient \
        exploitdb \
        dirb \
        gobuster \
        # SSH client + sshpass for lateral movement / multi-host scenarios
        # (e.g., MHBench OpenStack topologies — attacker pivots through a
        # jump host via ProxyJump to reach internal ring hosts).
        openssh-client \
        sshpass \
        # ── JavaScript runtime (JSFuck payload encoding/validation) ──
        nodejs \
        npm \
        # ── C2 client (connects to the separate c2-sliver server container) ──
        sliver

# Configure tmux: 50K line scrollback buffer to prevent output truncation
RUN echo "set-option -g history-limit 50000" > /root/.tmux.conf

# Optional HTTP sandbox daemon — see decepticon/sandbox_server/.
#
# The daemon is OFF by default. The existing dev / local-docker / GCE
# Spot deployments use this image as before (host docker daemon
# `docker exec`s into the container; entrypoint just tails forever).
# When `SANDBOX_DAEMON=1` is set at runtime — Cloud Run multi-container
# deploys do this — the entrypoint replaces the tail loop with the
# FastAPI server, and the agent container talks to it over HTTP
# instead of `docker exec`.
#
# Only `fastapi` + `uvicorn` + `deepagents` are pulled in here; the
# heavier decepticon agent / LLM / langgraph SDKs are deliberately
# left out so the sandbox image doesn't bloat for the >95% of users
# who never enable the daemon.
RUN pip3 install --break-system-packages --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.30.0" \
    "deepagents>=0.5.0"

# Ship only the modules the daemon actually imports:
#   - decepticon/__init__.py     — package marker (light-weight, just reads __version__)
#   - decepticon/sandbox_kernel/ — shared sandbox primitives: TmuxSessionManager,
#                                  BackgroundJobTracker, SandboxBase, and DaemonSandbox.
#                                  The daemon instantiates `DaemonSandbox` (exec_prefix=[],
#                                  pathlib upload/download) — no `docker exec`, no
#                                  agent-side transport, so the sandbox image stays
#                                  free of the `backends/` package on purpose.
#   - decepticon/sandbox_server/ — the FastAPI app + uvicorn entry point.
# `backends/` (DockerSandbox + HTTPSandbox + factory) is deliberately
# absent — that's agent-side code, lives in the langgraph image. Other
# subtrees (agents / llm / middleware / tools / core) are left out too
# so the sandbox image doesn't bloat for the >95% of users who never
# enable the daemon and so the dependency surface stays minimal.
# Phase 0 of the core/framework/sdk split relocated the framework
# source tree to packages/decepticon/decepticon/. The sandbox
# image stays an exec-only daemon — it only needs ``sandbox_kernel``
# + ``sandbox_server`` + the bare ``__init__.py`` so they can be
# imported as a Python package under PYTHONPATH=/opt.
COPY packages/decepticon/decepticon/__init__.py /opt/decepticon/__init__.py
COPY packages/decepticon/decepticon/sandbox_kernel /opt/decepticon/sandbox_kernel
COPY packages/decepticon/decepticon/sandbox_server /opt/decepticon/sandbox_server
ENV PYTHONPATH=/opt

# Skip the framework boot path on this image — the sandbox container
# ships only sandbox_kernel + sandbox_server, NOT decepticon-core or
# the rest of the framework. ``decepticon/__init__.py`` checks this
# env var and short-circuits the RoleRegistry + PluginRegistry setup
# so the sandbox process can ``python -m decepticon.sandbox_server``
# without importing decepticon-core (which isn't installed here).
ENV DECEPTICON_SKIP_BOOT=1

# Working directory for the agent's virtual filesystem.
# Runs as root — security boundary is the container, not the user.
# Root access is required for raw sockets (nmap SYN scans), packet capture,
# and unrestricted filesystem access during red team operations.
WORKDIR /workspace

# Skills are NO LONGER baked into the sandbox image. They live in the
# langgraph container (see ``containers/langgraph.Dockerfile``), where
# they are read in-process by ``FilesystemBackend`` via the
# ``CompositeBackend`` route declared in
# ``decepticon/backends/__init__.py:make_agent_backend``. Skills are
# read-only knowledge — they don't need the sandbox's isolated
# execution environment, and avoiding the HTTP round-trip per skill
# read saves agent-init latency.

# Entrypoint: chmod 777 /workspace so host user can access files without sudo.
# Security boundary is the container, not file permissions.
COPY containers/sandbox-entrypoint.sh /entrypoint.sh
# Strip any CR so the image builds correctly even from a Windows host
# whose checkout introduced CRLF line endings.
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Healthcheck: verify the sandbox is alive and tmux is usable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD tmux -V >/dev/null 2>&1 || exit 1

# Keep the container alive so the backend can 'docker exec' into it
CMD ["tail", "-f", "/dev/null"]
