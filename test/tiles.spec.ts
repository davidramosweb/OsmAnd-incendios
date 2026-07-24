import { env } from "cloudflare:workers";
import {
  createExecutionContext,
  waitOnExecutionContext,
} from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";

import { createWorker } from "../src/index";
import {
  normalizeCurrentStateCandidate,
  type CurrentStateCandidate,
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

function candidate(sourceDate = "2026-07-18", zone53Situation = 1) {
  const previfoc = cloneFixture(validPrevifocFixture);
  previfoc.time = `${sourceDate} 00:01:41.0`;
  previfoc.z1.find((zone) => zone.id === 53)!.nact = zone53Situation;
  return normalizeCurrentStateCandidate(
    previfoc,
    validSituacionFixture,
    provenance,
  );
}

function key(request: RequestInfo | URL): string {
  if (request instanceof Request) return request.url;
  return String(request);
}

function memoryCache() {
  const entries = new Map<string, Response>();
  const matched: string[] = [];
  const stored: string[] = [];
  const cache = {
    async match(request: RequestInfo | URL) {
      const requestKey = key(request);
      matched.push(requestKey);
      return entries.get(requestKey)?.clone();
    },
    async put(request: RequestInfo | URL, response: Response) {
      const requestKey = key(request);
      stored.push(requestKey);
      entries.set(requestKey, response.clone());
    },
    async delete(request: RequestInfo | URL) {
      return entries.delete(key(request));
    },
  } as Cache;
  return { cache, entries, matched, stored };
}

async function sha256(response: Response): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function request(
  pathname: string,
  options: Parameters<typeof createWorker>[0],
  init?: RequestInit<IncomingRequestCfProperties>,
  workerEnv: Env = env,
) {
  const ctx = createExecutionContext();
  const response = await createWorker(options).fetch(
    new IncomingRequest(`https://example.test${pathname}`, init),
    workerEnv,
    ctx,
  );
  await waitOnExecutionContext(ctx);
  return response;
}

describe("WORKER-004 dynamic XYZ tiles", () => {
  beforeEach(async () => {
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
  });

  it("serves a mixed current palette with the final headers", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const published = await publishCurrentState(repository, candidate(), () => fixedNow);
    const { cache } = memoryCache();

    const response = await request("/tiles/6/31/24.png", {
      now: () => fixedNow,
      cache,
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("image/png");
    expect(response.headers.get("cache-control")).toBe("public, max-age=3600");
    expect(response.headers.get("x-previfoc-stale")).toBe("false");
    expect(response.headers.get("x-previfoc-period")).toBe("current");
    expect(response.headers.get("x-previfoc-valid-date")).toBe("2026-07-18");
    expect(response.headers.get("x-previfoc-snapshot")).toBe(
      published.state.snapshotId,
    );
    expect(response.headers.get("etag")).toContain("-6-31-24");
    await expect(sha256(response)).resolves.toBe(
      "2e38eb8a32b89a887f021b308dba63f204a7364cdbb0e9fcba5c33fbda1d2738",
    );
  });

  it("uses gray only when state is absent or malformed and preserves stale colors", async () => {
    const absent = await request("/tiles/6/31/24.png", {
      now: () => fixedNow,
      cache: memoryCache().cache,
    });
    expect(absent.headers.get("x-previfoc-stale")).toBe("true");
    expect(absent.headers.has("x-previfoc-snapshot")).toBe(false);
    await expect(sha256(absent)).resolves.toBe(
      "775694210c1c87482f9cff30217c0a407ce64f6419705adbf9e35045497055c4",
    );

    await env.PREVIFOC_STATE.put(CURRENT_STATE_KEY, "not-json");
    const malformed = await request("/tiles/6/31/24.png", {
      now: () => fixedNow,
      cache: memoryCache().cache,
    });
    await expect(sha256(malformed)).resolves.toBe(
      "775694210c1c87482f9cff30217c0a407ce64f6419705adbf9e35045497055c4",
    );

    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
    const published = await publishCurrentState(
      new CurrentStateRepository(env.PREVIFOC_STATE),
      candidate("2026-07-17"),
      () => fixedNow,
    );
    const obsolete = await request("/tiles/6/31/24.png", {
      now: () => fixedNow,
      cache: memoryCache().cache,
    });
    expect(obsolete.headers.get("x-previfoc-snapshot")).toBe(
      published.state.snapshotId,
    );
    expect(obsolete.headers.get("x-previfoc-stale")).toBe("true");
    await expect(sha256(obsolete)).resolves.toBe(
      "2e38eb8a32b89a887f021b308dba63f204a7364cdbb0e9fcba5c33fbda1d2738",
    );
  });

  it("serves explicit today and hatched forecast routes from separate caches", async () => {
    const published = await publishCurrentState(
      new CurrentStateRepository(env.PREVIFOC_STATE),
      candidate(),
      () => fixedNow,
    );
    const cacheState = memoryCache();
    const options = { now: () => fixedNow, cache: cacheState.cache };
    const legacy = await request("/tiles/6/31/24.png", options);
    const current = await request("/tiles/current/6/31/24.png", options);
    const forecast = await request("/tiles/forecast-next-day/6/31/24.png", options);

    const legacyHash = await sha256(legacy);
    const currentHash = await sha256(current);
    const forecastHash = await sha256(forecast);
    expect(currentHash).toBe(legacyHash);
    expect(forecastHash).not.toBe(currentHash);
    expect(forecast.headers.get("x-previfoc-period")).toBe("forecast_next_day");
    expect(forecast.headers.get("x-previfoc-valid-date")).toBe("2026-07-19");
    expect(forecast.headers.get("x-previfoc-snapshot")).toBe(published.state.snapshotId);
    expect(cacheState.stored.some((key) => key.includes("forecast_next_day"))).toBe(true);
  });

  it("keeps the frozen transparent PNG for a valid uncovered coordinate", async () => {
    const response = await request("/tiles/6/0/0.png", {
      now: () => fixedNow,
      cache: memoryCache().cache,
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("x-previfoc-stale")).toBe("true");
    await expect(sha256(response)).resolves.toBe(
      "679644f8ef3768bbe373bc2db7d50c3d9f133013cb927154fc920a4471616809",
    );
  });

  it("reuses a warm cache and changes its key immediately with the snapshot", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    await publishCurrentState(repository, candidate(), () => fixedNow);
    const cacheState = memoryCache();
    let assetFetches = 0;
    const workerEnv = {
      PREVIFOC_STATE: env.PREVIFOC_STATE,
      ASSETS: {
        async fetch(assetRequest: Request) {
          assetFetches += 1;
          return env.ASSETS.fetch(assetRequest);
        },
      } as unknown as Fetcher,
    } as Env;
    const options = { now: () => fixedNow, cache: cacheState.cache };

    const cold = await request("/tiles/6/31/24.png", options, undefined, workerEnv);
    const warm = await request("/tiles/6/31/24.png", options, undefined, workerEnv);
    expect(assetFetches).toBe(1);
    expect(cacheState.stored).toHaveLength(1);
    expect(await sha256(warm)).toBe(await sha256(cold));

    await publishCurrentState(repository, candidate("2026-07-18", 4), () => fixedNow);
    const changed = await request("/tiles/6/31/24.png", options, undefined, workerEnv);
    expect(assetFetches).toBe(2);
    expect(cacheState.stored).toHaveLength(2);
    expect(cacheState.stored[1]).not.toBe(cacheState.stored[0]);
    expect(changed.headers.get("etag")).not.toBe(cold.headers.get("etag"));
  });

  it("changes the gray cache namespace at Madrid's next local date", async () => {
    await publishCurrentState(
      new CurrentStateRepository(env.PREVIFOC_STATE),
      candidate("2026-07-17"),
      () => fixedNow,
    );
    let now = new Date("2026-07-18T21:59:59.000Z");
    const cacheState = memoryCache();
    const options = { now: () => now, cache: cacheState.cache };

    await request("/tiles/6/31/24.png", options);
    now = new Date("2026-07-18T22:00:00.000Z");
    await request("/tiles/6/31/24.png", options);

    expect(cacheState.stored).toHaveLength(2);
    expect(cacheState.stored[0]).toContain("stale-2026-07-18");
    expect(cacheState.stored[1]).toContain("stale-2026-07-19");
  });

  it("supports HEAD and conditional ETag requests", async () => {
    const cache = memoryCache().cache;
    const get = await request("/tiles/6/31/24.png", {
      now: () => fixedNow,
      cache,
    });
    const etag = get.headers.get("etag")!;
    const head = await request(
      "/tiles/6/31/24.png",
      { now: () => fixedNow, cache },
      { method: "HEAD" },
    );
    expect(head.status).toBe(200);
    expect(head.headers.get("content-length")).toBe(get.headers.get("content-length"));
    expect((await head.arrayBuffer()).byteLength).toBe(0);

    const conditional = await request(
      "/tiles/6/31/24.png",
      { now: () => fixedNow, cache },
      { headers: { "if-none-match": etag } },
    );
    expect(conditional.status).toBe(304);
    expect((await conditional.arrayBuffer()).byteLength).toBe(0);
  });

  it("rejects invalid XYZ and methods before touching assets", async () => {
    let assetFetches = 0;
    const workerEnv = {
      PREVIFOC_STATE: env.PREVIFOC_STATE,
      ASSETS: {
        async fetch() {
          assetFetches += 1;
          return new Response(null, { status: 500 });
        },
      } as unknown as Fetcher,
    } as Env;
    const options = { now: () => fixedNow, cache: memoryCache().cache };

    for (const path of [
      "/tiles/5/0/0.png",
      "/tiles/15/0/0.png",
      "/tiles/6/64/0.png",
      "/tiles/6/0/64.png",
      "/tiles/6/-1/0.png",
      "/tiles/6/31/../secret.png",
      "/tiles/6/31/24.png/extra",
      "/tiles/tomorrow/6/31/24.png",
      "/tiles/forecast-next-day/15/0/0.png",
    ]) {
      const response = await request(path, options, undefined, workerEnv);
      expect(response.status).toBe(404);
    }
    const method = await request(
      "/tiles/6/31/24.png",
      options,
      { method: "POST" },
      workerEnv,
    );
    expect(method.status).toBe(405);
    expect(method.headers.get("allow")).toBe("GET, HEAD");
    expect(assetFetches).toBe(0);
  });
});
