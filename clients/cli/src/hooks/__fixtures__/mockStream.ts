import { vi } from "vitest";

export type StreamEvent = { event: string; data: unknown };

/**
 * Simple variant — yields every event in sequence with a microtask break
 * between each so React can batch state updates before the next event lands.
 */
export function createMockStream(events: StreamEvent[]): AsyncIterable<StreamEvent> {
  return {
    async *[Symbol.asyncIterator]() {
      for (const e of events) {
        await Promise.resolve();
        yield e;
      }
    },
  };
}

/**
 * Controllable variant — the test drives events one at a time and decides
 * when the stream ends. Use with `await act(async () => stream.emit(...))` so
 * React commits between each event before the next assertion.
 */
export interface ControllableStream extends AsyncIterable<StreamEvent> {
  /** Release one event to the consumer. Resolves after the consumer has pulled it. */
  emit(event: StreamEvent): Promise<void>;
  /** Signal end of stream — causes the iterator to return normally. */
  end(): void;
}

export function createControllableStream(): ControllableStream {
  type PendingResolve = (value: IteratorResult<StreamEvent>) => void;

  // Queue of events waiting to be consumed.
  const eventQueue: IteratorResult<StreamEvent>[] = [];
  // Resolve functions for each consumer `next()` call that arrived before an event.
  const waiters: PendingResolve[] = [];
  let done = false;

  function deliver(result: IteratorResult<StreamEvent>): void {
    if (waiters.length > 0) {
      // Consumer is already waiting — satisfy immediately.
      const resolve = waiters.shift()!;
      resolve(result);
    } else {
      // Consumer hasn't called next() yet — buffer the result.
      eventQueue.push(result);
    }
  }

  const iterable: ControllableStream = {
    async emit(event: StreamEvent): Promise<void> {
      deliver({ value: event, done: false });
      // Yield to the microtask queue so the async-iterator consumer has a
      // chance to pull the value before this promise settles.
      await Promise.resolve();
      await Promise.resolve();
    },

    end(): void {
      done = true;
      deliver({ value: undefined as unknown as StreamEvent, done: true });
    },

    [Symbol.asyncIterator](): AsyncIterator<StreamEvent> {
      return {
        next(): Promise<IteratorResult<StreamEvent>> {
          if (eventQueue.length > 0) {
            return Promise.resolve(eventQueue.shift()!);
          }
          if (done) {
            return Promise.resolve({ value: undefined as unknown as StreamEvent, done: true });
          }
          return new Promise<IteratorResult<StreamEvent>>((resolve) => {
            waiters.push(resolve);
          });
        },
      };
    },
  };

  return iterable;
}

export type MockClient = {
  threads: {
    create: ReturnType<typeof vi.fn>;
    getState: ReturnType<typeof vi.fn>;
  };
  runs: {
    stream: ReturnType<typeof vi.fn>;
    cancel: ReturnType<typeof vi.fn>;
  };
};

let _threadCounter = 0;

export function createMockClient(): MockClient {
  const threadId = `thread-${++_threadCounter}`;
  return {
    threads: {
      create: vi.fn(async () => ({ thread_id: threadId })),
      getState: vi.fn(async () => ({ values: {} })),
    },
    runs: {
      stream: vi.fn(() => createMockStream([])),
      cancel: vi.fn(async () => {}),
    },
  };
}
