"use client";

/**
 * WebTerminal — xterm.js terminal embedding the Decepticon CLI.
 *
 * Connects to the standalone terminal WebSocket server which spawns
 * the CLI in a PTY. Reports the thread ID back to the parent via callback.
 */

import { useEffect, useRef, useCallback } from "react";

const TERMINAL_WS_URL = process.env.NEXT_PUBLIC_TERMINAL_WS_URL ?? "ws://localhost:3003";

interface WebTerminalProps {
  /** Engagement DB cuid — used as LangGraph thread metadata. */
  engagementId: string;
  /** Engagement folder slug — used to scope the sandbox /workspace bind. */
  engagementSlug: string;
  agentId?: string;
  className?: string;
  onThreadId?: (threadId: string) => void;
}

export function WebTerminal({
  engagementId,
  engagementSlug,
  agentId = "soundwave",
  className,
  onThreadId,
}: WebTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const connectedRef = useRef(false);
  const engagementIdRef = useRef(engagementId);
  engagementIdRef.current = engagementId;
  const engagementSlugRef = useRef(engagementSlug);
  engagementSlugRef.current = engagementSlug;
  const agentIdRef = useRef(agentId);
  agentIdRef.current = agentId;
  const onThreadIdRef = useRef(onThreadId);
  onThreadIdRef.current = onThreadId;

  const connect = useCallback(async () => {
    const container = containerRef.current;
    if (!container || connectedRef.current) return;
    connectedRef.current = true;

    const [{ Terminal }, { FitAddon }] = await Promise.all([
      import("xterm"),
      import("@xterm/addon-fit"),
    ]);

    await import("xterm/css/xterm.css");

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'IBM Plex Mono', 'Fira Code', monospace",
      theme: {
        background: "#0a0e14",
        foreground: "#d4d4d4",
        cursor: "#faa32c",
        selectionBackground: "#264f78",
        black: "#1e1e1e",
        red: "#f44747",
        green: "#6a9955",
        yellow: "#d7ba7d",
        blue: "#569cd6",
        magenta: "#c586c0",
        cyan: "#4ec9b0",
        white: "#d4d4d4",
        brightBlack: "#808080",
        brightRed: "#f44747",
        brightGreen: "#6a9955",
        brightYellow: "#d7ba7d",
        brightBlue: "#569cd6",
        brightMagenta: "#c586c0",
        brightCyan: "#4ec9b0",
        brightWhite: "#ffffff",
      },
      allowTransparency: true,
      scrollback: 5000,
    });

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(container);
    fit.fit();

    const eid = engagementIdRef.current;
    const slug = engagementSlugRef.current;
    const aid = agentIdRef.current;

    const wsUrl =
      `${TERMINAL_WS_URL}?engagementId=${encodeURIComponent(eid)}` +
      `&engagementSlug=${encodeURIComponent(slug)}` +
      `&agentId=${encodeURIComponent(aid)}`;
    const ws = new WebSocket(wsUrl);

    let disposed = false;

    const cleanup = () => {
      if (disposed) return;
      disposed = true;
      resizeObserver.disconnect();
      ws.close();
      term.dispose();
      connectedRef.current = false;
      cleanupRef.current = null;
    };

    cleanupRef.current = cleanup;

    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: "resize",
        cols: term.cols,
        rows: term.rows,
      }));
    };

    ws.onmessage = (event) => {
      const data = typeof event.data === "string" ? event.data : "";
      if (data.startsWith("{")) {
        try {
          const msg = JSON.parse(data);
          if (msg.type === "threadId" && msg.threadId) {
            onThreadIdRef.current?.(msg.threadId);
            return;
          }
        } catch {
          // Not JSON
        }
      }
      term.write(data);
    };

    ws.onclose = () => {};
    ws.onerror = () => {};

    term.onData((data: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    let resizeTimer: ReturnType<typeof setTimeout>;
    const resizeObserver = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        try {
          fit.fit();
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: "resize",
              cols: term.cols,
              rows: term.rows,
            }));
          }
        } catch {
          // Ignore resize errors during teardown
        }
      }, 150);
    });
    resizeObserver.observe(container);
  }, []);

  useEffect(() => {
    connect();
    return () => { cleanupRef.current?.(); };
  }, [connect]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: "#0a0e14",
        padding: "8px",
      }}
    />
  );
}
