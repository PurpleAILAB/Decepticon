# syntax=docker/dockerfile:1
# Sliver C2 Server — modular team server container.
# Runs sliver-server in daemon mode (gRPC listener for operator clients).
# Starts by default with: docker compose up -d
#
# Pin digest for reproducible builds (same base as sandbox).
FROM kalilinux/kali-rolling@sha256:a3849f99f9f187122de4822341c49e55d250a771f2dbc5cfd56a146017e0e6ae

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
RUN chmod +x /usr/local/bin/entrypoint.sh

# Listener ports: HTTPS(443), DNS(53), mTLS(8888), gRPC operator(31337)
EXPOSE 443 53 8888 31337

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
