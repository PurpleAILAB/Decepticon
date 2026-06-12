import { describe, it, expect, beforeEach, afterEach } from "vitest";
import * as path from "node:path";
import * as os from "node:os";
import {
  SLUG_RE,
  resolveEngagementDir,
  defaultWorkspaceRoot,
  resolveCliEngagementDir,
} from "./workspace.js";

describe("SLUG_RE", () => {
  it("matches launcher policy", () => {
    expect(SLUG_RE.test("eng-abc")).toBe(true);
    expect(SLUG_RE.test("UPPER")).toBe(false);
    expect(SLUG_RE.test("-bad")).toBe(false);
  });
});

describe("resolveEngagementDir", () => {
  it("returns workspace/<slug>", () => {
    expect(resolveEngagementDir("eng-abc", "/workspace")).toBe(
      path.resolve("/workspace", "eng-abc"),
    );
  });
  it("rejects path traversal", () => {
    expect(() => resolveEngagementDir("../etc", "/workspace")).toThrow(
      "invalid engagement path",
    );
  });
});

describe("defaultWorkspaceRoot + resolveCliEngagementDir", () => {
  const origEng = process.env.DECEPTICON_ENGAGEMENT;
  const origWs = process.env.DECEPTICON_WORKSPACE_PATH;
  beforeEach(() => {
    delete process.env.DECEPTICON_ENGAGEMENT;
    delete process.env.DECEPTICON_WORKSPACE_PATH;
  });
  afterEach(() => {
    if (origEng === undefined) delete process.env.DECEPTICON_ENGAGEMENT;
    else process.env.DECEPTICON_ENGAGEMENT = origEng;
    if (origWs === undefined) delete process.env.DECEPTICON_WORKSPACE_PATH;
    else process.env.DECEPTICON_WORKSPACE_PATH = origWs;
  });

  it("default root is ~/.decepticon/workspace", () => {
    expect(defaultWorkspaceRoot()).toBe(
      path.join(os.homedir(), ".decepticon", "workspace"),
    );
  });
  it("honours DECEPTICON_WORKSPACE_PATH override", () => {
    process.env.DECEPTICON_WORKSPACE_PATH = "/custom/ws";
    expect(defaultWorkspaceRoot()).toBe("/custom/ws");
  });
  it("resolves per-engagement subdir from env", () => {
    process.env.DECEPTICON_WORKSPACE_PATH = "/workspace";
    process.env.DECEPTICON_ENGAGEMENT = "eng-abc";
    expect(resolveCliEngagementDir()).toBe(
      path.resolve("/workspace", "eng-abc"),
    );
  });
  it("returns null on missing or bad slug", () => {
    process.env.DECEPTICON_WORKSPACE_PATH = "/workspace";
    expect(resolveCliEngagementDir()).toBeNull();
    process.env.DECEPTICON_ENGAGEMENT = "../etc";
    expect(resolveCliEngagementDir()).toBeNull();
  });
});
