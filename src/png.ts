export type Rgb = readonly [red: number, green: number, blue: number];

export const LEVEL_COLORS = {
  1: [0xa4, 0xcc, 0x87],
  2: [0xff, 0x97, 0x00],
  3: [0xe8, 0x3d, 0x35],
} as const satisfies Record<1 | 2 | 3, Rgb>;

export const STALE_COLOR = [0x80, 0x80, 0x80] as const satisfies Rgb;

const PNG_SIGNATURE = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);
const PLTE = 0x504c5445;
const IEND = 0x49454e44;
const EXPECTED_PALETTE_BYTES = 48;
const FIRST_ZONE_PALETTE_OFFSET = 3;
const FIRST_HATCH_PALETTE_OFFSET = 24;

export type TileStyle = "solid" | "forecast_hatch";

export function forecastStripeColor(color: Rgb): Rgb {
  return color.map((component) => Math.round(component * 0.55)) as unknown as Rgb;
}

export class PngPaletteError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PngPaletteError";
  }
}

function makeCrcTable(): Uint32Array {
  const table = new Uint32Array(256);
  for (let value = 0; value < table.length; value += 1) {
    let crc = value;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc & 1) === 1 ? 0xedb88320 ^ (crc >>> 1) : crc >>> 1;
    }
    table[value] = crc >>> 0;
  }
  return table;
}

const CRC_TABLE = makeCrcTable();

export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ byte) & 0xff]!;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function assertColor(color: Rgb): void {
  if (
    color.length !== 3 ||
    color.some((component) =>
      !Number.isInteger(component) || component < 0 || component > 255
    )
  ) {
    throw new TypeError("palette colors must contain three RGB bytes");
  }
}

function readUint32(view: DataView, offset: number): number {
  return view.getUint32(offset, false);
}

/**
 * Replaces RGB entries 1-14 of PLTE and that chunk's CRC. Every other
 * byte, including IDAT and tRNS, remains byte-identical.
 */
export function recolorIndexedPng(
  input: ArrayBuffer | Uint8Array,
  zoneColors: readonly Rgb[],
  style: TileStyle = "solid",
): Uint8Array {
  if (zoneColors.length !== 7) {
    throw new TypeError("exactly seven zone colors are required");
  }
  zoneColors.forEach(assertColor);

  const source = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (
    source.length < PNG_SIGNATURE.length ||
    PNG_SIGNATURE.some((byte, index) => source[index] !== byte)
  ) {
    throw new PngPaletteError("invalid PNG signature");
  }

  const output = new Uint8Array(source);
  const view = new DataView(output.buffer);
  let offset = PNG_SIGNATURE.length;
  let paletteOffset: number | null = null;
  let paletteCrcOffset: number | null = null;
  let sawEnd = false;

  while (offset < output.length) {
    if (offset + 12 > output.length) {
      throw new PngPaletteError("truncated PNG chunk header");
    }

    const length = readUint32(view, offset);
    const typeOffset = offset + 4;
    const dataOffset = offset + 8;
    const crcOffset = dataOffset + length;
    const nextOffset = crcOffset + 4;
    if (nextOffset > output.length || nextOffset < crcOffset) {
      throw new PngPaletteError("truncated PNG chunk data");
    }

    const expectedCrc = readUint32(view, crcOffset);
    const actualCrc = crc32(output.subarray(typeOffset, crcOffset));
    if (expectedCrc !== actualCrc) {
      throw new PngPaletteError("PNG chunk has an invalid CRC");
    }

    const type = readUint32(view, typeOffset);
    if (type === PLTE) {
      if (paletteOffset !== null) {
        throw new PngPaletteError("PNG contains more than one PLTE chunk");
      }
      if (length !== EXPECTED_PALETTE_BYTES) {
        throw new PngPaletteError("PLTE must contain exactly nine RGB entries");
      }
      paletteOffset = dataOffset;
      paletteCrcOffset = crcOffset;
    }

    if (type === IEND) {
      if (length !== 0 || nextOffset !== output.length) {
        throw new PngPaletteError("IEND must be the final empty PNG chunk");
      }
      sawEnd = true;
    }
    offset = nextOffset;
  }

  if (!sawEnd) throw new PngPaletteError("PNG has no IEND chunk");
  if (paletteOffset === null || paletteCrcOffset === null) {
    throw new PngPaletteError("PNG has no PLTE chunk");
  }

  for (const [index, color] of zoneColors.entries()) {
    output.set(color, paletteOffset + FIRST_ZONE_PALETTE_OFFSET + index * 3);
    output.set(
      style === "forecast_hatch" ? forecastStripeColor(color) : color,
      paletteOffset + FIRST_HATCH_PALETTE_OFFSET + index * 3,
    );
  }
  view.setUint32(
    paletteCrcOffset,
    crc32(output.subarray(paletteOffset - 4, paletteCrcOffset)),
    false,
  );
  return output;
}
