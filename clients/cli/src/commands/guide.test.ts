/**
 * Regression test pinning the CLI /guide path-resolution fix (supersedes #636).
 * Bug: wrote to `${WORKSPACE}/guidance/inbox.jsonl` (root) instead of the
 * per-engagement subdir the agent-side `GuidanceMiddleware` actually drains.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import guide from "./guide.js";
import type { CommandContext } from "./types.js";

function mkCtx(): { ctx: CommandContext; events: string[] } {
  const events: string[] = [];
  const ctx: CommandContext = {
    addSystemEvent: (s: string) => events.push(s),
    clearEvents: () => events.splice(0, events.length),
    submit: () => {},
    resume: () => {},
    exit: () => {},
  };
  return { ctx, events };
}

describe("/guide CLI path resolution (redamon regression)", () => {
  const origEng = process.env.DECEPTICON_ENGAGEMENT;
  const origWs = process.env.DECEPTICON_WORKSPACE_PATH;
  let tmpRoot: string;

  beforeEach(() => {
    tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "deceptcli-"));
    process.env.DECEPTICON_WORKSPACE_PATH = tmpRoot;
    process.env.DECEPTICON_ENGAGEMENT = "eng-abc";
  });
  afterEach(() => {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
    if (origEng === undefined) delete process.env.DECEPTICON_ENGAGEMENT;
    else process.env.DECEPTICON_ENGAGEMENT = origEng;
    if (origWs === undefined) delete process.env.DECEPTICON_WORKSPACE_PATH;
    else process.env.DECEPTICON_WORKSPACE_PATH = origWs;
  });

  it("test_redamon_cli_path_resolved_via_project_helper: writes to per-engagement subdir, not root", async () => {
    const { ctx, events } = mkCtx();
    await guide.execute("focus on .14", ctx);
    const correct = path.join(tmpRoot, "eng-abc", "guidance", "inbox.jsonl");
    const buggyRoot = path.join(tmpRoot, "guidance", "inbox.jsonl");
    expect(fs.existsSync(correct)).toBe(true);
    expect(fs.existsSync(buggyRoot)).toBe(false);
    expect(fs.readFileSync(correct, "utf-8")).toContain('"text":"focus on .14"');
    expect(events.some((e) => e.startsWith("Guidance registered"))).toBe(true);
  });

  it("errors out when DECEPTICON_ENGAGEMENT is unset (no silent drop)", async () => {
    delete process.env.DECEPTICON_ENGAGEMENT;
    const { ctx, events } = mkCtx();
    await guide.execute("focus", ctx);
    expect(events.some((e) => /engagement/i.test(e))).toBe(true);
    expect(fs.existsSync(path.join(tmpRoot, "guidance", "inbox.jsonl"))).toBe(false);
  });

  it("rejects path-traversal slug", async () => {
    process.env.DECEPTICON_ENGAGEMENT = "../etc";
    const { ctx, events } = mkCtx();
    await guide.execute("hi", ctx);
    expect(events.some((e) => /engagement/i.test(e))).toBe(true);
  });
});
