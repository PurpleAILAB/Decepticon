#!/bin/sh
# Entrypoint for decepticon-web container.
#
# Process model:
#   PID 1  — this script (trap handler, keeps container alive)
#   child  — terminal server (ws://0.0.0.0:3003) — long-lived, survives Next.js restarts
#   child  — Next.js standalone server (:3000) — restartable via SIGUSR1
#
# SIGUSR1 handler: kills and restarts only the Next.js process. The terminal
# server (and any PTY sessions it manages) stays alive. This is what
# scripts/web-hotswap.sh sends after injecting new .next/ files — zero
# WebSocket disconnection for the operator.
#
# SIGTERM handler: clean shutdown of both processes (docker stop).

set -e
cd /app/clients/web

NEXT_PID=""
TERM_PID=""

# ── Handlers ──────────────────────────────────────────────────────

restart_next() {
  echo "[entrypoint] SIGUSR1 received — restarting Next.js..."
  if [ -n "$NEXT_PID" ] && kill -0 "$NEXT_PID" 2>/dev/null; then
    kill "$NEXT_PID" 2>/dev/null
    wait "$NEXT_PID" 2>/dev/null || true
  fi
  echo "[entrypoint] Starting Next.js..."
  node server.js &
  NEXT_PID=$!
  echo "[entrypoint] Next.js restarted (PID $NEXT_PID)"
}

shutdown() {
  echo "[entrypoint] SIGTERM received — shutting down..."
  [ -n "$NEXT_PID" ] && kill "$NEXT_PID" 2>/dev/null
  [ -n "$TERM_PID" ] && kill "$TERM_PID" 2>/dev/null
  wait 2>/dev/null
  exit 0
}

trap restart_next USR1
trap shutdown TERM INT

# ── Startup ───────────────────────────────────────────────────────

echo "[entrypoint] Running DB migrations..."
npx --yes prisma migrate deploy 2>&1 | grep -v 'npm notice'

echo "[entrypoint] Starting terminal server (ws://0.0.0.0:${TERMINAL_PORT:-3003})..."
npx --yes tsx server/terminal-server.ts &
TERM_PID=$!

echo "[entrypoint] Starting Next.js (standalone)..."
node server.js &
NEXT_PID=$!

echo "[entrypoint] Ready (terminal=$TERM_PID, next=$NEXT_PID)"

# Wait for either child to exit. If Next.js crashes, restart it.
# If the terminal server crashes, exit (Docker will restart the container).
while true; do
  # `wait -n` waits for any one child. Not available in dash/busybox sh,
  # so we poll instead.
  if ! kill -0 "$TERM_PID" 2>/dev/null; then
    echo "[entrypoint] Terminal server died — exiting"
    [ -n "$NEXT_PID" ] && kill "$NEXT_PID" 2>/dev/null
    exit 1
  fi
  if ! kill -0 "$NEXT_PID" 2>/dev/null; then
    echo "[entrypoint] Next.js died — restarting..."
    sleep 1
    node server.js &
    NEXT_PID=$!
    echo "[entrypoint] Next.js restarted (PID $NEXT_PID)"
  fi
  sleep 2
done
