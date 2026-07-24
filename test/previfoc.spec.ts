import { describe, expect, it, vi } from "vitest";

import {
  ingestCurrentStateCandidate,
  levelForSituationId,
  normalizeCurrentStateCandidate,
  PrevifocIngestionError,
  type CurrentStateCandidate,
  type IngestionErrorCode,
  type SituationId,
} from "../src/previfoc";
import {
  cloneFixture,
  invalidDuplicateZoneFixture,
  invalidWrongAdvisoryFixture,
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

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function expectIngestionError(
  action: () => unknown,
  code: IngestionErrorCode,
): PrevifocIngestionError {
  try {
    action();
  } catch (error) {
    expect(error).toBeInstanceOf(PrevifocIngestionError);
    expect(error).toMatchObject({ code });
    return error as PrevifocIngestionError;
  }
  throw new Error(`expected ${code}`);
}

function fixtureFetch(): typeof fetch {
  return async (input) => {
    const url = input.toString();
    return url.endsWith("/situacion")
      ? jsonResponse(validSituacionFixture)
      : jsonResponse(validPrevifocFixture);
  };
}

describe("WORKER-002 PREVIFOC normalization", () => {
  it("translates all nine situation IDs into their validated level", () => {
    expect(
      Array.from({ length: 9 }, (_, index) =>
        levelForSituationId((index + 1) as SituationId),
      ),
    ).toEqual([1, 1, 1, 2, 2, 2, 3, 3, 3]);
  });

  it("produces exactly seven zones ordered by ID with the MVP access rule", () => {
    const candidate = normalizeCurrentStateCandidate(
      validPrevifocFixture,
      validSituacionFixture,
      provenance,
    );

    expect(candidate).toMatchObject({
      schemaVersion: 2,
      sourceTimestampOriginal: "2026-07-18 00:01:41.0",
      retrievedAt: "2026-07-18T08:00:01.000Z",
      provenance,
    });
    expect(candidate.zones.map((zone) => zone.zoneId)).toEqual([
      53, 54, 55, 56, 57, 58, 59,
    ]);
    expect(candidate.zones).toHaveLength(7);
    expect(candidate.forecastNextDay).toMatchObject({
      validDate: "2026-07-19",
      zones: [
        { zoneId: 53, situationId: 1, level: 1 },
        { zoneId: 54, situationId: 2, level: 1 },
        { zoneId: 55, situationId: 3, level: 1 },
        { zoneId: 56, situationId: 4, level: 2 },
        { zoneId: 57, situationId: 5, level: 2 },
        { zoneId: 58, situationId: 7, level: 3 },
        { zoneId: 59, situationId: 4, level: 2 },
      ],
    });
    expect(JSON.stringify(candidate.forecastNextDay)).not.toContain("forestAccess");
    expect(candidate.zones.map((zone) => zone.forestAccess)).toEqual([
      "no_closure_inferred",
      "no_closure_inferred",
      "no_closure_inferred",
      "no_closure_inferred",
      "no_closure_inferred",
      "closed_by_mvp_rule",
      "closed_by_mvp_rule",
    ]);
    expect(JSON.stringify(candidate)).not.toContain("open");
  });

  it("accepts compatible additional fields without retaining unused HTML", () => {
    const previfoc = cloneFixture(validPrevifocFixture) as Record<
      string,
      unknown
    >;
    const situacion = cloneFixture(validSituacionFixture) as Record<
      string,
      unknown
    >;
    previfoc.future_field = { compatible: true };
    (previfoc.z1 as Array<Record<string, unknown>>)[0]!.future_zone_field =
      "ignored";
    situacion.future_catalog_field = ["ignored"];
    (
      situacion.SITUACION as Array<Record<string, unknown>>
    )[0]!.future_row_field = 42;

    const candidate = normalizeCurrentStateCandidate(
      previfoc,
      situacion,
      provenance,
    );
    expect(candidate.zones).toHaveLength(7);
    expect(JSON.stringify(candidate)).not.toContain("fixture deliberately");
  });

  it("rejects a duplicate or incomplete zone set", () => {
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          invalidDuplicateZoneFixture,
          validSituacionFixture,
          provenance,
        ),
      "DUPLICATE_ZONE_ID",
    );

    const unknown = cloneFixture(validPrevifocFixture);
    unknown.z1[0]!.id = 60;
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          unknown,
          validSituacionFixture,
          provenance,
        ),
      "INVALID_ZONE_SET",
    );

    const missing = cloneFixture(validPrevifocFixture);
    missing.z1.pop();
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          missing,
          validSituacionFixture,
          provenance,
        ),
      "INVALID_ZONE_SET",
    );
  });

  it("rejects unknown nact and situations belonging to another advisory", () => {
    const unknown = cloneFixture(validPrevifocFixture);
    unknown.z1[0]!.nact = 99;
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          unknown,
          validSituacionFixture,
          provenance,
        ),
      "UNKNOWN_CURRENT_SITUATION",
    );

    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          invalidWrongAdvisoryFixture,
          provenance,
        ),
      "SITUATION_WRONG_ADVISORY",
    );
  });

  it("rejects an unknown forecast situation atomically", () => {
    const unknown = cloneFixture(validPrevifocFixture);
    unknown.z1[0]!.npre = 99;
    expectIngestionError(
      () => normalizeCurrentStateCandidate(unknown, validSituacionFixture, provenance),
      "UNKNOWN_FORECAST_SITUATION",
    );
  });

  it("validates the complete active catalog, including duplicates", () => {
    const inactive = cloneFixture(validSituacionFixture);
    inactive.SITUACION.find(
      (situation) => situation.ID_SITUACION === 8,
    )!.ACTIVO = "N";
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          inactive,
          provenance,
        ),
      "SITUATION_INACTIVE",
    );

    const unknown = cloneFixture(validSituacionFixture);
    unknown.SITUACION.push({
      ...unknown.SITUACION[1]!,
      ID_SITUACION: 99,
    });
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          unknown,
          provenance,
        ),
      "UNKNOWN_PREVIFOC_SITUATION_ID",
    );

    const duplicate = cloneFixture(validSituacionFixture);
    duplicate.SITUACION.push({ ...duplicate.SITUACION[1]! });
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          duplicate,
          provenance,
        ),
      "DUPLICATE_SITUATION_ID",
    );

    const missing = cloneFixture(validSituacionFixture);
    missing.SITUACION = missing.SITUACION.filter(
      (situation) => situation.ID_SITUACION !== 2,
    );
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          missing,
          provenance,
        ),
      "INVALID_SITUATION_CATALOG",
    );
  });

  it("rejects missing or mistyped mandatory fields", () => {
    const missingTime = cloneFixture(validPrevifocFixture) as Partial<
      typeof validPrevifocFixture
    >;
    delete missingTime.time;
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          missingTime,
          validSituacionFixture,
          provenance,
        ),
      "INVALID_REQUIRED_FIELD",
    );

    const wrongNact = cloneFixture(validPrevifocFixture) as unknown as {
      z1: Array<{ nact: unknown }>;
    };
    wrongNact.z1[0]!.nact = "9";
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          wrongNact,
          validSituacionFixture,
          provenance,
        ),
      "INVALID_REQUIRED_FIELD",
    );

    const missingActive = cloneFixture(validSituacionFixture) as unknown as {
      SITUACION: Array<Record<string, unknown>>;
    };
    delete missingActive.SITUACION[1]!.ACTIVO;
    expectIngestionError(
      () =>
        normalizeCurrentStateCandidate(
          validPrevifocFixture,
          missingActive,
          provenance,
        ),
      "INVALID_REQUIRED_FIELD",
    );
  });
});

describe("WORKER-002 source download", () => {
  it("starts both downloads in parallel and preserves retrieval provenance", async () => {
    const pending: Array<{
      url: string;
      resolve: (response: Response) => void;
    }> = [];
    const fetchImpl: typeof fetch = (input) =>
      new Promise((resolve) => {
        pending.push({ url: input.toString(), resolve });
      });

    const ingestion = ingestCurrentStateCandidate({
      fetch: fetchImpl,
      now: () => new Date("2026-07-18T09:10:11.000Z"),
      sleep: async () => undefined,
      timeoutMs: 1_000,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    });

    await Promise.resolve();
    expect(pending).toHaveLength(2);
    for (const request of pending) {
      request.resolve(
        request.url.endsWith("/situacion")
          ? jsonResponse(validSituacionFixture)
          : jsonResponse(validPrevifocFixture),
      );
    }

    const candidate = await ingestion;
    expect(candidate.provenance.previfoc).toMatchObject({
      source: "previfoc",
      requestedUrl: "https://example.test/previfoc",
      retrievedAt: "2026-07-18T09:10:11.000Z",
      attempts: 1,
    });
    expect(candidate.provenance.situacion).toMatchObject({
      source: "situacion",
      requestedUrl: "https://example.test/situacion",
      retrievedAt: "2026-07-18T09:10:11.000Z",
      attempts: 1,
    });
  });

  it("retries a transient HTTP failure exactly once", async () => {
    let previfocAttempts = 0;
    const sleep = vi.fn(async () => undefined);
    const fetchImpl: typeof fetch = async (input) => {
      const url = input.toString();
      if (url.endsWith("/situacion")) {
        return jsonResponse(validSituacionFixture);
      }
      previfocAttempts += 1;
      return previfocAttempts === 1
        ? jsonResponse({ upstream: "unavailable" }, 503)
        : jsonResponse(validPrevifocFixture);
    };

    const candidate = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      now: () => new Date("2026-07-18T09:10:11.000Z"),
      sleep,
      timeoutMs: 100,
      retryDelayMs: 7,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    });

    expect(previfocAttempts).toBe(2);
    expect(sleep).toHaveBeenCalledOnce();
    expect(sleep).toHaveBeenCalledWith(7);
    expect(candidate.provenance.previfoc.attempts).toBe(2);
  });

  it("does not retry a non-transient HTTP failure or expose its body", async () => {
    let previfocAttempts = 0;
    const secretBody = "private-upstream-body-should-never-appear";
    const fetchImpl: typeof fetch = async (input) => {
      if (input.toString().endsWith("/situacion")) {
        return jsonResponse(validSituacionFixture);
      }
      previfocAttempts += 1;
      return new Response(secretBody, {
        status: 400,
        headers: { "content-type": "text/plain" },
      });
    };

    const error = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      sleep: async () => undefined,
      timeoutMs: 100,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    }).catch((reason: unknown) => reason);

    expect(error).toMatchObject({ code: "HTTP_STATUS", source: "previfoc" });
    expect(String(error)).not.toContain(secretBody);
    expect(previfocAttempts).toBe(1);
  });

  it("aborts a timed-out attempt and succeeds on its single retry", async () => {
    let previfocAttempts = 0;
    const fetchImpl: typeof fetch = async (input, init) => {
      if (input.toString().endsWith("/situacion")) {
        return jsonResponse(validSituacionFixture);
      }
      previfocAttempts += 1;
      if (previfocAttempts === 2) return jsonResponse(validPrevifocFixture);

      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => reject(new DOMException("timed out", "AbortError")),
          { once: true },
        );
      });
    };

    const candidate = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      now: () => new Date("2026-07-18T09:10:11.000Z"),
      sleep: async () => undefined,
      timeoutMs: 1,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    });

    expect(previfocAttempts).toBe(2);
    expect(candidate.provenance.previfoc.attempts).toBe(2);
  });

  it("keeps the timeout active while the JSON response body is read", async () => {
    let previfocAttempts = 0;
    const fetchImpl: typeof fetch = async (input, init) => {
      if (input.toString().endsWith("/situacion")) {
        return jsonResponse(validSituacionFixture);
      }
      previfocAttempts += 1;
      if (previfocAttempts === 2) return jsonResponse(validPrevifocFixture);

      const signal = init?.signal;
      return new Response(
        new ReadableStream({
          start(controller) {
            signal?.addEventListener(
              "abort",
              () => controller.error(new DOMException("timed out", "AbortError")),
              { once: true },
            );
          },
        }),
        { headers: { "content-type": "application/json" } },
      );
    };

    const candidate = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      now: () => new Date("2026-07-18T09:10:11.000Z"),
      sleep: async () => undefined,
      timeoutMs: 1,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    });

    expect(previfocAttempts).toBe(2);
    expect(candidate.provenance.previfoc.attempts).toBe(2);
  });

  it("redacts fetch failures and emits no source bodies to console", async () => {
    const secret = "secret-body-or-token";
    const logSpies = [
      vi.spyOn(console, "log").mockImplementation(() => undefined),
      vi.spyOn(console, "info").mockImplementation(() => undefined),
      vi.spyOn(console, "warn").mockImplementation(() => undefined),
      vi.spyOn(console, "error").mockImplementation(() => undefined),
    ];
    const fetchImpl: typeof fetch = async () => {
      throw new Error(secret);
    };

    const error = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      sleep: async () => undefined,
      timeoutMs: 100,
      retryDelayMs: 1,
    }).catch((reason: unknown) => reason);

    expect(error).toMatchObject({ code: "FETCH_FAILED" });
    expect(String(error)).not.toContain(secret);
    for (const spy of logSpies) {
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    }
  });

  it("rejects invalid JSON without including the response body", async () => {
    const secretBody = "{not-json: secret-body}";
    const fetchImpl: typeof fetch = async (input) =>
      input.toString().endsWith("/situacion")
        ? jsonResponse(validSituacionFixture)
        : new Response(secretBody, {
            status: 200,
            headers: { "content-type": "application/json" },
          });

    const error = await ingestCurrentStateCandidate({
      fetch: fetchImpl,
      sleep: async () => undefined,
      timeoutMs: 100,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    }).catch((reason: unknown) => reason);

    expect(error).toMatchObject({ code: "INVALID_JSON" });
    expect(String(error)).not.toContain(secretBody);
  });

  it("can download and normalize both sources through an injected fetch", async () => {
    const candidate = await ingestCurrentStateCandidate({
      fetch: fixtureFetch(),
      now: () => new Date("2026-07-18T09:10:11.000Z"),
      sleep: async () => undefined,
      timeoutMs: 100,
      retryDelayMs: 1,
      previfocUrl: "https://example.test/previfoc",
      situacionUrl: "https://example.test/situacion",
    });

    expect(candidate.zones).toHaveLength(7);
    expect(candidate.zones[0]).toMatchObject({
      zoneId: 53,
      situationId: 1,
      level: 1,
      forestAccess: "no_closure_inferred",
    });
    expect(candidate.forecastNextDay.zones).toHaveLength(7);
  });
});
