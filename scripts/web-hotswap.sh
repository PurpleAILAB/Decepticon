#!/usr/bin/env bash
# web-hotswap.sh — Hot-swap web dashboard into running container
#
# Builds Next.js on the host, injects the output directly into the
# running decepticon-web container, then signals PID 1 (the entrypoint
# supervisor) to restart only the Next.js process. The terminal server
# stays alive — zero WebSocket disconnections for the operator.
#
# Usage:
#   ./scripts/web-hotswap.sh              # build + inject + reload
#   ./scripts/web-hotswap.sh --skip-build # inject last build only
#   ./scripts/web-hotswap.sh --full       # build + inject + full container restart
#
# Speed:  ~25s with build, ~5s inject-only
# Safety: terminal connections preserved (unless --full)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$REPO_ROOT/clients/web"
CONTAINER="decepticon-web"
STANDALONE="$WEB_DIR/.next/standalone/clients/web"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
DIM='\033[2m'
NC='\033[0m'

info()  { echo -e "${GREEN}[hotswap]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hotswap]${NC} $*"; }
error() { echo -e "${RED}[hotswap]${NC} $*" >&2; }
dim()   { echo -e "${DIM}[hotswap]${NC} $*"; }

SKIP_BUILD=false
FULL_RESTART=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --full) FULL_RESTART=true ;;
  esac
done

# Pre-flight
if ! docker inspect "$CONTAINER" --format '{{.State.Running}}' 2>/dev/null | grep -q true; then
    error "$CONTAINER is not running"
    exit 1
fi

START=$(date +%s)

# ── Step 1: Build on host ─────────────────────────────────────────

if [[ "$SKIP_BUILD" == false ]]; then
    info "Building Next.js on host..."
    cd "$WEB_DIR"

    DATABASE_URL="${DATABASE_URL:-postgresql://decepticon:decepticon@localhost:5432/decepticon_web}" \
        npx prisma generate --no-hints 2>&1 | tail -1

    npm run build 2>&1 | tail -3

    BUILD_END=$(date +%s)
    info "Build completed in $((BUILD_END - START))s"
else
    info "Skipping build (--skip-build)"
    BUILD_END=$START
    if [[ ! -d "$STANDALONE" ]]; then
        error "No standalone build found — run without --skip-build first"
        exit 1
    fi
fi

# ── Step 2: Inject into container ─────────────────────────────────

info "Injecting into $CONTAINER..."

# Remove old .next (as root — container user is nextjs)
docker exec -u 0 "$CONTAINER" rm -rf /app/clients/web/.next

# Standalone .next via tar pipe
(cd "$STANDALONE" && tar cf - .next) | docker exec -u 0 -i "$CONTAINER" tar xf - -C /app/clients/web/

# Static assets (not in standalone)
(cd "$WEB_DIR" && tar cf - .next/static) | docker exec -u 0 -i "$CONTAINER" tar xf - -C /app/clients/web/

# Terminal server
docker cp "$WEB_DIR/server/terminal-server.ts" "$CONTAINER:/app/clients/web/server/terminal-server.ts"

# server.js (standalone entry point)
docker cp "$STANDALONE/server.js" "$CONTAINER:/app/clients/web/server.js"

# Fix ownership
docker exec -u 0 "$CONTAINER" chown -R nextjs:nodejs \
    /app/clients/web/.next \
    /app/clients/web/server.js \
    /app/clients/web/server/terminal-server.ts

INJECT_END=$(date +%s)
dim "Inject completed in $((INJECT_END - BUILD_END))s"

# ── Step 3: Reload ────────────────────────────────────────────────

if [[ "$FULL_RESTART" == true ]]; then
    info "Full container restart (--full)..."
    docker restart "$CONTAINER" >/dev/null 2>&1
    # Wait for healthy
    for _ in $(seq 1 30); do
        status=$(docker inspect "$CONTAINER" --format '{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
        [[ "$status" == "healthy" ]] && break
        sleep 1
    done
else
    # Signal PID 1 to restart only Next.js (terminal server stays alive)
    info "Reloading Next.js (terminal stays connected)..."
    docker kill --signal=USR1 "$CONTAINER" >/dev/null 2>&1 || {
        warn "SIGUSR1 failed — falling back to container restart"
        docker restart "$CONTAINER" >/dev/null 2>&1
    }
    # Wait for Next.js to come back up
    for _ in $(seq 1 20); do
        if curl -s -m 2 -o /dev/null http://localhost:3000/ 2>/dev/null; then
            break
        fi
        sleep 1
    done
fi

END=$(date +%s)

# ── Verify ────────────────────────────────────────────────────────

HTTP_CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    info "Done in $((END - START))s — http://localhost:3000 (HTTP $HTTP_CODE)"
else
    error "Done in $((END - START))s but HTTP $HTTP_CODE — check: docker logs $CONTAINER"
    exit 1
fi
