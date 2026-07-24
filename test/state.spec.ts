import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  normalizeCurrentStateCandidate,
  type CurrentStateCandidate,
} from "../src/previfoc";
import {
  calculateSnapshotId,
  canonicalSnapshotInput,
  CURRENT_STATE_KEY,
  CurrentStateRepository,
  dateInMadrid,
  isStateStale,
  nextCalendarDate,
  publishCurrentState,
} from "../src/state";
import {
  cloneFixture,
  validPrevifocFixture,
  validSituacionFixture,
} from "./fixtures/previfoc";

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

function candidate(
  sourceTimestampOriginal = "2026-07-18 00:01:41.0",
): CurrentStateCandidate {
  const previfoc = cloneFixture(validPrevifocFixture);
  previfoc.time = sourceTimestampOriginal;
  return normalizeCurrentStateCandidate(
    previfoc,
    validSituacionFixture,
    provenance,
  );
}

function candidateWithSituation(zoneId: number, situationId: number) {
  const previfoc = cloneFixture(validPrevifocFixture);
  previfoc.z1.find((zone) => zone.id === zoneId)!.nact = situationId;
  return normalizeCurrentStateCandidate(
    previfoc,
    validSituacionFixture,
    provenance,
  );
}

function candidateWithForecastSituation(zoneId: number, situationId: number) {
  const previfoc = cloneFixture(validPrevifocFixture);
  previfoc.z1.find((zone) => zone.id === zoneId)!.npre = situationId;
  return normalizeCurrentStateCandidate(previfoc, validSituacionFixture, provenance);
}

describe("WORKER-003 typed KV state", () => {
  beforeEach(async () => {
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
  });

  it("publishes the first complete candidate under the only key current", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const result = await publishCurrentState(
      repository,
      candidate(),
      () => new Date("2026-07-18T08:05:00.000Z"),
    );

    expect(result.outcome).toBe("published");
    expect(await env.PREVIFOC_STATE.list()).toMatchObject({
      keys: [{ name: CURRENT_STATE_KEY }],
    });
    await expect(repository.readCurrent()).resolves.toEqual(result.state);
    expect(result.state).toMatchObject({
      schemaVersion: 2,
      sourceTimestampOriginal: "2026-07-18 00:01:41.0",
      retrievedAt: "2026-07-18T08:00:01.000Z",
      publishedAt: "2026-07-18T08:05:00.000Z",
    });
    expect(result.state.zones.map((zone) => zone.zoneId)).toEqual([
      53, 54, 55, 56, 57, 58, 59,
    ]);
    expect(result.state.forecastNextDay.validDate).toBe("2026-07-19");
    expect(result.state.forecastNextDay.zones).toHaveLength(7);
  });

  it("rejects an invalid candidate before reading or modifying KV", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const invalid = structuredClone(candidate()) as unknown as {
      zones: unknown[];
    };
    invalid.zones.pop();
    const get = vi.spyOn(env.PREVIFOC_STATE, "get");
    const put = vi.spyOn(env.PREVIFOC_STATE, "put");

    await expect(
      publishCurrentState(repository, invalid),
    ).rejects.toMatchObject({ code: "INVALID_CANDIDATE" });
    expect(get).not.toHaveBeenCalled();
    expect(put).not.toHaveBeenCalled();
    get.mockRestore();
    put.mockRestore();
    expect(await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY)).toBeNull();
  });

  it("derives a deterministic SHA-256 snapshot from canonical date and levels", async () => {
    const first = candidate();
    const reordered = structuredClone(first);
    reordered.zones.reverse();

    const firstId = await calculateSnapshotId(
      first.sourceTimestampOriginal,
      first.zones,
    );
    expect(firstId).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(
      canonicalSnapshotInput(first.sourceTimestampOriginal, first.zones),
    ).toBe(
      '{"sourceDate":"2026-07-18","levels":[[53,1],[54,1],[55,1],[56,2],[57,2],[58,3],[59,3]]}',
    );
    await expect(
      calculateSnapshotId(first.sourceTimestampOriginal, first.zones),
    ).resolves.toBe(firstId);
    await expect(
      calculateSnapshotId(reordered.sourceTimestampOriginal, reordered.zones),
    ).rejects.toMatchObject({ code: "INVALID_CANDIDATE" });
  });

  it("changes snapshotId when any level changes", async () => {
    const original = candidate();
    const changed = candidateWithSituation(53, 4);
    await expect(
      calculateSnapshotId(changed.sourceTimestampOriginal, changed.zones),
    ).resolves.not.toBe(
      await calculateSnapshotId(
        original.sourceTimestampOriginal,
        original.zones,
      ),
    );
  });

  it("changes snapshotId when a forecast level changes", async () => {
    const original = candidate();
    const changed = candidateWithForecastSituation(53, 4);
    await expect(
      calculateSnapshotId(
        changed.sourceTimestampOriginal,
        changed.zones,
        changed.forecastNextDay.zones,
      ),
    ).resolves.not.toBe(
      await calculateSnapshotId(
        original.sourceTimestampOriginal,
        original.zones,
        original.forecastNextDay.zones,
      ),
    );
  });

  it("does not write when the semantic date and levels are unchanged", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const first = await publishCurrentState(
      repository,
      candidate(),
      () => new Date("2026-07-18T08:05:00.000Z"),
    );
    const before = await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY);
    const put = vi.spyOn(env.PREVIFOC_STATE, "put");

    const result = await publishCurrentState(
      repository,
      candidateWithSituation(53, 2),
      () => new Date("2026-07-18T09:05:00.000Z"),
    );

    expect(result).toEqual({ outcome: "unchanged", state: first.state });
    expect(put).not.toHaveBeenCalled();
    put.mockRestore();
    expect(await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY)).toBe(before);
  });

  it("reads legacy schema version 1 and explicitly rejects an incompatible version", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const published = await publishCurrentState(repository, candidate());
    const { forecastNextDay: _forecast, ...legacyBase } = published.state;
    const legacy = {
      ...legacyBase,
      schemaVersion: 1 as const,
      snapshotId: await calculateSnapshotId(
        published.state.sourceTimestampOriginal,
        published.state.zones,
      ),
    };
    await env.PREVIFOC_STATE.put(CURRENT_STATE_KEY, JSON.stringify(legacy));
    await expect(repository.readCurrent()).resolves.toEqual(legacy);

    await env.PREVIFOC_STATE.put(
      CURRENT_STATE_KEY,
      JSON.stringify({ schemaVersion: 3, future: true }),
    );
    await expect(repository.readCurrent()).rejects.toEqual(
      expect.objectContaining({ code: "INCOMPATIBLE_SCHEMA_VERSION" }),
    );
  });

  it("does not overwrite an incompatible value already stored under current", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    const future = JSON.stringify({ schemaVersion: 3, future: true });
    await env.PREVIFOC_STATE.put(CURRENT_STATE_KEY, future);
    const put = vi.spyOn(env.PREVIFOC_STATE, "put");

    await expect(
      publishCurrentState(repository, candidate()),
    ).rejects.toMatchObject({ code: "INCOMPATIBLE_SCHEMA_VERSION" });
    expect(put).not.toHaveBeenCalled();
    put.mockRestore();
    expect(await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY)).toBe(future);
  });

  it("persists normalized forecast but never HTML, dry-storm fields or geometry", async () => {
    await publishCurrentState(
      new CurrentStateRepository(env.PREVIFOC_STATE),
      candidate(),
    );
    const raw = await env.PREVIFOC_STATE.get(CURRENT_STATE_KEY);
    expect(raw).not.toBeNull();
    expect(raw).toContain("forecastNextDay");
    expect(raw).not.toContain("desEs");
    expect(raw).not.toContain("fixture deliberately");
    expect(raw).not.toContain("storm");
    expect(raw).not.toContain("torment");
    expect(raw).not.toContain("geometry");
  });
});

describe("WORKER-003 Europe/Madrid calendar freshness", () => {
  it("increments calendar dates across month and year boundaries", () => {
    expect(nextCalendarDate("2026-02-28")).toBe("2026-03-01");
    expect(nextCalendarDate("2026-12-31")).toBe("2027-01-01");
  });
  it("uses CET without a fixed UTC offset assumption", () => {
    expect(dateInMadrid(new Date("2026-01-15T22:59:59.999Z"))).toBe(
      "2026-01-15",
    );
    expect(dateInMadrid(new Date("2026-01-15T23:00:00.000Z"))).toBe(
      "2026-01-16",
    );
  });

  it("uses CEST without a fixed UTC offset assumption", () => {
    expect(dateInMadrid(new Date("2026-07-15T21:59:59.999Z"))).toBe(
      "2026-07-15",
    );
    expect(dateInMadrid(new Date("2026-07-15T22:00:00.000Z"))).toBe(
      "2026-07-16",
    );
  });

  it("becomes stale at Madrid midnight without waiting for Cron", async () => {
    const repository = new CurrentStateRepository(env.PREVIFOC_STATE);
    await env.PREVIFOC_STATE.delete(CURRENT_STATE_KEY);
    const { state } = await publishCurrentState(
      repository,
      candidate("2026-01-15 00:01:41.0"),
    );

    expect(
      isStateStale(state, new Date("2026-01-15T22:59:59.999Z")),
    ).toBe(false);
    expect(
      isStateStale(state, new Date("2026-01-15T23:00:00.000Z")),
    ).toBe(true);
  });
});
