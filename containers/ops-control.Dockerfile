# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────
# ops-control — the single lifecycle surface for compose-defined
# domain services.  See ADR-0006.
#
# This is the ONLY container in the management plane that bind-mounts
# the host's Docker socket.  Its HTTP API exposes an allowlisted
# subset of `docker compose --profile <name> up/stop -d` and nothing
# else; no raw `docker run`, no image pull, no volume / network edits.
# ─────────────────────────────────────────────────────────────────────

FROM alpine:3.20

# docker-cli ships /usr/bin/docker; docker-cli-compose drops the
# compose v2 plugin into /usr/libexec/docker/cli-plugins/.  Both are
# pinned by the apk index of the chosen Alpine release for
# reproducibility; we explicitly do not chase :latest.
RUN apk add --no-cache \
        python3 \
        py3-pip \
        docker-cli \
        docker-cli-compose \
        curl \
        tini \
    && python3 -m pip install --break-system-packages --no-cache-dir --upgrade pip

WORKDIR /app

COPY containers/ops-control/requirements.txt /app/requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r /app/requirements.txt

COPY containers/ops-control/main.py /app/main.py

# Default config; overridden by docker-compose.yml at runtime.
ENV OPS_PROFILE_ALLOWLIST="" \
    OPS_COMPOSE_PROJECT="decepticon" \
    OPS_COMPOSE_FILE="/host/docker-compose.yml" \
    OPS_DOCKER_BIN="docker"

EXPOSE 8090

# tini handles SIGTERM cleanly so the compose stop on the host doesn't
# leave a 10s zombie wait per restart.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

HEALTHCHECK --interval=10s --timeout=3s --retries=6 --start-period=10s \
    CMD curl -fsS http://127.0.0.1:8090/v1/health || exit 1
