#!/usr/bin/env node
/**
 * Runtime proxy for the containerized web app.
 *
 * It keeps the dashboard and the embedded terminal on one public origin:
 * regular HTTP goes to Next.js, while /terminal WebSocket upgrades go to the
 * terminal bridge process.
 */

import http, { type IncomingMessage } from "http";
import net from "net";

const PORT = parseInt(process.env.WEB_PROXY_PORT ?? "3000", 10);
const NEXT_PORT = parseInt(process.env.NEXT_INTERNAL_PORT ?? "3001", 10);
const TERMINAL_PORT = parseInt(process.env.TERMINAL_PORT ?? "3003", 10);
const HOST = process.env.HOSTNAME ?? "0.0.0.0";

function requestPath(req: IncomingMessage): string {
  return req.url ?? "/";
}

function isTerminalRequest(req: IncomingMessage): boolean {
  return requestPath(req).startsWith("/terminal");
}

function proxyHttp(req: IncomingMessage, res: http.ServerResponse): void {
  if (isTerminalRequest(req)) {
    res.writeHead(426, { "content-type": "text/plain; charset=utf-8" });
    res.end("WebSocket upgrade required");
    return;
  }

  const headers = { ...req.headers };
  headers.host = req.headers.host;
  headers["x-forwarded-host"] = req.headers.host ?? "";
  headers["x-forwarded-proto"] = req.headers["x-forwarded-proto"] ?? "http";

  const upstream = http.request(
    {
      host: "127.0.0.1",
      port: NEXT_PORT,
      method: req.method,
      path: requestPath(req),
      headers,
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode ?? 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    },
  );

  upstream.on("error", (err) => {
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    res.end(`Next.js upstream unavailable: ${err.message}`);
  });

  req.pipe(upstream);
}

function proxyUpgrade(req: IncomingMessage, socket: net.Socket, head: Buffer): void {
  const targetPort = isTerminalRequest(req) ? TERMINAL_PORT : NEXT_PORT;
  const upstream = net.connect(targetPort, "127.0.0.1");

  upstream.on("connect", () => {
    upstream.write(`${req.method} ${requestPath(req)} HTTP/${req.httpVersion}\r\n`);
    for (const [name, value] of Object.entries(req.headers)) {
      if (Array.isArray(value)) {
        for (const item of value) upstream.write(`${name}: ${item}\r\n`);
      } else if (value !== undefined) {
        upstream.write(`${name}: ${value}\r\n`);
      }
    }
    upstream.write("\r\n");
    if (head.length > 0) upstream.write(head);
    upstream.pipe(socket);
    socket.pipe(upstream);
  });

  upstream.on("error", () => {
    if (!socket.destroyed) {
      socket.write("HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n");
      socket.destroy();
    }
  });

  socket.on("error", () => upstream.destroy());
}

const server = http.createServer(proxyHttp);

server.on("upgrade", proxyUpgrade);
server.on("clientError", (_err, socket) => {
  socket.end("HTTP/1.1 400 Bad Request\r\n\r\n");
});

server.listen(PORT, HOST, () => {
  console.log(
    `[web-proxy] Listening on http://${HOST}:${PORT} ` +
    `(next=127.0.0.1:${NEXT_PORT}, terminal=127.0.0.1:${TERMINAL_PORT})`,
  );
});
