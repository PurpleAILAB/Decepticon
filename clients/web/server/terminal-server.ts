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
const CLI_PATH = resolve(__dirname, "../../cli/src/index.tsx");
const LANGGRAPH_API_URL = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";

const wss = new WebSocketServer({ port: PORT });

console.log(`[terminal-server] Listening on ws://localhost:${PORT}`);
console.log(`[terminal-server] CLI path: ${CLI_PATH}`);
console.log(`[terminal-server] LangGraph API: ${LANGGRAPH_API_URL}`);

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
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const engagementId = url.searchParams.get("engagementId") ?? "";
  const agentId = url.searchParams.get("agentId") ?? "soundwave";
  let threadId = url.searchParams.get("threadId") ?? "";

  // Create a thread if none provided
  if (!threadId) {
    try {
      threadId = await createThread(engagementId, agentId);
      console.log(`[terminal-server] Created new thread: ${threadId}`);
    } catch (err) {
      console.error(`[terminal-server] Failed to create thread:`, err);
    }
  }

  // Send thread ID to web client so it can save to localStorage
  if (threadId && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "threadId", threadId }));
  }

  console.log(`[terminal-server] Connection: engagement=${engagementId} agent=${agentId} thread=${threadId}`);

  const env: Record<string, string> = {
    ...process.env as Record<string, string>,
    TERM: "xterm-256color",
    FORCE_COLOR: "1",
    DECEPTICON_AGENT: agentId,
    DECEPTICON_ENGAGEMENT_ID: engagementId,
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
