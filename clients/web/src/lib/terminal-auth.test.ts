/**
 * Integration test for the WS handshake auth gate.
 *
 * The real `clients/web/server/terminal-server.ts` is a long-lived
 * process that imports `node-pty`, talks to LangGraph, and spawns the
 * CLI — too heavy to boot in a unit test. We instead spin up a minimal
 * `ws` server that wires up the **identical** auth-mode + extractWsToken
 * + tokensEqual code path, then verify behavior with real `ws` clients.
 *
 * This is a true integration test of the auth boundary (no mocking of
 * the helpers under test); only the unrelated PTY / LangGraph machinery
 * is omitted because it has no bearing on the security gate.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { WebSocketServer, WebSocket } from "ws";
import { type AddressInfo } from "node:net";
import { hashPassword } from "./auth-mode";
import { deriveWsToken, extractWsToken, tokensEqual } from "./auth-token";

type TestServer = {
  port: number;
  close: () => Promise<void>;
};

function startServer(expectedToken: string | null): Promise<TestServer> {
  return new Promise((resolveServer) => {
    const wss = new WebSocketServer({ port: 0, host: "127.0.0.1" });
    wss.on("connection", (ws, req) => {
      const url = new URL(req.url ?? "/", "ws://localhost");
      if (expectedToken) {
        const provided = extractWsToken(req.headers.authorization, url);
        if (!provided || !tokensEqual(provided, expectedToken)) {
          ws.close(1008, "Unauthorized");
          return;
        }
      }
      ws.send("hello");
    });
    wss.on("listening", () => {
      const addr = wss.address() as AddressInfo;
      resolveServer({
        port: addr.port,
        close: () =>
          new Promise<void>((res) => {
            wss.close(() => res());
          }),
      });
    });
  });
}

function connectWS(url: string): Promise<{ closed: boolean; code?: number; message?: string }> {
  return new Promise((resolveConn) => {
    const ws = new WebSocket(url);
    let resolved = false;
    ws.on("message", (data) => {
      if (resolved) return;
      resolved = true;
      resolveConn({ closed: false, message: data.toString() });
      ws.close();
    });
    ws.on("close", (code) => {
      if (resolved) return;
      resolved = true;
      resolveConn({ closed: true, code });
    });
    ws.on("error", () => {
      // ignore — the close event will fire
    });
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolveConn({ closed: true, code: -1 });
        ws.close();
      }
    }, 2000);
  });
}

describe("terminal-server WS handshake — mode: none (default)", () => {
  let server: TestServer;
  beforeAll(async () => {
    server = await startServer(null);
  });
  afterAll(async () => {
    await server.close();
  });

  it("accepts a connection with no token (regression guard for today's behavior)", async () => {
    const result = await connectWS(`ws://127.0.0.1:${server.port}/`);
    expect(result.closed).toBe(false);
    expect(result.message).toBe("hello");
  });
});

describe("terminal-server WS handshake — mode: password", () => {
  const PLAINTEXT = "wsroom";
  const HASH_RAW = hashPassword(PLAINTEXT, { N: 1024 });
  const TOKEN = deriveWsToken(HASH_RAW);

  let server: TestServer;
  beforeAll(async () => {
    server = await startServer(TOKEN);
  });
  afterAll(async () => {
    await server.close();
  });

  it("rejects with code 1008 when no token is sent", async () => {
    const result = await connectWS(`ws://127.0.0.1:${server.port}/`);
    expect(result.closed).toBe(true);
    expect(result.code).toBe(1008);
  });

  it("rejects with code 1008 on an obviously wrong token", async () => {
    const result = await connectWS(`ws://127.0.0.1:${server.port}/?token=deadbeef`);
    expect(result.closed).toBe(true);
    expect(result.code).toBe(1008);
  });

  it("rejects a token that is the right length but the wrong value", async () => {
    const wrong = "f".repeat(TOKEN.length);
    const result = await connectWS(`ws://127.0.0.1:${server.port}/?token=${wrong}`);
    expect(result.closed).toBe(true);
    expect(result.code).toBe(1008);
  });

  it("accepts a connection with the correct ?token=<derived>", async () => {
    const result = await connectWS(`ws://127.0.0.1:${server.port}/?token=${TOKEN}`);
    expect(result.closed).toBe(false);
    expect(result.message).toBe("hello");
  });

  it("uppercase hex query token is normalized and accepted", async () => {
    const result = await connectWS(
      `ws://127.0.0.1:${server.port}/?token=${TOKEN.toUpperCase()}`,
    );
    expect(result.closed).toBe(false);
    expect(result.message).toBe("hello");
  });
});
