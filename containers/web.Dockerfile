FROM node:24-slim AS base

WORKDIR /app

# Install dependencies
FROM base AS deps
COPY package.json package-lock.json ./
COPY clients/cli/package.json clients/cli/
COPY clients/web/package.json clients/web/
COPY clients/shared/streaming/package.json clients/shared/streaming/
RUN npm ci

# Generate Prisma client
COPY clients/web/prisma ./clients/web/prisma
COPY clients/web/prisma.config.ts ./clients/web/prisma.config.ts
WORKDIR /app/clients/web
RUN npx prisma generate
WORKDIR /app

# Build application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY clients/shared/ clients/shared/
COPY clients/web/ clients/web/
# Prisma generates to src/generated/ (gitignored) — carry it over from deps stage
COPY --from=deps /app/clients/web/src/generated ./clients/web/src/generated
WORKDIR /app/clients/web
# Explicit OSS edition — proxy.ts + hasEE() check this env var.
# EE builds override via --build-arg or separate Dockerfile.
ENV NEXT_PUBLIC_DECEPTICON_EDITION=oss
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
# OSS mode — same edition marker used at build time, propagated to runtime.
ENV NEXT_PUBLIC_DECEPTICON_EDITION=oss

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/clients/web/public ./public
# Next.js 16 standalone nests under the original path (clients/web/)
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/standalone/clients/web ./
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/standalone/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/clients/web/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
