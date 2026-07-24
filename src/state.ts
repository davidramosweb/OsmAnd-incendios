import {
  levelForSituationId,
  type CurrentStateCandidate,
  type CurrentZoneState,
  type ForecastZoneState,
  type SourceProvenance,
} from "./previfoc";

export const CURRENT_STATE_KEY = "current" as const;
export const CURRENT_STATE_SCHEMA_VERSION = 2 as const;
export const MADRID_TIME_ZONE = "Europe/Madrid" as const;

interface PersistedStateBase {
  snapshotId: string;
  sourceTimestampOriginal: string;
  retrievedAt: string;
  publishedAt: string;
  provenance: {
    previfoc: SourceProvenance;
    situacion: SourceProvenance;
  };
  zones: CurrentZoneState[];
}

export interface PersistedLegacyCurrentState extends PersistedStateBase {
  schemaVersion: 1;
}

export interface PersistedCurrentState extends PersistedStateBase {
  schemaVersion: typeof CURRENT_STATE_SCHEMA_VERSION;
  forecastNextDay: {
    validDate: string;
    zones: ForecastZoneState[];
  };
}

export type ReadableCurrentState =
  | PersistedLegacyCurrentState
  | PersistedCurrentState;

export type StateRepositoryErrorCode =
  | "INVALID_CANDIDATE"
  | "INVALID_JSON"
  | "INVALID_PERSISTED_STATE"
  | "INCOMPATIBLE_SCHEMA_VERSION";

export class StateRepositoryError extends Error {
  readonly code: StateRepositoryErrorCode;

  constructor(code: StateRepositoryErrorCode, message: string) {
    super(message);
    this.name = "StateRepositoryError";
    this.code = code;
  }
}

export interface PublishResult {
  outcome: "published" | "unchanged";
  state: PersistedCurrentState;
}

const zoneIds = [53, 54, 55, 56, 57, 58, 59] as const;
const sourceTimestampPattern =
  /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/;
const calendarDatePattern = /^(\d{4})-(\d{2})-(\d{2})$/;
const snapshotIdPattern = /^sha256:[0-9a-f]{64}$/;

const madridDateFormatter = new Intl.DateTimeFormat("en-US-u-ca-iso8601", {
  timeZone: MADRID_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  numberingSystem: "latn",
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value).sort();
  const sortedExpected = [...expected].sort();
  return actual.length === sortedExpected.length &&
    actual.every((key, index) => key === sortedExpected[index]);
}

function isIsoInstant(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    return new Date(value).toISOString() === value;
  } catch {
    return false;
  }
}

function isValidCalendarDate(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = calendarDatePattern.exec(value);
  if (!match) return false;
  const [, year, month, day] = match;
  const parsed = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return parsed.getUTCFullYear() === Number(year) &&
    parsed.getUTCMonth() === Number(month) - 1 &&
    parsed.getUTCDate() === Number(day);
}

function isValidSourceTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = sourceTimestampPattern.exec(value);
  if (!match) return false;
  const [, year, month, day, hour, minute, second] = match;
  const parsed = new Date(Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second),
  ));
  return parsed.getUTCFullYear() === Number(year) &&
    parsed.getUTCMonth() === Number(month) - 1 &&
    parsed.getUTCDate() === Number(day) &&
    parsed.getUTCHours() === Number(hour) &&
    parsed.getUTCMinutes() === Number(minute) &&
    parsed.getUTCSeconds() === Number(second);
}

function isValidUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function validateProvenance(
  value: unknown,
  expectedSource: "previfoc" | "situacion",
): value is SourceProvenance {
  return isRecord(value) &&
    hasExactKeys(value, [
      "source",
      "requestedUrl",
      "responseUrl",
      "retrievedAt",
      "attempts",
    ]) &&
    value.source === expectedSource &&
    isValidUrl(value.requestedUrl) &&
    isValidUrl(value.responseUrl) &&
    isIsoInstant(value.retrievedAt) &&
    (value.attempts === 1 || value.attempts === 2);
}

function validateProvenancePair(value: unknown): value is PersistedStateBase["provenance"] {
  return isRecord(value) &&
    hasExactKeys(value, ["previfoc", "situacion"]) &&
    validateProvenance(value.previfoc, "previfoc") &&
    validateProvenance(value.situacion, "situacion");
}

function validateCurrentZones(value: unknown): value is CurrentZoneState[] {
  if (!Array.isArray(value) || value.length !== zoneIds.length) return false;
  return value.every((rawZone, index) => {
    if (!isRecord(rawZone) ||
      !hasExactKeys(rawZone, ["zoneId", "situationId", "level", "forestAccess"]) ||
      rawZone.zoneId !== zoneIds[index] ||
      !Number.isInteger(rawZone.situationId) ||
      (rawZone.situationId as number) < 1 ||
      (rawZone.situationId as number) > 9) return false;
    const situationId = rawZone.situationId as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;
    const expectedLevel = levelForSituationId(situationId);
    return rawZone.level === expectedLevel &&
      rawZone.forestAccess === (expectedLevel === 3
        ? "closed_by_mvp_rule"
        : "no_closure_inferred");
  });
}

function validateForecastZones(value: unknown): value is ForecastZoneState[] {
  if (!Array.isArray(value) || value.length !== zoneIds.length) return false;
  return value.every((rawZone, index) => {
    if (!isRecord(rawZone) ||
      !hasExactKeys(rawZone, ["zoneId", "situationId", "level"]) ||
      rawZone.zoneId !== zoneIds[index] ||
      !Number.isInteger(rawZone.situationId) ||
      (rawZone.situationId as number) < 1 ||
      (rawZone.situationId as number) > 9) return false;
    const situationId = rawZone.situationId as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;
    return rawZone.level === levelForSituationId(situationId);
  });
}

function validateForecastBlock(value: unknown): value is PersistedCurrentState["forecastNextDay"] {
  return isRecord(value) &&
    hasExactKeys(value, ["validDate", "zones"]) &&
    isValidCalendarDate(value.validDate) &&
    validateForecastZones(value.zones);
}

export function sourceDateFromTimestamp(sourceTimestamp: string): string {
  if (!isValidSourceTimestamp(sourceTimestamp)) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "source timestamp is invalid",
    );
  }
  return sourceTimestamp.slice(0, 10);
}

export function nextCalendarDate(value: string): string {
  if (!isValidCalendarDate(value)) {
    throw new StateRepositoryError("INVALID_PERSISTED_STATE", "calendar date is invalid");
  }
  const date = new Date(`${value}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

export function dateInMadrid(now: Date): string {
  if (!Number.isFinite(now.getTime())) throw new TypeError("now must be a valid Date");
  const parts = madridDateFormatter.formatToParts(now);
  const part = (type: "year" | "month" | "day") =>
    parts.find((item) => item.type === type)?.value;
  const year = part("year");
  const month = part("month");
  const day = part("day");
  if (year === undefined || month === undefined || day === undefined) {
    throw new Error("Intl did not produce a Madrid calendar date");
  }
  return `${year}-${month}-${day}`;
}

export function isStateStale(state: ReadableCurrentState, now: Date): boolean {
  return sourceDateFromTimestamp(state.sourceTimestampOriginal) !== dateInMadrid(now);
}

function validateCandidate(value: unknown): CurrentStateCandidate {
  if (!isRecord(value) ||
    !hasExactKeys(value, [
      "schemaVersion",
      "sourceTimestampOriginal",
      "retrievedAt",
      "provenance",
      "zones",
      "forecastNextDay",
    ]) ||
    value.schemaVersion !== CURRENT_STATE_SCHEMA_VERSION ||
    !isValidSourceTimestamp(value.sourceTimestampOriginal) ||
    !isIsoInstant(value.retrievedAt) ||
    !validateProvenancePair(value.provenance) ||
    !validateCurrentZones(value.zones) ||
    !validateForecastBlock(value.forecastNextDay) ||
    value.forecastNextDay.validDate !== nextCalendarDate(
      sourceDateFromTimestamp(value.sourceTimestampOriginal),
    )) {
    throw new StateRepositoryError(
      "INVALID_CANDIDATE",
      "candidate does not match schema version 2",
    );
  }
  const latestRetrievedAt = value.provenance.previfoc.retrievedAt >
      value.provenance.situacion.retrievedAt
    ? value.provenance.previfoc.retrievedAt
    : value.provenance.situacion.retrievedAt;
  if (value.retrievedAt !== latestRetrievedAt) {
    throw new StateRepositoryError(
      "INVALID_CANDIDATE",
      "candidate retrieval timestamp is inconsistent",
    );
  }
  return value as unknown as CurrentStateCandidate;
}

export function canonicalSnapshotInput(
  sourceTimestampOriginal: string,
  zones: readonly CurrentZoneState[],
  forecastZones?: readonly ForecastZoneState[],
): string {
  if (!validateCurrentZones(zones) ||
    (forecastZones !== undefined && !validateForecastZones(forecastZones))) {
    throw new StateRepositoryError(
      "INVALID_CANDIDATE",
      "zones are not complete and canonical",
    );
  }
  const value: Record<string, unknown> = forecastZones === undefined
    ? {
        sourceDate: sourceDateFromTimestamp(sourceTimestampOriginal),
        levels: zones.map((zone) => [zone.zoneId, zone.level]),
      }
    : {
        sourceDate: sourceDateFromTimestamp(sourceTimestampOriginal),
        currentLevels: zones.map((zone) => [zone.zoneId, zone.level]),
        forecastNextDayLevels: forecastZones.map((zone) => [zone.zoneId, zone.level]),
      };
  return JSON.stringify(value);
}

export async function calculateSnapshotId(
  sourceTimestampOriginal: string,
  zones: readonly CurrentZoneState[],
  forecastZones?: readonly ForecastZoneState[],
): Promise<string> {
  const input = new TextEncoder().encode(
    canonicalSnapshotInput(sourceTimestampOriginal, zones, forecastZones),
  );
  const digest = await crypto.subtle.digest("SHA-256", input);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
  return `sha256:${hex}`;
}

function validatePersistedBase(value: Record<string, unknown>): boolean {
  return typeof value.snapshotId === "string" &&
    snapshotIdPattern.test(value.snapshotId) &&
    isValidSourceTimestamp(value.sourceTimestampOriginal) &&
    isIsoInstant(value.retrievedAt) &&
    isIsoInstant(value.publishedAt) &&
    validateProvenancePair(value.provenance) &&
    validateCurrentZones(value.zones);
}

export async function validatePersistedCurrentState(
  value: unknown,
): Promise<ReadableCurrentState> {
  if (!isRecord(value)) {
    throw new StateRepositoryError("INVALID_PERSISTED_STATE", "persisted state must be an object");
  }
  if (value.schemaVersion !== 1 && value.schemaVersion !== CURRENT_STATE_SCHEMA_VERSION) {
    throw new StateRepositoryError(
      "INCOMPATIBLE_SCHEMA_VERSION",
      "persisted state schema version is not supported",
    );
  }
  const isLegacy = value.schemaVersion === 1;
  const expectedKeys = isLegacy
    ? ["schemaVersion", "snapshotId", "sourceTimestampOriginal", "retrievedAt", "publishedAt", "provenance", "zones"]
    : ["schemaVersion", "snapshotId", "sourceTimestampOriginal", "retrievedAt", "publishedAt", "provenance", "zones", "forecastNextDay"];
  if (!hasExactKeys(value, expectedKeys) ||
    !validatePersistedBase(value) ||
    (!isLegacy && !validateForecastBlock(value.forecastNextDay))) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "persisted state does not match its schema",
    );
  }
  if (!isLegacy &&
    (value.forecastNextDay as PersistedCurrentState["forecastNextDay"]).validDate !==
      nextCalendarDate(sourceDateFromTimestamp(value.sourceTimestampOriginal as string))) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "forecast date is inconsistent with the source date",
    );
  }
  const expectedSnapshotId = await calculateSnapshotId(
    value.sourceTimestampOriginal as string,
    value.zones as CurrentZoneState[],
    isLegacy
      ? undefined
      : (value.forecastNextDay as PersistedCurrentState["forecastNextDay"]).zones,
  );
  if (value.snapshotId !== expectedSnapshotId) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "persisted state snapshot hash is inconsistent",
    );
  }
  return value as unknown as ReadableCurrentState;
}

export class CurrentStateRepository {
  constructor(private readonly kv: KVNamespace) {}

  async readCurrent(): Promise<ReadableCurrentState | null> {
    const raw = await this.kv.get(CURRENT_STATE_KEY, "text");
    if (raw === null) return null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new StateRepositoryError("INVALID_JSON", "persisted state is not valid JSON");
    }
    return validatePersistedCurrentState(parsed);
  }

  async writeCurrent(state: PersistedCurrentState): Promise<void> {
    const validated = await validatePersistedCurrentState(state);
    if (validated.schemaVersion !== CURRENT_STATE_SCHEMA_VERSION) {
      throw new StateRepositoryError("INVALID_PERSISTED_STATE", "cannot write a legacy state");
    }
    await this.kv.put(CURRENT_STATE_KEY, JSON.stringify(validated));
  }
}

export async function publishCurrentState(
  repository: CurrentStateRepository,
  candidateValue: unknown,
  now: () => Date = () => new Date(),
): Promise<PublishResult> {
  const candidate = validateCandidate(candidateValue);
  const snapshotId = await calculateSnapshotId(
    candidate.sourceTimestampOriginal,
    candidate.zones,
    candidate.forecastNextDay.zones,
  );
  const current = await repository.readCurrent();
  if (current?.schemaVersion === CURRENT_STATE_SCHEMA_VERSION &&
    current.snapshotId === snapshotId) {
    return { outcome: "unchanged", state: current };
  }
  const state: PersistedCurrentState = {
    schemaVersion: CURRENT_STATE_SCHEMA_VERSION,
    snapshotId,
    sourceTimestampOriginal: candidate.sourceTimestampOriginal,
    retrievedAt: candidate.retrievedAt,
    publishedAt: now().toISOString(),
    provenance: candidate.provenance,
    zones: candidate.zones.map((zone) => ({ ...zone })),
    forecastNextDay: {
      validDate: candidate.forecastNextDay.validDate,
      zones: candidate.forecastNextDay.zones.map((zone) => ({ ...zone })),
    },
  };
  await repository.writeCurrent(state);
  return { outcome: "published", state };
}
