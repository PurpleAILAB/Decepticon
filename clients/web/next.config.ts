import type { NextConfig } from "next";
import path from "node:path";

const LANGGRAPH_API_URL = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";

const nextConfig: NextConfig = {
  // Standalone output for Docker deployment (copies only needed files)
  output: "standalone",
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
  // Proxy LangGraph SDK requests to the LangGraph server (avoids CORS,
  // enables direct SDK streaming from the browser).
  async rewrites() {
    return [
      {
        source: "/lgs/:path*",
        destination: `${LANGGRAPH_API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
