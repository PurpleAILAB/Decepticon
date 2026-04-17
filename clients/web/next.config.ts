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
  // @decepticon/ee is an optional private package — tell the bundler to skip it
  // and leave resolution to Node.js at runtime (where try/catch handles absence).
  serverExternalPackages: ["@decepticon/ee"],
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
