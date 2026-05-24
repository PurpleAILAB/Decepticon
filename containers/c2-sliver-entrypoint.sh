#!/bin/bash
# Entrypoint for the Sliver C2 server container.
# Runs as root to fix volume permissions, then drops to sliver user.
# 1. Fixes ownership on mounted volumes
# 2. Starts sliver-server in daemon mode (as sliver user)
# 3. Auto-generates operator config on first run → shared /workspace volume
set -e

CONFIG_DIR="/workspace/.sliver-configs"
CONFIG_FILE="${CONFIG_DIR}/decepticon.cfg"

# ── Fix volume permissions (runs as root) ──────────────────────────
# Docker named volumes are created as root. Ensure sliver user can write.
chown -R sliver:users /home/sliver/.sliver
mkdir -p "$CONFIG_DIR"
chown sliver:users "$CONFIG_DIR"

# ── Everything below runs as sliver user ───────────────────────────
run_as_sliver() {
  runuser -u sliver -- "$@"
}

# Start daemon in background
run_as_sliver sliver-server daemon &
DAEMON_PID=$!

# Wait for daemon to finish initialization (cert generation, DB setup on first run)
echo "[c2-sliver] Waiting for daemon to initialize..."
for _ in $(seq 1 24); do
  if run_as_sliver sliver-server operator --name _probe --lhost localhost --permissions all --save /dev/null 2>/dev/null; then
    echo "[c2-sliver] Daemon ready."
    break
  fi
  sleep 5
done

# Generate operator config if not already present
if [ ! -f "$CONFIG_FILE" ]; then
  if run_as_sliver sliver-server operator --name decepticon --lhost c2-sliver --permissions all --save "$CONFIG_FILE"; then
    echo "[c2-sliver] Operator config saved → ${CONFIG_FILE}"
  else
    echo "[c2-sliver] WARNING: Failed to generate operator config"
  fi
else
  echo "[c2-sliver] Operator config already exists → ${CONFIG_FILE}"
fi

# Keep running — wait on daemon process
wait $DAEMON_PID
