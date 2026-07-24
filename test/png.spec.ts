import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";

import {
  crc32,
  forecastStripeColor,
  LEVEL_COLORS,
  PngPaletteError,
  recolorIndexedPng,
  STALE_COLOR,
  type Rgb,
} from "../src/png";

interface PngChunk {
  type: string;
  data: Uint8Array;
  crc: number;
  encoded: Uint8Array;
}

function chunks(png: Uint8Array): PngChunk[] {
  const view = new DataView(png.buffer, png.byteOffset, png.byteLength);
  const result: PngChunk[] = [];
  let offset = 8;
  while (offset < png.length) {
    const length = view.getUint32(offset, false);
    const dataOffset = offset + 8;
    const crcOffset = dataOffset + length;
    const type = String.fromCharCode(...png.subarray(offset + 4, dataOffset));
    result.push({
      type,
      data: png.slice(dataOffset, crcOffset),
      crc: view.getUint32(crcOffset, false),
      encoded: png.slice(offset, crcOffset + 4),
    });
    offset = crcOffset + 4;
  }
  return result;
}

async function coveredTemplate(): Promise<Uint8Array> {
  const response = await env.ASSETS.fetch(
    new Request("https://example.test/tiles/6/31/24.png"),
  );
  expect(response.status).toBe(200);
  return new Uint8Array(await response.arrayBuffer());
}

describe("WORKER-004 PNG palette mutator", () => {
  it("changes only PLTE zone RGB and its CRC while retaining a valid PNG", async () => {
    const original = await coveredTemplate();
    const colors: readonly Rgb[] = [
      LEVEL_COLORS[1],
      LEVEL_COLORS[1],
      LEVEL_COLORS[1],
      LEVEL_COLORS[2],
      LEVEL_COLORS[2],
      LEVEL_COLORS[3],
      LEVEL_COLORS[3],
    ];
    const recolored = recolorIndexedPng(original, colors);
    const before = chunks(original);
    const after = chunks(recolored);

    expect(after.map((chunk) => chunk.type)).toEqual([
      "IHDR",
      "PLTE",
      "tRNS",
      "IDAT",
      "IEND",
    ]);
    for (const [index, chunk] of after.entries()) {
      const typeBytes = recolored.subarray(
        12 + before.slice(0, index).reduce((size, item) => size + item.encoded.length, 0),
        16 + before.slice(0, index).reduce((size, item) => size + item.encoded.length, 0),
      );
      expect(chunk.crc).toBe(crc32(new Uint8Array([...typeBytes, ...chunk.data])));
      if (chunk.type !== "PLTE") {
        expect(chunk.encoded).toEqual(before[index]!.encoded);
      }
    }

    const palette = after.find((chunk) => chunk.type === "PLTE")!.data;
    expect(Array.from(palette.slice(3, 24))).toEqual(
      colors.flatMap((color) => Array.from(color)),
    );
    expect(Array.from(palette.slice(24, 45))).toEqual(
      colors.flatMap((color) => Array.from(color)),
    );
    expect(after.find((chunk) => chunk.type === "IDAT")!.data).toEqual(
      before.find((chunk) => chunk.type === "IDAT")!.data,
    );
  });

  it("darkens only the seven hatch entries for the forecast style", async () => {
    const colors: readonly Rgb[] = [
      LEVEL_COLORS[1], LEVEL_COLORS[2], LEVEL_COLORS[3], LEVEL_COLORS[1],
      LEVEL_COLORS[2], LEVEL_COLORS[3], LEVEL_COLORS[1],
    ];
    const result = recolorIndexedPng(await coveredTemplate(), colors, "forecast_hatch");
    const palette = chunks(result).find((chunk) => chunk.type === "PLTE")!.data;
    expect(Array.from(palette.slice(3, 24))).toEqual(
      colors.flatMap((color) => Array.from(color)),
    );
    expect(Array.from(palette.slice(24, 45))).toEqual(
      colors.flatMap((color) => Array.from(forecastStripeColor(color))),
    );
  });

  it("supports the seven-zone gray safety palette", async () => {
    const result = recolorIndexedPng(
      await coveredTemplate(),
      Array<Rgb>(7).fill(STALE_COLOR),
    );
    const palette = chunks(result).find((chunk) => chunk.type === "PLTE")!.data;
    expect(Array.from(palette.slice(3, 24))).toEqual(
      Array(7).fill([0x80, 0x80, 0x80]).flat(),
    );
  });

  it("rejects invalid signatures, corrupt chunks, and incomplete palettes", async () => {
    const template = await coveredTemplate();
    const colors = Array<Rgb>(7).fill(STALE_COLOR);
    const invalidSignature = new Uint8Array(template);
    invalidSignature[0] = 0;
    const corruptChunk = new Uint8Array(template);
    corruptChunk[20] ^= 0xff;

    expect(() => recolorIndexedPng(invalidSignature, colors)).toThrow(
      PngPaletteError,
    );
    expect(() => recolorIndexedPng(corruptChunk, colors)).toThrow(
      PngPaletteError,
    );
    expect(() => recolorIndexedPng(template, colors.slice(1))).toThrow(
      "exactly seven",
    );
  });
});
