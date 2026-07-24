import {
  ingestCurrentStateCandidate,
  PrevifocIngestionError,
  type CurrentStateCandidate,
} from "./previfoc";
import {
  CurrentStateRepository,
  dateInMadrid,
  isStateStale,
  nextCalendarDate,
  sourceDateFromTimestamp,
  type ReadableCurrentState,
  publishCurrentState,
  StateRepositoryError,
} from "./state";
import {
  LEVEL_COLORS,
  recolorIndexedPng,
  STALE_COLOR,
  type TileStyle,
  type Rgb,
} from "./png";

const CRON = "7 * * * *";
const DEPLOY_REFRESH_PATH = "/internal/deploy-refresh";

type PrevifocEnv = Env & {
  DEPLOY_HOOK_TOKEN?: string;
};

function jsonResponse(
  value: unknown,
  request: Request,
  status = 200,
  cacheControl = "no-store",
): Response {
  const body = request.method === "HEAD" ? null : JSON.stringify(value, null, 2);
  return new Response(body, {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": cacheControl,
    },
  });
}

function methodNotAllowed(): Response {
  return new Response("Method not allowed\n", {
    status: 405,
    headers: { allow: "GET, HEAD", "cache-control": "no-store" },
  });
}

function postMethodNotAllowed(): Response {
  return new Response("Method not allowed\n", {
    status: 405,
    headers: { allow: "POST", "cache-control": "no-store" },
  });
}

async function tokensMatch(actual: string, expected: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [actualDigest, expectedDigest] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(actual)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const actualBytes = new Uint8Array(actualDigest);
  const expectedBytes = new Uint8Array(expectedDigest);
  let difference = 0;
  for (let index = 0; index < actualBytes.length; index += 1) {
    difference |= actualBytes[index]! ^ expectedBytes[index]!;
  }
  return difference === 0;
}

async function serveDeployRefresh(
  request: Request,
  env: PrevifocEnv,
  options: ScheduledUpdateOptions,
): Promise<Response> {
  if (request.method !== "POST") return postMethodNotAllowed();

  const expectedToken = env.DEPLOY_HOOK_TOKEN;
  if (!expectedToken) {
    return jsonResponse(
      { ok: false, error_code: "DEPLOY_HOOK_NOT_CONFIGURED" },
      request,
      503,
    );
  }
  const authorization = request.headers.get("authorization") ?? "";
  const actualToken = authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : "";
  if (!(await tokensMatch(actualToken, expectedToken))) {
    return jsonResponse(
      { ok: false, error_code: "UNAUTHORIZED" },
      request,
      401,
    );
  }

  try {
    const outcome = await runScheduledUpdate(env, options);
    console.info(JSON.stringify({ event: "previfoc_deploy_refresh", outcome }));
    return jsonResponse({ ok: true, outcome }, request);
  } catch (error) {
    console.warn(
      JSON.stringify({
        event: "previfoc_deploy_refresh",
        outcome: "preserved_last_valid",
        ...safeScheduledError(error),
      }),
    );
    return jsonResponse(
      {
        ok: false,
        outcome: "preserved_last_valid",
        ...safeScheduledError(error),
      },
      request,
      502,
    );
  }
}

async function serveOsmandPackage(request: Request, env: Env): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return methodNotAllowed();
  }
  const packageUrl = new URL("/previfoc.osf", request.url);
  const asset = await env.ASSETS.fetch(new Request(packageUrl, { method: "GET" }));
  if (!asset.ok) return asset;

  const headers = new Headers(asset.headers);
  headers.set("content-type", "application/octet-stream");
  headers.set("content-disposition", 'attachment; filename="previfoc.osf"');
  headers.set("x-content-type-options", "nosniff");
  headers.set("cache-control", "public, max-age=3600, must-revalidate");
  return new Response(request.method === "HEAD" ? null : asset.body, {
    status: asset.status,
    headers,
  });
}

export interface TileCoordinates {
  zoom: number;
  x: number;
  y: number;
}

export type TilePeriod = "current" | "forecast_next_day";

interface TileRequest extends TileCoordinates {
  period: TilePeriod;
}

function parseTileRequest(pathname: string): TileRequest | null {
  const match =
    /^\/tiles\/(?:(current|forecast-next-day)\/)?(\d+)\/(\d+)\/(\d+)\.png$/.exec(
      pathname,
    );
  if (!match) return null;
  const period: TilePeriod = match[1] === "forecast-next-day"
    ? "forecast_next_day"
    : "current";
  const zoom = Number(match[2]);
  const x = Number(match[3]);
  const y = Number(match[4]);
  if (zoom < 6 || zoom > 14) return null;
  const extent = 2 ** zoom;
  return x >= 0 && x < extent && y >= 0 && y < extent
    ? { period, zoom, x, y }
    : null;
}

export function parseTilePath(pathname: string): TileCoordinates | null {
  const request = parseTileRequest(pathname);
  return request === null
    ? null
    : { zoom: request.zoom, x: request.x, y: request.y };
}

interface TileState {
  cacheTag: string;
  etag: string;
  snapshotId?: string;
  stale: boolean;
  period: TilePeriod;
  validDate: string;
  style: TileStyle;
  colors: readonly Rgb[];
}

function tileState(
  state: ReadableCurrentState | null,
  now: Date,
  request: TileRequest,
): TileState {
  const localDate = dateInMadrid(now);
  const forecast = state?.schemaVersion === 2
    ? state.forecastNextDay
    : null;
  const periodZones = request.period === "current" ? state?.zones : forecast?.zones;
  const validDate = request.period === "current"
    ? state === null
      ? localDate
      : sourceDateFromTimestamp(state.sourceTimestampOriginal)
    : forecast?.validDate ?? nextCalendarDate(localDate);
  const stale = state === null || periodZones === undefined || isStateStale(state, now);
  const cacheTag = state === null || periodZones === undefined
    ? `unavailable:${request.period}:${localDate}`
    : `${state.snapshotId}:${request.period}:${stale ? `stale-${localDate}` : "current"}`;
  const representation = cacheTag.replaceAll(":", "-");
  return {
    cacheTag,
    etag: `"${representation}-${request.zoom}-${request.x}-${request.y}"`,
    snapshotId: periodZones === undefined ? undefined : state?.snapshotId,
    stale,
    period: request.period,
    validDate,
    style: request.period === "forecast_next_day" ? "forecast_hatch" : "solid",
    colors: periodZones === undefined
      ? Array<Rgb>(7).fill(STALE_COLOR)
      : periodZones.map((zone) => LEVEL_COLORS[zone.level]),
  };
}

async function readTileState(
  env: Env,
  now: Date,
  request: TileRequest,
): Promise<TileState> {
  try {
    const state = await new CurrentStateRepository(env.PREVIFOC_STATE).readCurrent();
    return tileState(state, now, request);
  } catch {
    return tileState(null, now, request);
  }
}

function internalCacheRequest(
  state: TileState,
  coordinates: TileCoordinates,
): Request {
  const tag = encodeURIComponent(state.cacheTag);
  return new Request(
    `https://previfoc-tile-cache.invalid/v1/${tag}/${coordinates.zoom}/${coordinates.x}/${coordinates.y}.png`,
  );
}

function tileHeaders(state: TileState, contentLength?: number): Headers {
  const headers = new Headers({
    "content-type": "image/png",
    "cache-control": "public, max-age=3600",
    etag: state.etag,
    "x-previfoc-stale": String(state.stale),
    "x-previfoc-period": state.period,
    "x-previfoc-valid-date": state.validDate,
  });
  if (state.snapshotId !== undefined) {
    headers.set("x-previfoc-snapshot", state.snapshotId);
  }
  if (contentLength !== undefined) {
    headers.set("content-length", String(contentLength));
  }
  return headers;
}

function publicTileResponse(
  body: BodyInit | null,
  request: Request,
  state: TileState,
  contentLength?: number,
): Response {
  return new Response(request.method === "HEAD" ? null : body, {
    status: 200,
    headers: tileHeaders(state, contentLength),
  });
}

function notModifiedTileResponse(state: TileState): Response {
  return new Response(null, { status: 304, headers: tileHeaders(state) });
}

function requestAcceptsEtag(request: Request, etag: string): boolean {
  const value = request.headers.get("if-none-match");
  return value !== null &&
    value.split(",").some((candidate) => {
      const normalized = candidate.trim();
      return normalized === "*" || normalized === etag;
    });
}

async function serveTile(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  now: Date,
  cache: Cache,
): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return methodNotAllowed();
  }

  const pathname = new URL(request.url).pathname;
  const tileRequest = parseTileRequest(pathname);
  if (tileRequest === null) {
    return new Response("Tile not found\n", {
      status: 404,
      headers: { "cache-control": "no-store" },
    });
  }

  const coordinates: TileCoordinates = tileRequest;
  const state = await readTileState(env, now, tileRequest);
  if (requestAcceptsEtag(request, state.etag)) {
    return notModifiedTileResponse(state);
  }

  const cacheRequest = internalCacheRequest(state, coordinates);
  let cached: Response | undefined;
  try {
    cached = await cache.match(cacheRequest);
  } catch {
    cached = undefined;
  }
  if (cached !== undefined) {
    const length = Number(cached.headers.get("content-length"));
    return publicTileResponse(
      cached.body,
      request,
      state,
      Number.isSafeInteger(length) && length >= 0 ? length : undefined,
    );
  }

  const canonicalUrl = new URL(
    `/tiles/${coordinates.zoom}/${coordinates.x}/${coordinates.y}.png`,
    request.url,
  );
  const assetRequest = new Request(canonicalUrl, { method: "GET" });
  let asset = await env.ASSETS.fetch(assetRequest);
  const covered = asset.status !== 404;
  if (!covered) {
    const fallbackUrl = new URL("/tiles/transparent.png", request.url);
    asset = await env.ASSETS.fetch(new Request(fallbackUrl, { method: "GET" }));
  }
  if (!asset.ok) return asset;

  const original = new Uint8Array(await asset.arrayBuffer());
  const bytes = covered
    ? recolorIndexedPng(original, state.colors, state.style)
    : original;
  const cacheResponse = new Response(bytes, {
    headers: {
      "content-type": "image/png",
      "cache-control": "public, max-age=3600",
      "content-length": String(bytes.byteLength),
    },
  });
  ctx.waitUntil(cache.put(cacheRequest, cacheResponse).catch(() => undefined));

  return publicTileResponse(bytes, request, state, bytes.byteLength);
}

async function readStateResponse(
  request: Request,
  env: Env,
  route: "status" | "health",
  now: Date,
): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return methodNotAllowed();
  }

  const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
  try {
    const state = await repository.readCurrent();
    if (state === null) {
      return jsonResponse(
        { ok: false, status: "unavailable", reason: "not_published" },
        request,
        503,
        route === "status" ? "public, max-age=300" : "no-store",
      );
    }

    const isStale = isStateStale(state, now);
    if (route === "status") {
      const forecastNextDay = state.schemaVersion === 2
        ? { ...state.forecastNextDay, isStale }
        : null;
      return jsonResponse(
        { ...state, isStale, forecastNextDay },
        request,
        200,
        "public, max-age=300",
      );
    }

    return jsonResponse(
      {
        ok: !isStale,
        status: isStale ? "stale" : "current",
        snapshotId: state.snapshotId,
        sourceDate: state.sourceTimestampOriginal.slice(0, 10),
        forecastValidDate: state.schemaVersion === 2
          ? state.forecastNextDay.validDate
          : null,
        currentDateMadrid: dateInMadrid(now),
      },
      request,
      isStale ? 503 : 200,
      "no-store",
    );
  } catch (error) {
    const reason =
      error instanceof StateRepositoryError
        ? error.code === "INCOMPATIBLE_SCHEMA_VERSION"
          ? "incompatible_schema_version"
          : "invalid_persisted_state"
        : "state_read_failed";
    return jsonResponse(
      { ok: false, status: "unavailable", reason },
      request,
      503,
      route === "status" ? "public, max-age=300" : "no-store",
    );
  }
}

export interface ScheduledUpdateOptions {
  ingest?: () => Promise<CurrentStateCandidate>;
  now?: () => Date;
  cache?: Cache;
}

export type WorkerOptions = ScheduledUpdateOptions;

export async function runScheduledUpdate(
  env: Env,
  options: ScheduledUpdateOptions = {},
): Promise<"published" | "unchanged"> {
  const ingest = options.ingest ?? (() => ingestCurrentStateCandidate());
  const candidate = await ingest();
  const result = await publishCurrentState(
    new CurrentStateRepository(env.PREVIFOC_STATE),
    candidate,
    options.now,
  );
  return result.outcome;
}

function safeScheduledError(error: unknown): Record<string, unknown> {
  if (error instanceof PrevifocIngestionError) {
    return { error_code: error.code, source: error.source };
  }
  if (error instanceof StateRepositoryError) {
    return { error_code: error.code };
  }
  return { error_code: "UNEXPECTED_ERROR" };
}

export function createWorker(options: WorkerOptions = {}) {
  return {
    async fetch(request, env, ctx): Promise<Response> {
      const pathname = new URL(request.url).pathname;

      if (pathname === DEPLOY_REFRESH_PATH) {
        return serveDeployRefresh(request, env, options);
      }

      if (pathname === "/") {
        const indexUrl = new URL("/index.html", request.url);
        return env.ASSETS.fetch(new Request(indexUrl, request));
      }

      if (pathname === "/health") {
        return readStateResponse(
          request,
          env,
          "health",
          options.now?.() ?? new Date(),
        );
      }

      if (pathname === "/status.json") {
        return readStateResponse(
          request,
          env,
          "status",
          options.now?.() ?? new Date(),
        );
      }

      if (pathname === "/previfoc.osf") {
        return serveOsmandPackage(request, env);
      }

      if (pathname.startsWith("/tiles/")) {
        return serveTile(
          request,
          env,
          ctx,
          options.now?.() ?? new Date(),
          options.cache ?? caches.default,
        );
      }

      return env.ASSETS.fetch(request);
    },

    async scheduled(controller, env, _ctx): Promise<void> {
      try {
        const outcome = await runScheduledUpdate(env, options);
        console.info(
          JSON.stringify({
            event: "previfoc_scheduled_update",
            outcome,
            cron: controller.cron,
            configured_cron: CRON,
            scheduled_time: new Date(controller.scheduledTime).toISOString(),
          }),
        );
      } catch (error) {
        console.warn(
          JSON.stringify({
            event: "previfoc_scheduled_update",
            outcome: "preserved_last_valid",
            cron: controller.cron,
            configured_cron: CRON,
            scheduled_time: new Date(controller.scheduledTime).toISOString(),
            ...safeScheduledError(error),
          }),
        );
      }
    },
  } satisfies ExportedHandler<PrevifocEnv>;
}

const worker = createWorker();

export default worker;
