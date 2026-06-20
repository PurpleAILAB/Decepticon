import { afterEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";

const ENV: Env = { POSTHOG_KEY: "phc_test", POSTHOG_HOST: "https://ph.test" };

const VALID_BATCH = {
  schema_version: "1.0",
  tier: "A",
  install_id: "1e9a73a6-c8bd-4e1e-be02-78f4b11de4e1",
  client: { decepticon_version: "1.1.13", os: "linux" },
  events: [{ type: "tool.call", ts: 1718880000, tool: "nmap", status: "ok" }],
};

function post(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("https://gw.test/v1/telemetry", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

afterEach(() => vi.restoreAllMocks());

/** `.json()` is typed `unknown` under workers-types — cast for assertions. */
const body = async (r: Response): Promise<Record<string, unknown>> =>
  (await r.json()) as Record<string, unknown>;

const okFetch = () => vi.fn(async (_url: string, _init: RequestInit) => new Response("ok", { status: 200 }));

describe("telemetry gateway worker", () => {
  it("accepts a valid batch and forwards to PostHog (202)", async () => {
    const fetchMock = okFetch();
    vi.stubGlobal("fetch", fetchMock);

    const res = await worker.fetch(post(VALID_BATCH), ENV);
    expect(res.status).toBe(202);
    expect(await body(res)).toEqual({ accepted: 1 });

    // Forwarded exactly once, to the configured host, with the secret key.
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://ph.test/batch/");
    const sent = JSON.parse(init.body as string);
    expect(sent.api_key).toBe("phc_test");
    expect(sent.batch[0].event).toBe("tool.call");
    expect(sent.batch[0].distinct_id).toBe(VALID_BATCH.install_id);
    // Privacy: no IP anywhere in the forwarded payload.
    expect(JSON.stringify(sent)).not.toMatch(/cf-connecting|\bip\b/i);
  });

  it("rejects raw target IP with 422 and never forwards or echoes it", async () => {
    const fetchMock = okFetch();
    vi.stubGlobal("fetch", fetchMock);

    const leaky = {
      ...VALID_BATCH,
      events: [{ type: "tool.call", ts: 1, tool: "10.0.0.5" }],
    };
    const res = await worker.fetch(post(leaky), ENV);
    expect(res.status).toBe(422);
    const b = await body(res);
    expect(b.error).toBe("tier_c_content_rejected");
    expect(b.klass).toBe("ipv4");
    expect(JSON.stringify(b)).not.toContain("10.0.0.5"); // value never echoed
    expect(fetchMock).not.toHaveBeenCalled(); // never forwarded
  });

  it("rejects a trajectory step whose reasoning still leaks a raw IP (422)", async () => {
    const fetchMock = okFetch();
    vi.stubGlobal("fetch", fetchMock);
    const leaky = {
      ...VALID_BATCH,
      tier: "R",
      events: [{ type: "trajectory.step", ts: 1, role: "agent", text: "exploit 10.0.0.5 via SQLi" }],
    };
    const res = await worker.fetch(post(leaky), ENV);
    expect(res.status).toBe(422);
    const b = await body(res);
    expect(b.klass).toBe("ipv4");
    expect(JSON.stringify(b)).not.toContain("10.0.0.5");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a properly masked trajectory step (202)", async () => {
    const fetchMock = okFetch();
    vi.stubGlobal("fetch", fetchMock);
    const masked = {
      ...VALID_BATCH,
      tier: "R",
      events: [{ type: "trajectory.step", ts: 1, role: "agent", text: "exploit <HOST_1> via SQLi" }],
    };
    const res = await worker.fetch(post(masked), ENV);
    expect(res.status).toBe(202);
  });

  it("rejects an off-contract field with 400 (schema)", async () => {
    const fetchMock = okFetch();
    vi.stubGlobal("fetch", fetchMock);
    const res = await worker.fetch(post({ ...VALID_BATCH, raw_prompt: "secret" }), ENV);
    expect(res.status).toBe(400);
    expect((await body(res)).error).toBe("schema_validation_failed");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects non-JSON content-type with 415", async () => {
    const res = await worker.fetch(post(VALID_BATCH, { "content-type": "text/plain" }), ENV);
    expect(res.status).toBe(415);
  });

  it("rejects invalid JSON with 400", async () => {
    const res = await worker.fetch(post("{not json", {}), ENV);
    expect(res.status).toBe(400);
    expect((await body(res)).error).toBe("invalid_json");
  });

  it("rejects a GET on the ingest path with 405", async () => {
    const res = await worker.fetch(new Request("https://gw.test/v1/telemetry"), ENV);
    expect(res.status).toBe(405);
  });

  it("serves a health check on GET /", async () => {
    const res = await worker.fetch(new Request("https://gw.test/"), ENV);
    expect(res.status).toBe(200);
    expect((await body(res)).ok).toBe(true);
  });

  it("returns 502 when PostHog is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    const res = await worker.fetch(post(VALID_BATCH), ENV);
    expect(res.status).toBe(502);
  });

  it("enforces the rate limiter when bound (429)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("ok", { status: 200 })));
    const env: Env = { ...ENV, RATE_LIMITER: { limit: async () => ({ success: false }) } };
    const res = await worker.fetch(post(VALID_BATCH), env);
    expect(res.status).toBe(429);
  });
});
