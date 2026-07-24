import {
  levelForSituationId,
  type CurrentStateCandidate,
  type CurrentZoneState,
  type SourceProvenance,
} from "./previfoc";

export const CURRENT_STATE_KEY = "current" as const;
export const CURRENT_STATE_SCHEMA_VERSION = 1 as const;
export const MADRID_TIME_ZONE = "Europe/Madrid" as const;

export interface PersistedCurrentState {
  schemaVersion: typeof CURRENT_STATE_SCHEMA_VERSION;
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
  return (
    actual.length === sortedExpected.length &&
    actual.every((key, index) => key === sortedExpected[index])
  );
}

function isIsoInstant(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    return new Date(value).toISOString() === value;
  } catch {
    return false;
  }
}

function isValidSourceTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = sourceTimestampPattern.exec(value);
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
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "source",
      "requestedUrl",
      "responseUrl",
      "retrievedAt",
      "attempts",
    ])
  ) {
    return false;
  }
  return (
    value.source === expectedSource &&
    isValidUrl(value.requestedUrl) &&
    isValidUrl(value.responseUrl) &&
    isIsoInstant(value.retrievedAt) &&
    (value.attempts === 1 || value.attempts === 2)
  );
}

function validateZones(value: unknown): value is CurrentZoneState[] {
  if (!Array.isArray(value) || value.length !== zoneIds.length) return false;

  return value.every((rawZone, index) => {
    if (
      !isRecord(rawZone) ||
      !hasExactKeys(rawZone, [
        "zoneId",
        "situationId",
        "level",
        "forestAccess",
      ]) ||
      rawZone.zoneId !== zoneIds[index] ||
      !Number.isInteger(rawZone.situationId) ||
      (rawZone.situationId as number) < 1 ||
      (rawZone.situationId as number) > 9
    ) {
      return false;
    }

    const situationId = rawZone.situationId as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;
    const expectedLevel = levelForSituationId(situationId);
    return (
      rawZone.level === expectedLevel &&
      rawZone.forestAccess ===
        (expectedLevel === 3
          ? "closed_by_mvp_rule"
          : "no_closure_inferred")
    );
  });
}

function validateCandidate(value: unknown): CurrentStateCandidate {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "schemaVersion",
      "sourceTimestampOriginal",
      "retrievedAt",
      "provenance",
      "zones",
    ]) ||
    value.schemaVersion !== CURRENT_STATE_SCHEMA_VERSION ||
    !isValidSourceTimestamp(value.sourceTimestampOriginal) ||
    !isIsoInstant(value.retrievedAt) ||
    !isRecord(value.provenance) ||
    !hasExactKeys(value.provenance, ["previfoc", "situacion"]) ||
    !validateProvenance(value.provenance.previfoc, "previfoc") ||
    !validateProvenance(value.provenance.situacion, "situacion") ||
    !validateZones(value.zones)
  ) {
    throw new StateRepositoryError(
      "INVALID_CANDIDATE",
      "candidate does not match schema version 1",
    );
  }

  const latestRetrievedAt =
    value.provenance.previfoc.retrievedAt >
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

export function sourceDateFromTimestamp(sourceTimestamp: string): string {
  if (!isValidSourceTimestamp(sourceTimestamp)) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "source timestamp is invalid",
    );
  }
  return sourceTimestamp.slice(0, 10);
}

export function dateInMadrid(now: Date): string {
  if (!Number.isFinite(now.getTime())) {
    throw new TypeError("now must be a valid Date");
  }
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

export function isStateStale(
  state: PersistedCurrentState,
  now: Date,
): boolean {
  return (
    sourceDateFromTimestamp(state.sourceTimestampOriginal) !== dateInMadrid(now)
  );
}

export function canonicalSnapshotInput(
  sourceTimestampOriginal: string,
  zones: readonly CurrentZoneState[],
): string {
  if (!validateZones(zones)) {
    throw new StateRepositoryError(
      "INVALID_CANDIDATE",
      "zones are not complete and canonical",
    );
  }
  return JSON.stringify({
    sourceDate: sourceDateFromTimestamp(sourceTimestampOriginal),
    levels: zones.map((zone) => [zone.zoneId, zone.level]),
  });
}

export async function calculateSnapshotId(
  sourceTimestampOriginal: string,
  zones: readonly CurrentZoneState[],
): Promise<string> {
  const input = new TextEncoder().encode(
    canonicalSnapshotInput(sourceTimestampOriginal, zones),
  );
  const digest = await crypto.subtle.digest("SHA-256", input);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return `sha256:${hex}`;
}

export async function validatePersistedCurrentState(
  value: unknown,
): Promise<PersistedCurrentState> {
  if (!isRecord(value)) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "persisted current state must be an object",
    );
  }
  if (value.schemaVersion !== CURRENT_STATE_SCHEMA_VERSION) {
    throw new StateRepositoryError(
      "INCOMPATIBLE_SCHEMA_VERSION",
      "persisted current state schema version is not supported",
    );
  }
  if (
    !hasExactKeys(value, [
      "schemaVersion",
      "snapshotId",
      "sourceTimestampOriginal",
      "retrievedAt",
      "publishedAt",
      "provenance",
      "zones",
    ]) ||
    typeof value.snapshotId !== "string" ||
    !snapshotIdPattern.test(value.snapshotId) ||
    !isValidSourceTimestamp(value.sourceTimestampOriginal) ||
    !isIsoInstant(value.retrievedAt) ||
    !isIsoInstant(value.publishedAt) ||
    !isRecord(value.provenance) ||
    !hasExactKeys(value.provenance, ["previfoc", "situacion"]) ||
    !validateProvenance(value.provenance.previfoc, "previfoc") ||
    !validateProvenance(value.provenance.situacion, "situacion") ||
    !validateZones(value.zones)
  ) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "persisted current state does not match schema version 1",
    );
  }

  const expectedSnapshotId = await calculateSnapshotId(
    value.sourceTimestampOriginal,
    value.zones,
  );
  if (value.snapshotId !== expectedSnapshotId) {
    throw new StateRepositoryError(
      "INVALID_PERSISTED_STATE",
      "persisted current state snapshot hash is inconsistent",
    );
  }

  return value as unknown as PersistedCurrentState;
}

export class CurrentStateRepository {
  constructor(private readonly kv: KVNamespace) {}

  async readCurrent(): Promise<PersistedCurrentState | null> {
    const raw = await this.kv.get(CURRENT_STATE_KEY, "text");
    if (raw === null) return null;

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new StateRepositoryError(
        "INVALID_JSON",
        "persisted current state is not valid JSON",
      );
    }
    return validatePersistedCurrentState(parsed);
  }

  async writeCurrent(state: PersistedCurrentState): Promise<void> {
    const validated = await validatePersistedCurrentState(state);
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
  );
  const current = await repository.readCurrent();
  if (current?.snapshotId === snapshotId) {
    return { outcome: "unchanged", state: current };
  }

  const publishedAt = now().toISOString();
  const state: PersistedCurrentState = {
    schemaVersion: CURRENT_STATE_SCHEMA_VERSION,
    snapshotId,
    sourceTimestampOriginal: candidate.sourceTimestampOriginal,
    retrievedAt: candidate.retrievedAt,
    publishedAt,
    provenance: candidate.provenance,
    zones: candidate.zones.map((zone) => ({ ...zone })),
  };
  await repository.writeCurrent(state);
  return { outcome: "published", state };
}
