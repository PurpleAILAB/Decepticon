# ----------------------
# build-base — Node 22 LTS + native build toolchain.
# Used only by stages that compile native addons (node-pty, sharp).
# ----------------------
FROM node:22-slim AS build-base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    ca-certificates \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ----------------------
# deps — install full workspace dependencies (incl. devDependencies for build).
# ----------------------
FROM build-base AS deps

WORKDIR /app

COPY package.json package-lock.json ./
COPY clients/cli/package.json clients/cli/
COPY clients/web/package.json clients/web/
COPY clients/shared/streaming/package.json clients/shared/streaming/

RUN npm ci --no-audit --no-fund

# ----------------------
# build — prisma generate + next build.
# Granular COPYs so unrelated files don't bust the build cache.
# ----------------------
FROM build-base AS build

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY clients/web ./clients/web
COPY clients/cli ./clients/cli
COPY clients/shared ./clients/shared

WORKDIR /app/clients/web

RUN npx prisma generate
RUN npm run build

# ----------------------
# runtime — minimal node:22-slim, NO build toolchain.
# Native addons compiled in `build` are copied as prebuilt .node binaries;
# python3/make/g++ are not needed at runtime and would add ~1GB of bloat.
# ----------------------
FROM node:22-slim AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
ENV TERMINAL_PORT=3003

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Standalone Next.js server
COPY --from=build --chown=nextjs:nodejs /app/clients/web/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/clients/web/.next/static ./clients/web/.next/static
COPY --from=build --chown=nextjs:nodejs /app/clients/web/public ./clients/web/public
# Prisma schema + migrations
COPY --from=build --chown=nextjs:nodejs /app/clients/web/prisma ./clients/web/prisma
COPY --from=build --chown=nextjs:nodejs /app/clients/web/prisma.config.ts ./clients/web/prisma.config.ts
# Terminal WebSocket server
COPY --from=build --chown=nextjs:nodejs /app/clients/web/server ./clients/web/server
# CLI source (spawned by terminal server via PTY)
COPY --from=build --chown=nextjs:nodejs /app/clients/cli/src ./clients/cli/src
COPY --from=build --chown=nextjs:nodejs /app/clients/cli/package.json ./clients/cli/package.json
# Shared streaming library
COPY --from=build --chown=nextjs:nodejs /app/clients/shared ./clients/shared
# node_modules carries the compiled native addons (node-pty, sharp) plus
# tsx for running the terminal server. Production-only installs would drop
# tsx (devDep), so we keep the full tree but rely on the `runner` stage
# omitting build tools to keep the image lean.
COPY --from=build --chown=nextjs:nodejs /app/node_modules ./node_modules

WORKDIR /app/clients/web

COPY --chmod=755 containers/web-entrypoint.sh /web-entrypoint.sh

USER nextjs

EXPOSE 3000 3003

CMD ["/web-entrypoint.sh"]
