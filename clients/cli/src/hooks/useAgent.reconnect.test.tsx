// @vitest-environment jsdom
//
// useAgent reconnect-loop behavior tests.
//
// Kept in its own file (rather than extending useAgent.test.tsx) because the
// reconnect path needs a richer mock surface — joinStream, controllable
// drop/error iterators, advancing fake timers through the backoff schedule —
// and mixing the two would obscure either suite. The engagement-handoff suite
// in useAgent.test.tsx covers the happy-path lifecycle; this file covers what
// happens when the WebSocket flips around mid-stream.

import { renderHook, act } from "@testing-library/react";
import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
  type Mock,
} from "vitest";
import {
  createMockStream,
  createMockClient,
  createControllableStream,
  type MockClient,
  type StreamEvent,
} from "./__fixtures__/mockStream.js";

// ── Hoisted mock state ──────────────────────────────────────────────────────
const { mockState } = vi.hoisted(() => ({
  mockState: { client: null as MockClient | null },
}));

vi.mock("@langchain/langgraph-sdk", () => ({
  Client: vi.fn(() => mockState.client),
}));

vi.mock("../utils/threadStore.js", () => ({
  saveThread: vi.fn(async () => {}),
  touchThread: vi.fn(async () => {}),
  loadThreadByIndex: vi.fn(async () => null),
}));

vi.mock("../commands/modelOverride.js", () => ({
  getModelOverride: () => undefined,
}));

vi.mock("../commands/assistantOverride.js", () => ({
  getAssistantOverride: () => undefined,
}));

// Dynamic import after env stubbing — see useAgent.test.tsx for rationale.
let useAgent: (typeof import("./useAgent.js"))["useAgent"];

// ── Common event fixtures ───────────────────────────────────────────────────

const metadataEvent: StreamEvent = {
  event: "metadata",
  data: { run_id: "run-xyz", thread_id: "thread-1" },
};

/** A LangGraph "values" snapshot containing one AI message with no tool calls
 *  — the natural-end-of-run signal that flips completionReceived. */
const completionValuesEvent: StreamEvent = {
  event: "values",
  data: {
    messages: [{ type: "ai", content: "all done" }],
  },
};

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Build an iterator that yields the given events and then throws — simulates
 * a WebSocket close that ESBuild-style transports surface as an iteration
 * error mid-stream.
 */
function streamThatThrows(events: StreamEvent[], errMsg: string): AsyncIterable<StreamEvent> {
  return {
    async *[Symbol.asyncIterator]() {
      for (const e of events) {
        await Promise.resolve();
        yield e;
      }
      throw new Error(errMsg);
    },
  };
}

// ── Suite ───────────────────────────────────────────────────────────────────

describe("useAgent — WebSocket auto-reconnect", () => {
  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();
    vi.stubEnv("DECEPTICON_API_URL", "http://localhost:2024");
    vi.stubEnv("DECEPTICON_ASSISTANT_ID", "decepticon");
    delete process.env.DECEPTICON_ENGAGEMENT;
    delete process.env.DECEPTICON_WORKSPACE_PATH;
    delete process.env.DECEPTICON_THREAD_ID;
    mockState.client = createMockClient();
    ({ useAgent } = await import("./useAgent.js"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  // ── 1. Drop mid-stream → reconnect via joinStream, no second POST ─────────
  it("re-attaches via joinStream after a drop without dispatching a duplicate run", async () => {
    const mc = mockState.client!;

    // First pass: metadata, then the connection dies.
    const firstStream = streamThatThrows([metadataEvent], "ECONNRESET");
    // Second pass (after reconnect): receives the completion event cleanly.
    const secondStream = createMockStream([completionValuesEvent]);

    // runs.stream is the "POST a new run" entry point — only the first
    // attempt should ever call it. Subsequent reconnects must go through
    // joinStream against the captured run_id.
    (mc.runs.stream as Mock).mockReturnValueOnce(firstStream);
    (mc.runs.joinStream as Mock).mockReturnValueOnce(secondStream);

    const { result } = renderHook(() => useAgent());

    act(() => {
      result.current.submit("kick off the run");
    });

    // Let runs.stream get called and the first stream's metadata event flow
    // through, then the error fires.
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Advance through the 1s backoff for the first reconnect attempt.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
      await vi.runAllTimersAsync();
    });

    // Final flush so the second stream's completion event lands and the
    // reconnect "Reconnected" notice's 2s timer rolls forward.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
      await vi.runAllTimersAsync();
    });

    // CRITICAL: only ONE POST to /runs/stream — no duplicate run dispatched.
    expect((mc.runs.stream as Mock).mock.calls.length).toBe(1);

    // joinStream was called against the captured run_id from metadata.
    expect((mc.runs.joinStream as Mock).mock.calls.length).toBe(1);
    const joinArgs = (mc.runs.joinStream as Mock).mock.calls[0];
    expect(joinArgs[1]).toBe("run-xyz");

    // Thread state was fetched before the resume call (so we don't replay).
    expect((mc.threads.getState as Mock).mock.calls.length).toBeGreaterThanOrEqual(1);

    // Final connection status is "connected"; "Reconnected" flash auto-cleared.
    expect(result.current.connectionState.status).toBe("connected");
    expect(result.current.connectionState.attempt).toBe(0);
  });

  // ── 2. Connection status transitions through "reconnecting" → "connected" ─
  it("transitions connection status to 'reconnecting' during backoff and back to 'connected' on resume", async () => {
    const mc = mockState.client!;
    const firstStream = streamThatThrows([metadataEvent], "socket hang up");
    // Use a controllable second stream so the test can hold the run open
    // and observe the "reconnecting" status snapshot before completion.
    const secondStream = createControllableStream();
    (mc.runs.stream as Mock).mockReturnValueOnce(firstStream);
    (mc.runs.joinStream as Mock).mockReturnValueOnce(secondStream);

    const { result } = renderHook(() => useAgent());
    expect(result.current.connectionState.status).toBe("connected");

    act(() => {
      result.current.submit("hello");
    });

    // Drain microtasks so the first stream errors and the reconnect loop
    // enters the backoff sleep — but only advance enough that the 1s timer
    // has NOT fired yet. The setConnectionState({status: "reconnecting"}) is
    // committed synchronously before the sleep, so checking after a 500ms
    // tick (well short of the 1000ms backoff) gives us the in-flight value.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(result.current.connectionState.status).toBe("reconnecting");
    expect(result.current.connectionState.attempt).toBe(1);

    // Finish the backoff. joinStream returns the controllable stream; emit
    // the completion event so the run finishes and status flips back.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    await act(async () => {
      await secondStream.emit(completionValuesEvent);
      secondStream.end();
      await vi.runAllTimersAsync();
    });
    // Settle the "Reconnected" flash timer.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
      await vi.runAllTimersAsync();
    });

    expect(result.current.connectionState.status).toBe("connected");
  });

  // ── 3. Hard error after max attempts → status "disconnected" ──────────────
  it("transitions to 'disconnected' after MAX_RECONNECT_ATTEMPTS consecutive failures", async () => {
    const mc = mockState.client!;

    // First stream gives us a run_id, then dies.
    const firstStream = streamThatThrows([metadataEvent], "boom");
    (mc.runs.stream as Mock).mockReturnValueOnce(firstStream);

    // Every subsequent joinStream attempt also dies, no events. The loop
    // should give up after MAX_RECONNECT_ATTEMPTS (8) attempts.
    (mc.runs.joinStream as Mock).mockImplementation(() =>
      streamThatThrows([], "still down"),
    );

    const { result } = renderHook(() => useAgent());

    act(() => {
      result.current.submit("doomed run");
    });

    // Walk all the way through the backoff schedule: 1+2+4+8+16+16+16+16 = 79s
    // plus a generous buffer for microtasks. We advance in big chunks.
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    for (let i = 0; i < 12; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
        await vi.runAllTimersAsync();
      });
    }

    // After exhausting attempts, status flips to "disconnected" and an error
    // surfaces. (joinStream should have been called MAX_RECONNECT_ATTEMPTS
    // times — the first failure on the original `runs.stream` counts as
    // failure #1, then joinStream gets called for attempts 1..MAX, so
    // joinStream is called MAX times before we give up at MAX+1.)
    expect(result.current.connectionState.status).toBe("disconnected");
    expect(result.current.error).toBeTruthy();
    // We never POST a second new run.
    expect((mc.runs.stream as Mock).mock.calls.length).toBe(1);
  });

  // ── 4. Clean stream completion never flips status ─────────────────────────
  it("leaves connection status 'connected' for a run that completes without drops", async () => {
    const mc = mockState.client!;
    const cleanStream = createMockStream([metadataEvent, completionValuesEvent]);
    (mc.runs.stream as Mock).mockReturnValueOnce(cleanStream);

    const { result } = renderHook(() => useAgent());

    act(() => {
      result.current.submit("a clean run");
    });
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    expect(result.current.connectionState.status).toBe("connected");
    expect(result.current.connectionState.attempt).toBe(0);
    expect((mc.runs.joinStream as Mock).mock.calls.length).toBe(0);
  });

  // ── 5. Operator abort during reconnect backoff bails out cleanly ──────────
  it("aborts the reconnect backoff when the operator cancels", async () => {
    const mc = mockState.client!;
    const firstStream = streamThatThrows([metadataEvent], "transient");
    (mc.runs.stream as Mock).mockReturnValueOnce(firstStream);
    // joinStream would be called next, but cancel should fire first.
    const lateStream = createControllableStream();
    (mc.runs.joinStream as Mock).mockReturnValueOnce(lateStream);

    const { result } = renderHook(() => useAgent());

    act(() => {
      result.current.submit("will cancel");
    });
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // We are now sleeping in the backoff. Cancel the run.
    act(() => {
      result.current.cancel();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await vi.runAllTimersAsync();
    });

    // Run state ends idle, error stays clear, and the cancel pathway took
    // priority over the reconnect path.
    expect(result.current.runState).toBe("idle");
  });
});
