import { describe, it, expect } from "vitest";
import {
  nextBackoffMs,
  BACKOFF_SCHEDULE_MS,
  BACKOFF_CAP_MS,
  MAX_RECONNECT_ATTEMPTS,
} from "./useReconnect.js";

describe("nextBackoffMs", () => {
  it("returns 0 when no failures yet (initial connect)", () => {
    expect(nextBackoffMs(0)).toBe(0);
  });

  it("treats negative input as 'no failures yet' (defensive)", () => {
    expect(nextBackoffMs(-1)).toBe(0);
    expect(nextBackoffMs(-100)).toBe(0);
  });

  it("follows the documented schedule 1/2/4/8/16 seconds", () => {
    expect(nextBackoffMs(1)).toBe(1000);
    expect(nextBackoffMs(2)).toBe(2000);
    expect(nextBackoffMs(3)).toBe(4000);
    expect(nextBackoffMs(4)).toBe(8000);
    expect(nextBackoffMs(5)).toBe(16000);
  });

  it("caps at 16s for any further failures", () => {
    expect(nextBackoffMs(6)).toBe(16000);
    expect(nextBackoffMs(7)).toBe(16000);
    expect(nextBackoffMs(100)).toBe(16000);
  });
});

describe("backoff constants", () => {
  it("exposes the exact schedule the spec mandates", () => {
    expect([...BACKOFF_SCHEDULE_MS]).toEqual([1000, 2000, 4000, 8000, 16000]);
  });

  it("cap equals the last entry in the schedule", () => {
    expect(BACKOFF_CAP_MS).toBe(16000);
    expect(BACKOFF_SCHEDULE_MS[BACKOFF_SCHEDULE_MS.length - 1]).toBe(
      BACKOFF_CAP_MS,
    );
  });

  it("max attempts is a positive integer", () => {
    expect(Number.isInteger(MAX_RECONNECT_ATTEMPTS)).toBe(true);
    expect(MAX_RECONNECT_ATTEMPTS).toBeGreaterThan(0);
  });
});
