# ── Stage 1: Build ────────────────────────────────────────────────
FROM node:24-slim AS builder
WORKDIR /app

# Copy workspace root (lock file) + cli package.json for dependency install
COPY package.json package-lock.json ./
COPY clients/cli/package.json clients/cli/
COPY clients/shared/streaming/package.json clients/shared/streaming/

# Stamp the package version from the git tag at build time. Source-tree
# package.json carries a "0.0.0" sentinel; release.yml passes the real
# version via --build-arg so the shipped package metadata matches the tag.
ARG VERSION=0.0.0
RUN sed -i 's/"version": "[^"]*"/"version": "'"$VERSION"'"/' clients/cli/package.json

RUN npm ci --workspace=@decepticon/cli

# Copy CLI and shared source and build. Build the shared workspace first
# so the CLI's tsc compile + runtime both resolve `@decepticon/streaming`
# to its emitted dist/ (its package.json main points at dist/index.js).
COPY clients/shared/ clients/shared/
COPY clients/cli/ clients/cli/
RUN npm run build --workspace=@decepticon/streaming
RUN npm run build --workspace=@decepticon/cli

# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM node:24-slim
WORKDIR /app

# Copy compiled output + runtime dependencies. We run plain `node` on the
# tsc-emitted dist/ — no tsx runtime loader. tsx 4.20+ registers a JSON
# transform on the module loader that rewrites `*.json` into ESM JS, which
# breaks any CJS dependency doing `require('./*.json')` (notably
# `cli-boxes` via `boxen` via `ink`). Compiling ahead of time and dropping
# tsx at runtime removes that hazard entirely.
COPY --from=builder /app/clients/cli/package.json ./
COPY --from=builder /app/node_modules ./node_modules
# Shared workspace package is symlinked from node_modules; copy its
# package.json + dist so the symlink resolves to a real ESM build.
COPY --from=builder /app/clients/shared/streaming/package.json ./clients/shared/streaming/package.json
COPY --from=builder /app/clients/shared/streaming/dist ./clients/shared/streaming/dist
COPY --from=builder /app/clients/cli/dist ./dist

ENV DECEPTICON_API_URL=http://langgraph:2024
ENV NODE_ENV=production

# No HEALTHCHECK — CLI is an interactive TTY app with no HTTP surface.

# Run as root by operator policy. The CLI shells out to bundled offensive
# tools (apt/curl/wget/git fetches at runtime), so a non-root USER would
# break the agent's ability to install missing utilities on the fly.
# Semgrep ``missing-user-entrypoint`` is explicitly dispositioned here.
USER root

ENTRYPOINT ["node", "dist/index.js"]
