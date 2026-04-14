import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @decepticon/ee is an optional private package — tell the bundler to skip it
  // and leave resolution to Node.js at runtime (where try/catch handles absence).
  serverExternalPackages: ["@decepticon/ee"],
};

export default nextConfig;
