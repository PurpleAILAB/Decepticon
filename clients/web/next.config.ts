import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              "connect-src 'self' ws://localhost:* http://localhost:*",
              "frame-ancestors 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
  // Pin Turbopack workspace root to the monorepo root (where npm workspaces
  // hoist node_modules). Without this, Turbopack can't resolve `next` since
  // it's not in clients/web/node_modules anymore.
  turbopack: {
    root: path.resolve(process.cwd(), "..", ".."),
  },
  // Packages that must NOT be bundled — left as external Node.js requires.
  // @prisma/client + pg: Turbopack otherwise aliases them with content hashes
  // (e.g. @prisma/client-2c3a…) which the standalone build can't resolve at runtime.
  // @decepticon/ee: optional private package, absence handled via try/catch.
  serverExternalPackages: ["@prisma/client", "pg", "@decepticon/ee", "node-pty", "ws"],
  // Do not expose raw LangGraph rewrites from the public web app. Browser
  // clients should use localhost-only LangGraph URLs in local OSS mode or
  // authenticated server-side route handlers in hosted deployments.
};

export default nextConfig;
