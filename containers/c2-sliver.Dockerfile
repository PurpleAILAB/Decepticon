# syntax=docker/dockerfile:1
# Sliver C2 Server — modular team server container.
# Runs sliver-server in daemon mode (gRPC listener for operator clients).
# Starts by default with: docker compose up -d
#
# Pin digest for reproducible builds (same base as sandbox).
FROM kalilinux/kali-rolling@sha256:ab7f9873e9d976d62f59e172350604dd980339f567bfb2eaa5c2bdfaa2dc42b7

# Fix SSL: the pinned image may have expired CA certs, so bootstrap
# ca-certificates over HTTP first, then switch back to HTTPS.
#
# BuildKit cache mounts mirror the sandbox image — see that Dockerfile
# for the rationale. Cache id is distinct so c2-sliver and sandbox
# don't share an apt-lists race.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked,id=c2-sliver-apt-cache \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=c2-sliver-apt-lists \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo "APT::Sandbox::User \"root\";" > /etc/apt/apt.conf.d/10sandbox && \
    sed -i 's|https://|http://|g' /etc/apt/sources.list* 2>/dev/null; \
    find /etc/apt/sources.list.d/ -name '*.sources' -exec sed -i 's|https://|http://|g' {} + 2>/dev/null; \
    apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    sed -i 's|http://|https://|g' /etc/apt/sources.list* 2>/dev/null; \
    find /etc/apt/sources.list.d/ -name '*.sources' -exec sed -i 's|http://|https://|g' {} + 2>/dev/null; \
    apt-get update && \
    apt-get install -y --no-install-recommends sliver

# Non-root operator user (UID 1000 — consistent with sandbox container)
# Pre-create .sliver dir so Docker volume inherits correct ownership on first mount.
RUN useradd -m -s /bin/bash -u 1000 -g users sliver && \
    mkdir -p /opt/sliver /home/sliver/.sliver && \
    chown -R sliver:users /opt/sliver /home/sliver/.sliver

WORKDIR /opt/sliver

# Entrypoint: fixes volume permissions, starts daemon, generates operator config
COPY containers/c2-sliver-entrypoint.sh /usr/local/bin/entrypoint.sh
# Strip any CR so the image builds correctly even from a Windows host
# whose checkout introduced CRLF line endings.
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Listener ports: HTTPS(443), DNS(53), mTLS(8888), gRPC operator(31337)
EXPOSE 443 53 8888 31337

# Runs as root by design. Sliver binds privileged ports (53/443), writes
# to /opt/sliver via the entrypoint shim (chown of the operator-key
# volume), and needs raw socket access for the DNS + mTLS listeners.
# Hardening happens at the docker-compose layer (read-only rootfs,
# tmpfs, ``cap-drop ALL`` + ``cap-add NET_BIND_SERVICE,NET_RAW`` only).
# Explicit USER directive silences semgrep
# ``missing-user-entrypoint`` while documenting the disposition.
USER root

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
