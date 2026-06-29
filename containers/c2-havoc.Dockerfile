# syntax=docker/dockerfile:1
# Havoc C2 Teamserver — modular team server container.
# Runs the Havoc teamserver in daemon mode with gRPC operator port (40056).
# Starts by default with: docker compose --profile c2-havoc up -d
#
# Pin digest for reproducible builds (same base as sandbox).
FROM kalilinux/kali-rolling@sha256:ab7f9873e9d976d62f59e172350604dd980339f567bfb2eaa5c2bdfaa2dc42b7

# Fix SSL: the pinned image may have expired CA certs, so bootstrap
# ca-certificates over HTTP first, then switch back to HTTPS.
#
# BuildKit cache mounts mirror the sandbox image — see that Dockerfile
# for the rationale. Cache id is distinct so c2-havoc and sandbox
# don't share an apt-lists race.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked,id=c2-havoc-apt-cache \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked,id=c2-havoc-apt-lists \
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
    apt-get install -y --no-install-recommends \
        git \
        golang \
        mingw-w64 \
        nasm \
        python3 \
        make \
        cmake \
        gcc \
        g++

# Build Havoc teamserver from source.
# Client is not needed — operators interact via the Decepticon agent layer.
ARG HAVOC_VERSION=main
RUN git clone --depth 1 --branch "$HAVOC_VERSION" \
        https://github.com/HavocFramework/Havoc /opt/havoc-src && \
    cd /opt/havoc-src && \
    make ts-build && \
    cp havoc /usr/local/bin/havoc-server && \
    rm -rf /opt/havoc-src/.git

# Non-root operator user (UID 1000 — consistent with sandbox container)
# Pre-create .havoc dir so Docker volume inherits correct ownership on first mount.
RUN useradd -m -s /bin/bash -u 1000 -g users havoc && \
    mkdir -p /opt/havoc /home/havoc/.havoc /opt/havoc/data && \
    chown -R havoc:users /opt/havoc /home/havoc/.havoc

WORKDIR /opt/havoc

# Copy default profile template into the image
COPY containers/c2-havoc-entrypoint.sh /usr/local/bin/entrypoint.sh
# Strip any CR so the image builds correctly even from a Windows host
# whose checkout introduced CRLF line endings.
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Listener ports: HTTPS(443), HTTP(80), operator/gRPC(40056)
EXPOSE 443 80 40056

# Runs as root by design. Havoc binds privileged ports (80/443), writes
# to /opt/havoc via the entrypoint shim (chown of the operator-key
# volume), and needs raw socket access for the HTTP/S listeners.
# Hardening happens at the docker-compose layer (read-only rootfs,
# tmpfs, ``cap-drop ALL`` + ``cap-add NET_BIND_SERVICE`` only).
# Explicit USER directive silences semgrep
# ``missing-user-entrypoint`` while documenting the disposition.
USER root

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
