#!/bin/bash
# Make /workspace world-accessible so the host user can read findings,
# reports, and engagement files without sudo.
# Security boundary is the container itself, not file permissions.
chmod -R 777 /workspace 2>/dev/null || true
# Ensure all NEW files are also world-readable/writable
umask 0000

# ── Commercial RE backend (opt-in at runtime) ──
# When the backend installation is mounted at DECEPTICON_HEXBE_PATH and the
# library wheel hasn't been installed yet, install it now from the mounted
# volume. This avoids needing a named build context in the Dockerfile.
if [ -n "${DECEPTICON_HEXBE_PATH:-}" ] && \
   [ -d "${DECEPTICON_HEXBE_PATH}/idalib/python" ] && \
   ! python3 -c "import idapro" 2>/dev/null; then
    pip install --no-cache-dir --break-system-packages -q \
        "${DECEPTICON_HEXBE_PATH}"/idalib/python/idapro*.whl 2>/dev/null && \
    python3 "${DECEPTICON_HEXBE_PATH}/idalib/python/py-activate-idalib.py" \
        -d "${DECEPTICON_HEXBE_PATH}" 2>/dev/null && \
    echo "[hexbe] Commercial RE backend library activated" || true
fi

# HTTP daemon mode (default ON). The container runs the FastAPI sandbox
# server on ``localhost:9999`` for every deployment target — dev,
# local-docker, GCE Spot VMs, and Cloud Run multi-container. The agent
# process (HTTPSandbox in decepticon/backends/http_sandbox.py) talks to
# it over HTTP. The previous default of ``0`` (tail -f keep-alive) is
# kept as an opt-out for legacy ``docker exec`` workflows: set
# ``SANDBOX_DAEMON=0`` to disable the daemon.
if [ "${SANDBOX_DAEMON:-1}" = "1" ]; then
    exec python3 -m decepticon.sandbox_server
fi

exec "$@"
