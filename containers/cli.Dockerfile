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

# Copy CLI and shared source and build
COPY clients/shared/ clients/shared/
COPY clients/cli/ clients/cli/
RUN npm run build --workspace=@decepticon/cli

# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM node:24-slim
WORKDIR /app

# Copy compiled output + runtime dependencies
COPY --from=builder /app/clients/cli/package.json ./
COPY --from=builder /app/node_modules ./node_modules
# Shared workspace packages are symlinked from node_modules — copy the
# actual source so the symlinks resolve at runtime.
COPY --from=builder /app/clients/shared ./clients/shared
# tsx runs src/ directly — dist/ is not used at runtime
COPY --from=builder /app/clients/cli/src ./src

ENV DECEPTICON_API_URL=http://langgraph:2024
ENV NODE_ENV=production

# No HEALTHCHECK — CLI is an interactive TTY app with no HTTP surface.

ENTRYPOINT ["node", "--import", "tsx/esm", "src/index.tsx"]
