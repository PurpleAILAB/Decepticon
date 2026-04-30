#!/usr/bin/env node
/**
 * Terminal WebSocket Server — spawns Decepticon CLI in a PTY.
 *
 * Creates a LangGraph thread on connection (if none exists) and shares it
 * with both the CLI process (via env var) and the web client (via JSON message).
 * This ensures both surfaces observe the same execution.
 *
 * Protocol (Server → Client):
 *   - JSON { type: "threadId", threadId: "..." } — thread ID for web to store
 *   - Raw text — PTY stdout/stderr for xterm.js
 *
 * Protocol (Client → Server):
 *   - JSON { type: "resize", cols, rows } — terminal resize
 *   - Raw text — stdin for PTY
 */

import { WebSocketServer, WebSocket } from "ws";
import * as pty from "node-pty";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PORT = parseInt(process.env.TERMINAL_PORT ?? "3003", 10);
const WEB_PORT = process.env.WEB_PORT ?? "3000";
const CLI_PATH = resolve(__dirname, "../../cli/src/index.tsx");
const LANGGRAPH_API_URL = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";
const ALLOWED_ORIGINS = new Set(
  (process.env.TERMINAL_ALLOWED_ORIGINS ?? `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`)
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
);

const wss = new WebSocketServer({ port: PORT });

console.log(`[terminal-server] Listening on ws://localhost:${PORT}`);
console.log(`[terminal-server] CLI path: ${CLI_PATH}`);
console.log(`[terminal-server] LangGraph API: ${LANGGRAPH_API_URL}`);

function isAllowedOrigin(origin: string | undefined): boolean {
  if (!origin) return false;
  try {
    return ALLOWED_ORIGINS.has(new URL(origin).origin);
  } catch {
    return false;
  }
}

/** Create a new LangGraph thread via the REST API. */
async function createThread(engagementId: string, agentId: string): Promise<string> {
  const res = await fetch(`${LANGGRAPH_API_URL}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      metadata: {
        engagement_id: engagementId,
        assistant_id: agentId,
      },
    }),
  });
  if (!res.ok) throw new Error(`Failed to create thread: ${res.status}`);
  const data = await res.json() as { thread_id: string };
  return data.thread_id;
}

wss.on("connection", async (ws: WebSocket, req) => {
  if (!isAllowedOrigin(req.headers.origin)) {
    ws.close(1008, "Origin not allowed");
    return;
  }

  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const engagementId = url.searchParams.get("engagementId") ?? "";
  // engagementSlug is the folder name under ~/.decepticon/workspace/.
  // It identifies the engagement directory the CLI will operate inside;
  // engagementId is the DB record cuid passed to LangGraph thread metadata.
  const engagementSlug = url.searchParams.get("engagementSlug") ?? "";
  const agentId = url.searchParams.get("agentId") ?? "soundwave";
  let threadId = url.searchParams.get("threadId") ?? "";

  if (!threadId) {
    try {
      threadId = await createThread(engagementId, agentId);
      console.log(`[terminal-server] Created new thread: ${threadId}`);
    } catch (err) {
      console.error(`[terminal-server] Failed to create thread:`, err);
    }
  }

  if (threadId && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "threadId", threadId }));
  }

  console.log(
    `[terminal-server] Connection: engagement=${engagementId} slug=${engagementSlug} agent=${agentId} thread=${threadId}`,
  );

  const env: Record<string, string> = {
    ...process.env as Record<string, string>,
    TERM: "xterm-256color",
    FORCE_COLOR: "1",
    // Names align with the CLI's expectations (clients/cli/src/hooks/useAgent.ts):
    // DECEPTICON_ASSISTANT_ID picks the LangGraph assistant; DECEPTICON_ENGAGEMENT
    // is the folder slug used for system-level logging and the engagement_ready
    // handoff. Internal Docker hostname for the LangGraph endpoint is forwarded
    // explicitly so the CLI subprocess does not fall back to localhost.
    DECEPTICON_ASSISTANT_ID: agentId,
    DECEPTICON_ENGAGEMENT: engagementSlug,
    DECEPTICON_API_URL: LANGGRAPH_API_URL,
  };
  if (threadId) {
    env.DECEPTICON_THREAD_ID = threadId;
  }

  const term = pty.spawn("node", ["--import", "tsx/esm", CLI_PATH], {
    name: "xterm-256color",
    cols: 120,
    rows: 30,
    cwd: resolve(__dirname, "../.."),
    env,
  });

  console.log(`[terminal-server] PTY spawned: pid=${term.pid}`);

  term.onData((data: string) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  });

  term.onExit(({ exitCode }) => {
    console.log(`[terminal-server] PTY exited: pid=${term.pid} code=${exitCode}`);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(`\r\n[Process exited with code ${exitCode}]\r\n`);
      ws.close();
    }
  });

  ws.on("message", (raw: Buffer | string) => {
    const msg = raw.toString();
    try {
      const parsed = JSON.parse(msg);
      if (parsed.type === "resize" && parsed.cols && parsed.rows) {
        term.resize(parsed.cols, parsed.rows);
        return;
      }
    } catch {
      // Not JSON — raw stdin
    }
    term.write(msg);
  });

  ws.on("close", () => {
    console.log(`[terminal-server] Connection closed, killing PTY pid=${term.pid}`);
    term.kill();
  });

  ws.on("error", (err) => {
    console.error(`[terminal-server] WebSocket error:`, err.message);
    term.kill();
  });
});

wss.on("error", (err) => {
  console.error(`[terminal-server] Server error:`, err.message);
});
