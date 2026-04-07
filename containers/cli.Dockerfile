# ── Stage 1: Build ────────────────────────────────────────────────
FROM node:25-slim AS builder
WORKDIR /app

# Copy workspace root (lock file) + cli package.json for dependency install
COPY package.json package-lock.json ./
COPY clients/cli/package.json clients/cli/
RUN npm ci --workspace=@decepticon/cli

# Copy CLI source and build
COPY clients/cli/ clients/cli/
RUN npm run build --workspace=@decepticon/cli

# ── Stage 2: Runtime ──────────────────────────────────────────────
FROM node:25-slim
WORKDIR /app

# Copy compiled output + runtime dependencies
COPY --from=builder /app/clients/cli/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/clients/cli/dist ./dist
# Keep src/ for tsx runtime (index.tsx shebang entry)
COPY --from=builder /app/clients/cli/src ./src

ENV DECEPTICON_API_URL=http://langgraph:2024
ENV NODE_ENV=production

ENTRYPOINT ["node", "--import", "tsx/esm", "src/index.tsx"]
