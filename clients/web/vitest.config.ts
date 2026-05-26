import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // Disable PostCSS processing — Next.js's tailwind/lightningcss pipeline
  // isn't relevant for Node-side unit tests, and on macOS its optional
  // native binary often isn't installed.
  css: {
    postcss: { plugins: [] },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    environment: "node",
    globals: false,
  },
});
