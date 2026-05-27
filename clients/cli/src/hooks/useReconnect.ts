/**
 * useReconnect — backoff scheduling for the CLI's LangGraph stream.
 *
 * The CLI streams events from LangGraph over HTTP (the @langchain/langgraph-sdk
 * Client wraps SSE/WebSocket transport). When LangGraph or its upstream LiteLLM
 * sidecar restarts, the stream drops mid-run and the operator used to need a
 * Ctrl+C + relaunch to recover.
 *
 * This module exposes the pure scheduler used by useAgent's reconnect loop so
 * the schedule itself can be unit-tested without spinning up the React hook
 * and the mock SDK. The full loop (joinStream + thread-state resume + UI
 * notice) lives in useAgent.ts.
 *
 * Schedule (from docs/fork/2026-05-26-decepticon-mac-fork-design.md §5.7):
 *
 *   attempt 1 → 1s
 *   attempt 2 → 2s
 *   attempt 3 → 4s
 *   attempt 4 → 8s
 *   attempt 5+ → 16s (cap)
 *
 * The counter resets to 0 once a single message lands on a freshly reconnected
 * stream, so a stable connection that flickers once doesn't lock us into the
 * cap on the next blip.
 */

/** Backoff schedule in milliseconds: 1s, 2s, 4s, 8s, 16s. */
export const BACKOFF_SCHEDULE_MS = [1000, 2000, 4000, 8000, 16000] as const;

/** Maximum delay between reconnect attempts (cap once the schedule is exhausted). */
export const BACKOFF_CAP_MS = 16000;

/**
 * Maximum total consecutive reconnect attempts before we give up and surface a
 * hard error to the operator. The CLI then transitions to a `"disconnected"`
 * connection status and the run is treated as failed.
 *
 * Eight attempts at the documented schedule covers roughly the first ~75
 * seconds of an outage — enough to ride out a LangGraph restart or a LiteLLM
 * blip without giving up too aggressively. Beyond that, something is wrong
 * with the operator's setup and surfacing the error is more useful than
 * silently retrying.
 */
export const MAX_RECONNECT_ATTEMPTS = 8;

/**
 * Returns the next backoff delay (ms) given the count of consecutive failures.
 *
 * - 0 failures → 0 (caller has not yet observed a drop; no delay).
 * - 1..5 failures → the documented schedule above.
 * - 6+ failures → BACKOFF_CAP_MS.
 *
 * The `consecutiveFailures` argument is "the number of failed attempts so far
 * including the one that just happened" — so the first call after a drop
 * passes `1` and gets back `1000`.
 */
export function nextBackoffMs(consecutiveFailures: number): number {
  if (consecutiveFailures <= 0) return 0;
  const idx = Math.min(consecutiveFailures - 1, BACKOFF_SCHEDULE_MS.length - 1);
  return BACKOFF_SCHEDULE_MS[idx] ?? BACKOFF_CAP_MS;
}
