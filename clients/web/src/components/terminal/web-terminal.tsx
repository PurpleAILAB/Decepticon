"use client";

/**
 * WebTerminal — xterm.js terminal embedding the Decepticon CLI.
 *
 * Connects to the standalone terminal WebSocket server which spawns
 * the CLI in a PTY. Reports the thread ID back to the parent via callback.
 *
 * Reconnection strategy:
 * - Silent reconnect with exponential backoff (1s → 2s → 4s, cap 4s)
 * - No terminal spam during reconnect — only a single status line
 * - Status bar shows connection state at all times
 * - After successful reconnect, clears the status message
 * - After 15 failed attempts, stops and offers manual retry
 */

import { useEffect, useRef, useCallback, useState } from "react";
import { cn } from "@/lib/utils";

const TERMINAL_WS_URL = process.env.NEXT_PUBLIC_TERMINAL_WS_URL ?? "ws://localhost:3003";
const MAX_RECONNECT_DELAY = 4000;
const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_ATTEMPTS = 15;

type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected" | "error";

interface WebTerminalProps {
  engagementId: string;
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
  const [connState, setConnState] = useState<ConnectionState>("connecting");

  const engagementIdRef = useRef(engagementId);
  engagementIdRef.current = engagementId;
  const engagementSlugRef = useRef(engagementSlug);
  engagementSlugRef.current = engagementSlug;
  const agentIdRef = useRef(agentId);
  agentIdRef.current = agentId;
  const onThreadIdRef = useRef(onThreadId);
  onThreadIdRef.current = onThreadId;

  const termRef = useRef<import("xterm").Terminal | null>(null);
  const fitRef = useRef<import("@xterm/addon-fit").FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const disposedRef = useRef(false);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track whether we've shown the reconnecting message (to avoid spam)
  const reconnectMsgShownRef = useRef(false);
  // Track the onData listener for manual retry so we can dispose it
  const retryListenerRef = useRef<{ dispose: () => void } | null>(null);
  // Track the main onData listener so we can dispose it on reconnect
  const onDataDisposableRef = useRef<{ dispose: () => void } | null>(null);

  const cleanup = useCallback(() => {
    disposedRef.current = true;
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    retryListenerRef.current?.dispose();
    resizeObserverRef.current?.disconnect();
    wsRef.current?.close();
    termRef.current?.dispose();
    wsRef.current = null;
    termRef.current = null;
    fitRef.current = null;
  }, []);

  const connectWs = useCallback(() => {
    if (disposedRef.current) return;
    const term = termRef.current;
    if (!term) return;

    // Dispose any pending manual-retry listener
    retryListenerRef.current?.dispose();
    retryListenerRef.current = null;

    // Close old WS
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    const eid = engagementIdRef.current;
    const slug = engagementSlugRef.current;
    const aid = agentIdRef.current;

    const wsUrl =
      `${TERMINAL_WS_URL}?engagementId=${encodeURIComponent(eid)}` +
      `&engagementSlug=${encodeURIComponent(slug)}` +
      `&agentId=${encodeURIComponent(aid)}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnState("connected");
      reconnectAttemptRef.current = 0;
      reconnectMsgShownRef.current = false;
      // Silent reconnect — no terminal output. If the server reattaches us
      // to an existing session, the scrollback replay handles visual continuity.
      ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    };

    ws.onmessage = (event) => {
      const data = typeof event.data === "string" ? event.data : "";
      if (data.startsWith("{")) {
        try {
          const msg = JSON.parse(data);
          // Filter ALL control messages — never write JSON frames to the terminal
          if (msg.type === "threadId" && msg.threadId) {
            onThreadIdRef.current?.(msg.threadId);
            return;
          }
          if (msg.type === "pong" || msg.type === "error" || msg.type === "ping") {
            return; // Control message — consume silently
          }
          if (msg.type === "reattached") {
            // Server reattached us to an existing PTY — full reset then
            // scrollback replay arrives as raw text right after this message.
            term.reset();
            return;
          }
        } catch {
          // Not valid JSON — pass through as terminal output
        }
      }
      term.write(data);
    };

    ws.onclose = (ev) => {
      if (disposedRef.current) return;

      if (ev.code === 1000) {
        // Clean close — process exited normally
        setConnState("disconnected");
        term.writeln("\r\n\x1b[90m[Session ended. Press Enter to start a new session.]\x1b[0m");
        const disposable = term.onData(() => {
          disposable.dispose();
          reconnectAttemptRef.current = 0;
          reconnectMsgShownRef.current = false;
          connectWs();
        });
        retryListenerRef.current = disposable;
        return;
      }

      // Abnormal close — reconnect silently
      scheduleReconnect();
    };

    ws.onerror = () => {
      if (disposedRef.current) return;
      // onerror always fires before onclose — just update the indicator
      setConnState("reconnecting");
    };

    // Forward input — dispose previous listener to prevent duplicates on reconnect
    onDataDisposableRef.current?.dispose();
    onDataDisposableRef.current = term.onData((data: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(data);
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (disposedRef.current) return;

    const attempt = reconnectAttemptRef.current;

    if (attempt >= MAX_RECONNECT_ATTEMPTS) {
      setConnState("error");
      const term = termRef.current;
      if (term) {
        term.writeln("\r\n\x1b[31m[Connection failed. Press Enter to retry.]\x1b[0m");
        reconnectMsgShownRef.current = false;
        const disposable = term.onData(() => {
          disposable.dispose();
          reconnectAttemptRef.current = 0;
          connectWs();
        });
        retryListenerRef.current = disposable;
      }
      return;
    }

    // Show ONE reconnecting message on the first attempt only
    // No terminal output during reconnect — status bar shows state.
    // The server's session persistence means the PTY is still alive;
    // on reattach the scrollback replays seamlessly.
    reconnectMsgShownRef.current = true;

    setConnState("reconnecting");
    const delay = Math.min(INITIAL_RECONNECT_DELAY * Math.pow(2, attempt), MAX_RECONNECT_DELAY);
    reconnectAttemptRef.current = attempt + 1;

    reconnectTimerRef.current = setTimeout(() => {
      if (!disposedRef.current) connectWs();
    }, delay);
  }, [connectWs]);

  // Initialize terminal + first connection
  const init = useCallback(async () => {
    const container = containerRef.current;
    if (!container || disposedRef.current) return;

    try {
      const [{ Terminal }, { FitAddon }] = await Promise.all([
        import("xterm"),
        import("@xterm/addon-fit"),
      ]);
      await import("xterm/css/xterm.css");

      if (termRef.current) {
        // Already initialized — just reconnect WS
        connectWs();
        return;
      }

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
        scrollback: 10000,
      });

      const fit = new FitAddon();
      term.loadAddon(fit);
      term.open(container);
      fit.fit();

      termRef.current = term;
      fitRef.current = fit;

      // Resize observer
      const resizeObserver = new ResizeObserver(() => {
        if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
        resizeTimerRef.current = setTimeout(() => {
          try {
            fitRef.current?.fit();
            const ws = wsRef.current;
            const t = termRef.current;
            if (ws?.readyState === WebSocket.OPEN && t) {
              ws.send(JSON.stringify({ type: "resize", cols: t.cols, rows: t.rows }));
            }
          } catch {
            // ignore
          }
        }, 150);
      });
      resizeObserver.observe(container);
      resizeObserverRef.current = resizeObserver;

      // Connect
      connectWs();
    } catch (err) {
      setConnState("error");
      console.error("[WebTerminal] Init failed:", err);
    }
  }, [connectWs]);

  useEffect(() => {
    disposedRef.current = false;
    init();
    return cleanup;
  }, [init, cleanup]);

  // ── Heartbeat: detect silently-dead sockets ──────────────────────
  // Ping every 15s; if no data received from server within 20s of a
  // ping, the socket is half-open — force-close and let reconnect handle it.
  // Pong responses are filtered by onmessage above (never reach terminal).
  useEffect(() => {
    const PING_INTERVAL = 15000;
    const PONG_TIMEOUT = 5000;
    let pongTimer: ReturnType<typeof setTimeout>;

    const pingTimer = setInterval(() => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      try {
        ws.send(JSON.stringify({ type: "ping" }));
        pongTimer = setTimeout(() => {
          // If WS is still the same instance and still "open", it's half-open — kill it
          if (wsRef.current === ws && ws.readyState === WebSocket.OPEN) {
            ws.close();
          }
        }, PONG_TIMEOUT);
      } catch {
        ws.close();
      }
    }, PING_INTERVAL);

    return () => {
      clearInterval(pingTimer);
      clearTimeout(pongTimer);
    };
  }, [connState]);

  // ── Visibility: reconnect when tab becomes visible ───────────────
  // Browsers throttle/kill WS in background tabs. Reconnect on focus.
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === "visible") {
        const ws = wsRef.current;
        if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
          reconnectAttemptRef.current = 0;
          reconnectMsgShownRef.current = false;
          connectWs();
        }
      }
    };
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, [connectWs]);

  // ── Network: reconnect when browser comes back online ────────────
  useEffect(() => {
    const handler = () => {
      const ws = wsRef.current;
      if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
        reconnectAttemptRef.current = 0;
        reconnectMsgShownRef.current = false;
        connectWs();
      }
    };
    window.addEventListener("online", handler);
    return () => window.removeEventListener("online", handler);
  }, [connectWs]);

  const statusColor: Record<ConnectionState, string> = {
    connecting: "bg-amber-400",
    connected: "bg-emerald-400",
    reconnecting: "bg-amber-400 animate-pulse",
    disconnected: "bg-zinc-500",
    error: "bg-red-400",
  };

  const statusLabel: Record<ConnectionState, string> = {
    connecting: "Connecting...",
    connected: "Connected",
    reconnecting: "Reconnecting...",
    disconnected: "Disconnected",
    error: "Connection Error",
  };

  return (
    <div className={cn("relative flex flex-col", className)}>
      {/* Status bar */}
      <div className="flex items-center gap-2 border-b border-white/[0.06] bg-[#0a0e14] px-3 py-1.5">
        <div className={cn("h-2 w-2 rounded-full", statusColor[connState])} />
        <span className="text-[11px] text-zinc-500">{statusLabel[connState]}</span>
        <span className="flex-1" />
        <span className="text-[10px] font-mono text-zinc-600">{engagementSlug}</span>
      </div>
      {/* Terminal container */}
      <div
        ref={containerRef}
        className="flex-1"
        style={{
          backgroundColor: "#0a0e14",
          padding: "8px",
          minHeight: 0,
        }}
      />
    </div>
  );
}
