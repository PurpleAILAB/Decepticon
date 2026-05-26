import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import { safeDeleteEngagement, pruneTrash } from "./safe-delete";

describe("safe-delete", () => {
  let decepticonHome: string;
  let workspacePath: string;

  beforeEach(async () => {
    decepticonHome = await fs.mkdtemp(
      path.join(os.tmpdir(), "decepticon-test-"),
    );
    workspacePath = path.join(decepticonHome, "workspace");
    await fs.mkdir(workspacePath, { recursive: true });
  });

  afterEach(async () => {
    await fs.rm(decepticonHome, { recursive: true, force: true });
  });

  it("moves an engagement to .trash on non-darwin platforms", async () => {
    if (process.platform === "darwin") {
      // The macOS path goes through osascript / Finder; cover with a
      // platform-specific test rather than mutating the user's Trash.
      return;
    }
    const slug = "test-engagement";
    const engagementDir = path.join(workspacePath, slug);
    await fs.mkdir(engagementDir);
    await fs.writeFile(path.join(engagementDir, "marker.txt"), "important");

    const dest = await safeDeleteEngagement(workspacePath, slug);

    // Original gone
    await expect(fs.access(engagementDir)).rejects.toThrow();
    // Trash copy intact
    expect(dest).toContain(path.join(decepticonHome, ".trash"));
    expect(dest).toContain(slug);
    const restored = await fs.readFile(
      path.join(dest, "marker.txt"),
      "utf-8",
    );
    expect(restored).toBe("important");
  });

  it("is idempotent when the engagement is already gone", async () => {
    const dest = await safeDeleteEngagement(workspacePath, "ghost-engagement");
    // No exception; returns the would-be target path
    expect(dest).toContain("ghost-engagement");
  });

  it("rejects unsafe slugs (path traversal / separators)", async () => {
    await expect(
      safeDeleteEngagement(workspacePath, "../etc"),
    ).rejects.toThrow(/unsafe slug/);
    await expect(
      safeDeleteEngagement(workspacePath, "a/b"),
    ).rejects.toThrow(/unsafe slug/);
    await expect(
      safeDeleteEngagement(workspacePath, ".hidden"),
    ).rejects.toThrow(/unsafe slug/);
    await expect(
      safeDeleteEngagement(workspacePath, "ab"),
    ).rejects.toThrow(/unsafe slug/);
  });

  it("pruneTrash removes entries older than 30 days", async () => {
    const trashDir = path.join(decepticonHome, ".trash");
    await fs.mkdir(trashDir, { recursive: true });
    const stale = path.join(trashDir, "old-engagement-2026-01-01");
    const fresh = path.join(trashDir, "new-engagement-now");
    await fs.mkdir(stale);
    await fs.mkdir(fresh);
    const fortyDaysAgo = new Date(Date.now() - 40 * 24 * 60 * 60 * 1000);
    await fs.utimes(stale, fortyDaysAgo, fortyDaysAgo);

    await pruneTrash(workspacePath);

    await expect(fs.access(stale)).rejects.toThrow(); // pruned
    await fs.access(fresh); // kept
  });

  it("pruneTrash is a no-op when .trash doesn't exist", async () => {
    await expect(pruneTrash(workspacePath)).resolves.not.toThrow();
  });
});
