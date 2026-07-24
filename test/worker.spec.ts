import { env } from "cloudflare:workers";
import {
  createExecutionContext,
  createScheduledController,
  waitOnExecutionContext,
} from "cloudflare:test";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createWorker,
  runScheduledUpdate,
} from "../src/index";
import {
  normalizeCurrentStateCandidate,
  PrevifocIngestionError,
  type CurrentStateCandidate,
  type IngestionErrorCode,
} from "../src/previfoc";
import {
  CURRENT_STATE_KEY,
  CurrentStateRepository,
  publishCurrentState,
} from "../src/state";
import {
  cloneFixture,
  validPrevifocFixture,
  validSituacionFixture,
} from "./fixtures/previfoc";

const IncomingRequest = Request<unknown, IncomingRequestCfProperties>;
const fixedNow = new Date("2026-07-18T12:00:00.000Z");
const provenance: CurrentStateCandidate["provenance"] = {
  previfoc: {
    source: "previfoc",
    requestedUrl: "https://example.test/previfoc",
    responseUrl: "https://example.test/previfoc",
    retrievedAt: "2026-07-18T08:00:00.000Z",
    attempts: 1,
  },
  situacion: {
    source: "situacion",
    requestedUrl: "https://example.test/situacion",
    responseUrl: "https://example.test/situacion",
    retrievedAt: "2026-07-18T08:00:01.000Z",
    attempts: 1,
  },
};

function candidate(sourceDate = "2026-07-18"): CurrentStateCandidate {
  const previfoc = cloneFixture(validPrevifocFixture);
  previfoc.time = `${sourceDate} 00:01:41.0`;
  return normalizeCurrentStateCandidate(
    previfoc,
    validSituacionFixture,
    provenance,
  );
}

async function request(
  pathname: string,
  worker = createWorker({ now: () => fixedNow }),
) {
  const ctx = createExecutionContext();
  const response = await worker.fetch(
    new IncomingRequest(`https://example.test${pathname}`),
    env,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return response;
}

async function sha256(response: Response): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function deployRefreshRequest(
  token: string | undefined,
  worker = createWorker({
    ingest: async () => candidate(),
    now: () => fixedNow,
  }),
) {
  const ctx = createExecutionContext();
  const requestHeaders = token === undefined
    ? undefined
    : { authorization: `Bearer ${token}` };
  const response = await worker.fetch(
    new IncomingRequest("https://example.test/internal/deploy-refresh", {
      method: "POST",
      headers: requestHeaders,
    }),
    {
      PREVIFOC_STATE: env.PREVIFOC_STATE,
      ASSETS: env.ASSETS,
      DEPLOY_HOOK_TOKEN: "test-deploy-hook-token",
    },
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return response;
}

describe("WORKER-003 scheduled publication", () => {
  beforeEach(async () => {
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
  });

  it("connects the scheduled workflow and publishes current", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const worker = createWorker({
      ingest: async () => candidate(),
      now: () => fixedNow,
    });
    const controller = createScheduledController({
      cron: "7 * * * *",
      scheduledTime: new Date("2026-07-18T12:07:00.000Z"),
    });
    const ctx = createExecutionContext();

    await worker.scheduled(controller, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(await env.PREVIFOC_STATE.list()).toMatchObject({
      keys: [{ name: CURRENT_STATE_KEY }],
    });
    expect(info).toHaveBeenCalledOnce();
    expect(info.mock.calls[0]?.[0]).toContain('"outcome":"published"');
    info.mockRestore();
  });

  it.each<[IngestionErrorCode, "previfoc" | "situacion"]>([
    ["FETCH_FAILED", "previfoc"],
    ["HTTP_STATUS", "previfoc"],
    ["INVALID_SITUATION_CATALOG", "situacion"],
  ])("preserves the last valid state after %s", async (code, source) => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    await publishCurrentState(repository, candidate(), () => fixedNow);
    const before = await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY);
    const secret = "complete-upstream-body-and-token";
    const warning = vi
      .spyOn(console, "warn")
      .mockImplementation(() => undefined);
    const worker = createWorker({
      ingest: async () => {
        throw new PrevifocIngestionError(code, secret, source);
      },
    });
    const controller = createScheduledController({
      cron: "7 * * * *",
      scheduledTime: fixedNow,
    });
    const ctx = createExecutionContext();

    await worker.scheduled(controller, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY)).toBe(before);
    expect(warning).toHaveBeenCalledOnce();
    const log = String(warning.mock.calls[0]?.[0]);
    expect(log).toContain(`"error_code":"${code}"`);
    expect(log).toContain('"outcome":"preserved_last_valid"');
    expect(log).not.toContain(secret);
    expect(log).not.toContain("zones");
    warning.mockRestore();
  });

  it("exposes the orchestration result for an unchanged recovery", async () => {
    await expect(
      runScheduledUpdate(env, {
        ingest: async () => candidate(),
        now: () => fixedNow,
      }),
    ).resolves.toBe("published");
    const put = vi.spyOn(env.PREVIFOC_STATE, "put");
    await expect(
      runScheduledUpdate(env, {
        ingest: async () => candidate(),
        now: () => new Date("2026-07-18T13:00:00.000Z"),
      }),
    ).resolves.toBe("unchanged");
    expect(put).not.toHaveBeenCalled();
    put.mockRestore();
  });
});

describe("post-deployment refresh", () => {
  beforeEach(async () => {
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
  });

  it("rejects requests without the deploy token", async () => {
    const response = await deployRefreshRequest(undefined);
    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toEqual({
      ok: false,
      error_code: "UNAUTHORIZED",
    });
  });

  it("publishes immediately with the deploy token", async () => {
    const response = await deployRefreshRequest("test-deploy-hook-token");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      ok: true,
      outcome: "published",
    });
    await expect(
      new CurrentStateRepository(env.PREVIFOC_STATE).readCurrent(),
    ).resolves.toMatchObject({
      schemaVersion: 2,
      forecastNextDay: { validDate: "2026-07-19" },
    });
  });

  it("preserves the current state and fails the hook on ingestion errors", async () => {
    const worker = createWorker({
      ingest: async () => {
        throw new PrevifocIngestionError(
          "FETCH_FAILED",
          "upstream request failed",
          "previfoc",
        );
      },
    });
    const response = await deployRefreshRequest("test-deploy-hook-token", worker);
    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toMatchObject({
      ok: false,
      outcome: "preserved_last_valid",
      error_code: "FETCH_FAILED",
      source: "previfoc",
    });
  });
});

describe("WORKER-003 HTTP state contracts", () => {
  beforeEach(async () => {
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
  });

  it("returns cached 503 JSON when status has never been published", async () => {
    const response = await request("/status.json");
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toBe("public, max-age=300");
    await expect(response.json()).resolves.toEqual({
      ok: false,
      status: "unavailable",
      reason: "not_published",
    });
  });

  it("returns current and stale status without persisting isStale", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    await publishCurrentState(repository, candidate(), () => fixedNow);

    const current = await request("/status.json");
    expect(current.status).toBe(200);
    expect(current.headers.get("cache-control")).toBe("public, max-age=300");
    await expect(current.json()).resolves.toMatchObject({
      schemaVersion: 2,
      sourceTimestampOriginal: "2026-07-18 00:01:41.0",
      isStale: false,
      forecastNextDay: {
        validDate: "2026-07-19",
        isStale: false,
      },
    });
    expect(await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY)).not.toContain(
      "isStale",
    );

    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
    await publishCurrentState(
      repository,
      candidate("2026-07-17"),
      () => fixedNow,
    );
    const stale = await request("/status.json");
    expect(stale.status).toBe(200);
    await expect(stale.json()).resolves.toMatchObject({ isStale: true });
  });

  it("returns health 200 only for Madrid's current date and never caches it", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);

    const missing = await request("/health");
    expect(missing.status).toBe(503);
    expect(missing.headers.get("cache-control")).toBe("no-store");

    await publishCurrentState(
      repository,
      candidate("2026-07-17"),
      () => fixedNow,
    );
    const stale = await request("/health");
    expect(stale.status).toBe(503);
    expect(stale.headers.get("cache-control")).toBe("no-store");
    await expect(stale.json()).resolves.toMatchObject({
      ok: false,
      status: "stale",
    });

    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
    await publishCurrentState(repository, candidate(), () => fixedNow);
    const current = await request("/health");
    expect(current.status).toBe(200);
    expect(current.headers.get("cache-control")).toBe("no-store");
    await expect(current.json()).resolves.toMatchObject({
      ok: true,
      status: "current",
      currentDateMadrid: "2026-07-18",
    });
  });

  it("returns 503 and explicitly identifies an incompatible stored schema", async () => {
    await env.PREVIFOC_STATE.put(
      CURRENT_STATE_KEY,
      JSON.stringify({ schemaVersion: 3 }),
    );
    const status = await request("/status.json");
    expect(status.status).toBe(503);
    await expect(status.json()).resolves.toMatchObject({
      reason: "incompatible_schema_version",
    });
    const health = await request("/health");
    expect(health.status).toBe(503);
    expect(health.headers.get("cache-control")).toBe("no-store");
  });
});

describe("WORKER-003 inherited asset routing", () => {
  it("hands a covered tile to WORKER-004's safe gray mode", async () => {
    const response = await request("/tiles/6/31/24.png");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    expect(response.headers.get("x-previfoc-stale")).toBe("true");
    await expect(sha256(response)).resolves.toBe(
      "775694210c1c87482f9cff30217c0a407ce64f6419705adbf9e35045497055c4",
    );
  });

  it("uses the frozen transparent tile for a valid uncovered XYZ", async () => {
    const response = await request("/tiles/6/0/0.png");
    expect(response.status).toBe(200);
    await expect(sha256(response)).resolves.toBe(
      "679644f8ef3768bbe373bc2db7d50c3d9f133013cb927154fc920a4471616809",
    );
  });

  it("serves WEB-001 at both the public root and its asset path", async () => {
    const [root, asset] = await Promise.all([
      request("/"),
      request("/index.html"),
    ]);
    expect(root.status).toBe(200);
    expect(root.headers.get("content-type")).toContain("text/html");
    expect(asset.status).toBe(200);
    expect(await root.text()).toBe(await asset.text());

    const htmlResponse = await request("/");
    const html = (await htmlResponse.text()).replace(/\s+/g, " ");
    expect(html).toContain("PREVIFOC para OsmAnd");
    expect(html).toContain(
      "Servicio no oficial.</strong> Criterio preventivo propio: cuando PREVIFOC publica nivel 3",
    );
    expect(html).toContain(
      "Los niveles 1 y 2 no confirman que una vía esté abierta.",
    );
    expect(html.match(/data-zone-id=/g)).toHaveLength(7);
    expect(html).toContain('href="/previfoc.osf"');
    expect(html).toContain('href="https://www.112cv.gva.es/es/incendios-forestales"');
    expect(html).toContain("Institut Cartogràfic Valencià / Generalitat Valenciana");
    expect(html).toContain("CC BY 4.0");
    expect(html).toContain('data-period="forecast_next_day"');
    expect(html).toContain("Paquete versión 2.0.0");
    expect(html).toContain("<noscript>");
  });

  it("serves the progressive enhancement assets without third-party code", async () => {
    const css = await request("/styles.css");
    expect(css.status).toBe(200);
    expect(css.headers.get("content-type")).toContain("text/css");
    expect(await css.text()).toContain("prefers-reduced-motion");

    const script = await request("/app.js");
    expect(script.status).toBe(200);
    expect(script.headers.get("content-type")).toContain("javascript");
    const javascript = await script.text();
    expect(javascript).toContain('fetch("/status.json"');
    expect(javascript).toContain("EXPECTED_ZONE_IDS = [53, 54, 55, 56, 57, 58, 59]");
    expect(javascript).toContain("status-card--stale");
    expect(javascript).not.toMatch(/https?:\/\//);
  });

  it("serves the frozen OSMAND-003 installer byte for byte", async () => {
    const response = await request("/previfoc.osf");
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/octet-stream");
    expect(response.headers.get("content-disposition")).toBe(
      'attachment; filename="previfoc.osf"',
    );
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    await expect(sha256(response)).resolves.toBe(
      "a1076e107b9427d992e9c71c0c96575f6c7ddd5a80d889f4b7883c85b17204fd",
    );
  });
});
