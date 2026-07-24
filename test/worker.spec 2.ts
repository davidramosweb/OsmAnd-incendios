import { env } from "cloudflare:workers";
import {
  createExecutionContext,
  createScheduledController,
  waitOnExecutionContext,
} from "cloudflare:test";
import { describe, expect, it, vi } from "vitest";

import worker from "../src/index";

const IncomingRequest = Request<unknown, IncomingRequestCfProperties>;

describe("WORKER-001 scaffold", () => {
  it("serves /health from the Worker", async () => {
    const request = new IncomingRequest("https://example.test/health");
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("application/json");
    await expect(response.json()).resolves.toMatchObject({
      ok: true,
      phase: "WORKER-001",
    });
  });

  it("exposes the frozen geometry contract in /status.json", async () => {
    const request = new IncomingRequest("https://example.test/status.json");
    const ctx = createExecutionContext();
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);

    await expect(response.json()).resolves.toMatchObject({
      status: "scaffold",
      geometry_version:
        "sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
      covered_tiles: 9507,
      state_source: "provisional-no-kv-read",
    });
  });

  it("invokes scheduled() locally without side effects", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const controller = createScheduledController({
      cron: "7 * * * *",
      scheduledTime: new Date("2026-07-18T12:07:00Z"),
    });
    const ctx = createExecutionContext();

    await worker.scheduled(controller, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(log).toHaveBeenCalledOnce();
    expect(log.mock.calls[0]?.[0]).toContain('"effects":"none"');
    expect(await env.PREVIFOC_STATE.list()).toMatchObject({ keys: [] });
    log.mockRestore();
  });
});
