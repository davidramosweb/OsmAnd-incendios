export const PREVIFOC_URL =
  "https://wpr.112cv.gva.es/external/api/storage/descargar/json/previfoc";
export const SITUACION_URL =
  "https://wpr.112cv.gva.es/external/api/storage/descargar/json/static/situacion";

export const ZONE_IDS = [53, 54, 55, 56, 57, 58, 59] as const;
export const SITUATION_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9] as const;

export type ZoneId = (typeof ZONE_IDS)[number];
export type SituationId = (typeof SITUATION_IDS)[number];
export type PrevifocLevel = 1 | 2 | 3;
export type ForestAccess = "closed_by_mvp_rule" | "no_closure_inferred";
export type PrevifocSource = "previfoc" | "situacion";

export interface CurrentZoneState {
  zoneId: ZoneId;
  situationId: SituationId;
  level: PrevifocLevel;
  forestAccess: ForestAccess;
}

export interface ForecastZoneState {
  zoneId: ZoneId;
  situationId: SituationId;
  level: PrevifocLevel;
}

export interface SourceProvenance {
  source: PrevifocSource;
  requestedUrl: string;
  responseUrl: string;
  retrievedAt: string;
  attempts: 1 | 2;
}

export interface CurrentStateCandidate {
  schemaVersion: 2;
  sourceTimestampOriginal: string;
  retrievedAt: string;
  provenance: {
    previfoc: SourceProvenance;
    situacion: SourceProvenance;
  };
  zones: CurrentZoneState[];
  forecastNextDay: {
    validDate: string;
    zones: ForecastZoneState[];
  };
}

export type IngestionErrorCode =
  | "FETCH_FAILED"
  | "HTTP_STATUS"
  | "INVALID_CONTENT_TYPE"
  | "INVALID_JSON"
  | "INVALID_SHAPE"
  | "INVALID_REQUIRED_FIELD"
  | "INVALID_SOURCE_TIMESTAMP"
  | "DUPLICATE_ZONE_ID"
  | "INVALID_ZONE_SET"
  | "DUPLICATE_SITUATION_ID"
  | "UNKNOWN_PREVIFOC_SITUATION_ID"
  | "SITUATION_WRONG_ADVISORY"
  | "SITUATION_INACTIVE"
  | "INVALID_SITUATION_CATALOG"
  | "UNKNOWN_CURRENT_SITUATION"
  | "UNKNOWN_FORECAST_SITUATION";

export class PrevifocIngestionError extends Error {
  readonly code: IngestionErrorCode;
  readonly source?: PrevifocSource;

  constructor(
    code: IngestionErrorCode,
    message: string,
    source?: PrevifocSource,
  ) {
    super(message);
    this.name = "PrevifocIngestionError";
    this.code = code;
    this.source = source;
  }
}

interface PrevifocZoneInput {
  zoneId: ZoneId;
  currentSituationId: number;
  forecastSituationId: number;
}

interface ValidatedPrevifoc {
  sourceTimestampOriginal: string;
  zones: PrevifocZoneInput[];
}

interface DownloadedSource {
  body: unknown;
  provenance: SourceProvenance;
}

export interface IngestCurrentStateOptions {
  fetch?: typeof fetch;
  now?: () => Date;
  sleep?: (milliseconds: number) => Promise<void>;
  timeoutMs?: number;
  retryDelayMs?: number;
  previfocUrl?: string;
  situacionUrl?: string;
}

const DEFAULT_TIMEOUT_MS = 5_000;
const DEFAULT_RETRY_DELAY_MS = 200;
const MAX_ATTEMPTS = 2;

const zoneIdSet = new Set<number>(ZONE_IDS);
const situationIdSet = new Set<number>(SITUATION_IDS);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fail(
  code: IngestionErrorCode,
  source: PrevifocSource,
  message: string,
): never {
  throw new PrevifocIngestionError(code, `${source}: ${message}`, source);
}

function requireRecord(
  value: unknown,
  source: PrevifocSource,
  path: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    fail("INVALID_SHAPE", source, `${path} must be an object`);
  }
  return value;
}

function requireArray(
  object: Record<string, unknown>,
  key: string,
  source: PrevifocSource,
  path: string,
): unknown[] {
  if (!Object.hasOwn(object, key) || !Array.isArray(object[key])) {
    fail(
      "INVALID_REQUIRED_FIELD",
      source,
      `${path}.${key} must be an array`,
    );
  }
  return object[key];
}

function requireInteger(
  object: Record<string, unknown>,
  key: string,
  source: PrevifocSource,
  path: string,
): number {
  const value = object[key];
  if (!Object.hasOwn(object, key) || !Number.isInteger(value)) {
    fail(
      "INVALID_REQUIRED_FIELD",
      source,
      `${path}.${key} must be an integer`,
    );
  }
  return value as number;
}

function requireString(
  object: Record<string, unknown>,
  key: string,
  source: PrevifocSource,
  path: string,
): string {
  const value = object[key];
  if (!Object.hasOwn(object, key) || typeof value !== "string") {
    fail(
      "INVALID_REQUIRED_FIELD",
      source,
      `${path}.${key} must be a string`,
    );
  }
  return value;
}

function isValidSourceTimestamp(value: string): boolean {
  const match =
    /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/.exec(
      value,
    );
  if (!match) return false;

  const [, year, month, day, hour, minute, second] = match;
  const parsed = new Date(
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    ),
  );
  return (
    parsed.getUTCFullYear() === Number(year) &&
    parsed.getUTCMonth() === Number(month) - 1 &&
    parsed.getUTCDate() === Number(day) &&
    parsed.getUTCHours() === Number(hour) &&
    parsed.getUTCMinutes() === Number(minute) &&
    parsed.getUTCSeconds() === Number(second)
  );
}

export function validatePrevifocSource(value: unknown): ValidatedPrevifoc {
  const source = "previfoc";
  const root = requireRecord(value, source, "$");
  const sourceTimestampOriginal = requireString(root, "time", source, "$");
  if (!isValidSourceTimestamp(sourceTimestampOriginal)) {
    fail(
      "INVALID_SOURCE_TIMESTAMP",
      source,
      "$.time does not match the observed local timestamp format",
    );
  }

  const rawZones = requireArray(root, "z1", source, "$");
  const seen = new Set<number>();
  const zones: PrevifocZoneInput[] = [];

  for (const [index, rawZone] of rawZones.entries()) {
    const path = `$.z1[${index}]`;
    const zone = requireRecord(rawZone, source, path);
    const zoneId = requireInteger(zone, "id", source, path);
    const currentSituationId = requireInteger(zone, "nact", source, path);
    const forecastSituationId = requireInteger(zone, "npre", source, path);

    if (seen.has(zoneId)) {
      fail("DUPLICATE_ZONE_ID", source, `${path}.id is duplicated`);
    }
    seen.add(zoneId);

    if (!zoneIdSet.has(zoneId)) {
      fail("INVALID_ZONE_SET", source, `${path}.id is not a PREVIFOC zone`);
    }
    zones.push({
      zoneId: zoneId as ZoneId,
      currentSituationId,
      forecastSituationId,
    });
  }

  if (
    zones.length !== ZONE_IDS.length ||
    ZONE_IDS.some((zoneId) => !seen.has(zoneId))
  ) {
    fail(
      "INVALID_ZONE_SET",
      source,
      "$.z1 must contain exactly zones 53 through 59",
    );
  }

  return { sourceTimestampOriginal, zones };
}

export function levelForSituationId(
  situationId: SituationId,
): PrevifocLevel {
  if (situationId <= 3) return 1;
  if (situationId <= 6) return 2;
  return 3;
}

export function validateSituationSource(
  value: unknown,
): Map<SituationId, PrevifocLevel> {
  const source = "situacion";
  const root = requireRecord(value, source, "$");
  const rawSituations = requireArray(root, "SITUACION", source, "$");
  const seen = new Set<number>();
  const previfocSituations = new Map<SituationId, PrevifocLevel>();

  for (const [index, rawSituation] of rawSituations.entries()) {
    const path = `$.SITUACION[${index}]`;
    const situation = requireRecord(rawSituation, source, path);
    const situationId = requireInteger(
      situation,
      "ID_SITUACION",
      source,
      path,
    );
    const advisoryId = requireInteger(situation, "ID_AVISO", source, path);
    const active = requireString(situation, "ACTIVO", source, path);

    if (seen.has(situationId)) {
      fail(
        "DUPLICATE_SITUATION_ID",
        source,
        `${path}.ID_SITUACION is duplicated`,
      );
    }
    seen.add(situationId);

    if (advisoryId !== 3) {
      if (situationIdSet.has(situationId)) {
        fail(
          "SITUATION_WRONG_ADVISORY",
          source,
          `${path} assigns a PREVIFOC situation ID to another advisory`,
        );
      }
      continue;
    }

    if (!situationIdSet.has(situationId)) {
      fail(
        "UNKNOWN_PREVIFOC_SITUATION_ID",
        source,
        `${path}.ID_SITUACION is outside the validated PREVIFOC catalog`,
      );
    }
    if (active !== "S") {
      fail("SITUATION_INACTIVE", source, `${path} is not active`);
    }

    const typedId = situationId as SituationId;
    previfocSituations.set(typedId, levelForSituationId(typedId));
  }

  if (
    previfocSituations.size !== SITUATION_IDS.length ||
    SITUATION_IDS.some((situationId) => !previfocSituations.has(situationId))
  ) {
    fail(
      "INVALID_SITUATION_CATALOG",
      source,
      "catalog must contain the nine active PREVIFOC situations",
    );
  }

  return previfocSituations;
}

export function normalizeCurrentStateCandidate(
  previfocValue: unknown,
  situacionValue: unknown,
  provenance: CurrentStateCandidate["provenance"],
): CurrentStateCandidate {
  const previfoc = validatePrevifocSource(previfocValue);
  const situationLevels = validateSituationSource(situacionValue);

  const resolveLevel = (
    situationId: number,
    errorCode: "UNKNOWN_CURRENT_SITUATION" | "UNKNOWN_FORECAST_SITUATION",
    period: "current" | "forecast",
  ): { situationId: SituationId; level: PrevifocLevel } => {
    if (!situationIdSet.has(situationId)) {
      fail(
        errorCode,
        "previfoc",
        `a zone references an unknown ${period} situation`,
      );
    }
    const typedSituationId = situationId as SituationId;
    const level = situationLevels.get(typedSituationId);
    if (level === undefined) {
      fail(
        errorCode,
        "previfoc",
        `a zone does not resolve to an active PREVIFOC ${period} situation`,
      );
    }
    return { situationId: typedSituationId, level };
  };

  const zones = previfoc.zones
    .map(({ zoneId, currentSituationId }) => {
      const { situationId, level } = resolveLevel(
        currentSituationId,
        "UNKNOWN_CURRENT_SITUATION",
        "current",
      );
      return {
        zoneId,
        situationId,
        level,
        forestAccess:
          level === 3
            ? ("closed_by_mvp_rule" as const)
            : ("no_closure_inferred" as const),
      };
    })
    .sort((left, right) => left.zoneId - right.zoneId);

  const forecastZones = previfoc.zones
    .map(({ zoneId, forecastSituationId }) => ({
      zoneId,
      ...resolveLevel(
        forecastSituationId,
        "UNKNOWN_FORECAST_SITUATION",
        "forecast",
      ),
    }))
    .sort((left, right) => left.zoneId - right.zoneId);

  const sourceDate = previfoc.sourceTimestampOriginal.slice(0, 10);
  const date = new Date(`${sourceDate}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  const forecastValidDate = date.toISOString().slice(0, 10);

  return {
    schemaVersion: 2,
    sourceTimestampOriginal: previfoc.sourceTimestampOriginal,
    retrievedAt:
      provenance.previfoc.retrievedAt > provenance.situacion.retrievedAt
        ? provenance.previfoc.retrievedAt
        : provenance.situacion.retrievedAt,
    provenance,
    zones,
    forecastNextDay: {
      validDate: forecastValidDate,
      zones: forecastZones,
    },
  };
}

function isTransientStatus(status: number): boolean {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

function defaultSleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function validatedPositiveOption(value: number, name: string): number {
  if (!Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${name} must be a positive finite number`);
  }
  return value;
}

async function discardBody(response: Response): Promise<void> {
  try {
    await response.body?.cancel();
  } catch {
    // The response is already being rejected; body cleanup must not mask it.
  }
}

async function downloadJsonSource(
  source: PrevifocSource,
  requestedUrl: string,
  fetchImpl: typeof fetch,
  now: () => Date,
  sleep: (milliseconds: number) => Promise<void>,
  timeoutMs: number,
  retryDelayMs: number,
): Promise<DownloadedSource> {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;

    try {
      response = await fetchImpl(requestedUrl, {
        method: "GET",
        headers: { accept: "application/json" },
        signal: controller.signal,
      });
    } catch {
      clearTimeout(timeout);
      if (attempt < MAX_ATTEMPTS) {
        await sleep(retryDelayMs);
        continue;
      }
      fail(
        "FETCH_FAILED",
        source,
        `request failed after ${MAX_ATTEMPTS} attempts`,
      );
    }
    if (!response.ok) {
      await discardBody(response);
      clearTimeout(timeout);
      if (isTransientStatus(response.status) && attempt < MAX_ATTEMPTS) {
        await sleep(retryDelayMs);
        continue;
      }
      fail(
        "HTTP_STATUS",
        source,
        `upstream returned HTTP ${response.status} after ${attempt} attempt(s)`,
      );
    }

    const contentType = response.headers.get("content-type");
    if (!contentType?.toLowerCase().startsWith("application/json")) {
      await discardBody(response);
      clearTimeout(timeout);
      fail(
        "INVALID_CONTENT_TYPE",
        source,
        "upstream response is not application/json",
      );
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      const timedOut = controller.signal.aborted;
      clearTimeout(timeout);
      if (timedOut && attempt < MAX_ATTEMPTS) {
        await sleep(retryDelayMs);
        continue;
      }
      if (timedOut) {
        fail(
          "FETCH_FAILED",
          source,
          `request failed after ${MAX_ATTEMPTS} attempts`,
        );
      }
      fail("INVALID_JSON", source, "upstream response is not valid JSON");
    }
    clearTimeout(timeout);

    const retrievedAt = now().toISOString();
    return {
      body,
      provenance: {
        source,
        requestedUrl,
        responseUrl: response.url || requestedUrl,
        retrievedAt,
        attempts: attempt as 1 | 2,
      },
    };
  }

  throw new Error("unreachable");
}

export async function ingestCurrentStateCandidate(
  options: IngestCurrentStateOptions = {},
): Promise<CurrentStateCandidate> {
  const fetchImpl = options.fetch ?? fetch;
  const now = options.now ?? (() => new Date());
  const sleep = options.sleep ?? defaultSleep;
  const timeoutMs = validatedPositiveOption(
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    "timeoutMs",
  );
  const retryDelayMs = validatedPositiveOption(
    options.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS,
    "retryDelayMs",
  );
  const previfocUrl = options.previfocUrl ?? PREVIFOC_URL;
  const situacionUrl = options.situacionUrl ?? SITUACION_URL;

  const [previfoc, situacion] = await Promise.all([
    downloadJsonSource(
      "previfoc",
      previfocUrl,
      fetchImpl,
      now,
      sleep,
      timeoutMs,
      retryDelayMs,
    ),
    downloadJsonSource(
      "situacion",
      situacionUrl,
      fetchImpl,
      now,
      sleep,
      timeoutMs,
      retryDelayMs,
    ),
  ]);

  return normalizeCurrentStateCandidate(previfoc.body, situacion.body, {
    previfoc: previfoc.provenance,
    situacion: situacion.provenance,
  });
}
