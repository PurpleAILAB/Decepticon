FROM node:24-slim AS base

WORKDIR /app

# Install dependencies
FROM base AS deps
COPY clients/web/package.json clients/web/package-lock.json ./
RUN npm ci --production=false

# Generate Prisma client
COPY clients/web/prisma ./prisma
COPY clients/web/prisma.config.ts ./prisma.config.ts
RUN npx prisma generate

# Build application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY clients/web/ .
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
