# syntax=docker/dockerfile:1
# Pin digest for reproducible builds and stable GHA cache layers.
# To update: docker pull kalilinux/kali-rolling:latest && docker inspect --format='{{index .RepoDigests 0}}' kalilinux/kali-rolling:latest
FROM kalilinux/kali-rolling@sha256:a3849f99f9f187122de4822341c49e55d250a771f2dbc5cfd56a146017e0e6ae

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
        # ── JavaScript runtime (JSFuck payload encoding/validation) ──
        nodejs \
        npm \
        # ── C2 client (connects to the separate c2-sliver server container) ──
        sliver

# Configure tmux: 50K line scrollback buffer to prevent output truncation
RUN echo "set-option -g history-limit 50000" > /root/.tmux.conf

# Working directory for the agent's virtual filesystem.
# Runs as root — security boundary is the container, not the user.
# Root access is required for raw sockets (nmap SYN scans), packet capture,
# and unrestricted filesystem access during red team operations.
WORKDIR /workspace

# Skill library — baked at /skills/ so every agent (recon, exploit, analyst,
# detector, soundwave, ...) can resolve `/skills/<category>/<skill>/SKILL.md`
# via the load_skill tool without depending on a host-side bind mount. The
# OSS install path doesn't ship skills/ to disk, so without this COPY the
# sandbox container would expose an empty /skills/ and every agent prompt
# referencing a skill file would fail.
#
# Devs iterating on skill content override this at runtime via the
# `./skills:/skills:ro` bind mount in docker-compose.override.yml — that
# file is committed but not downloaded by install.sh, so OSS users
# automatically get the baked-in skills and devs get hot-edits.
#
# Placed after the heavy apt-install layer so a skill-only edit invalidates
# only this thin trailing layer.
COPY skills/ /skills/

# Entrypoint: chmod 777 /workspace so host user can access files without sudo.
# Security boundary is the container, not file permissions.
COPY containers/sandbox-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

# Healthcheck: verify the sandbox is alive and tmux is usable.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD tmux -V >/dev/null 2>&1 || exit 1

# Keep the container alive so the backend can 'docker exec' into it
CMD ["tail", "-f", "/dev/null"]
