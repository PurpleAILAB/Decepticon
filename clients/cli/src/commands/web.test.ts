import { describe, expect, it } from "vitest";
import { formatComposeFailure } from "./web.js";

describe("formatComposeFailure", () => {
  it("keeps the tail of docker compose stderr so the real error is visible", () => {
    const stderr = `${"pulling layer\n".repeat(80)}Error response from daemon: ports are not available: bind: address already in use`;

    const message = formatComposeFailure("start", 1, stderr);

    expect(message).toContain("Failed to start web (exit 1)");
    expect(message).toContain("address already in use");
  });
});
