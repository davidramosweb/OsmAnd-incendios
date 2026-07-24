#!/usr/bin/env python3
"""Genera, recolorea y valida el PNG indexado congelado de TILES-001.

El recoloreado modifica exclusivamente las entradas RGB 1–14 de PLTE y su CRC.
No decodifica píxeles, no toca tRNS y conserva IDAT byte a byte.
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile
from typing import Any, Sequence
import zlib


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tiles-001"

FORMAT_VERSION = "previfoc-indexed-template-v2"
GEOMETRY_VERSION = (
    "sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0"
)
FROZEN_HASHES = {
    "master": "e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
    "geojson": "b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2",
    "crosswalk": "0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876",
}
FROZEN_PATHS = {
    "master": PROJECT_ROOT / "data" / "zones" / "zones.gpkg",
    "geojson": PROJECT_ROOT / "data" / "zones" / "zones.geojson",
    "crosswalk": PROJECT_ROOT / "data" / "crosswalk" / "crosswalk.csv",
}
GEO004_MANIFEST = PROJECT_ROOT / "data" / "geo-004" / "manifest.json"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WIDTH = 256
HEIGHT = 256
BIT_DEPTH = 8
COLOR_TYPE = 3
CHUNK_ORDER = (b"IHDR", b"PLTE", b"tRNS", b"IDAT", b"IEND")

# Marcadores de identidad, deliberadamente ajenos al estilo final del producto.
MARKER_PALETTE = (
    (0x00, 0x00, 0x00),  # 0: fondo; RGB invisible por alpha 0
    (0x11, 0x22, 0x33),  # 1: zona 53 / 1N
    (0x22, 0x33, 0x44),  # 2: zona 54 / 1S
    (0x33, 0x44, 0x55),  # 3: zona 55 / 2
    (0x44, 0x55, 0x66),  # 4: zona 56 / 3
    (0x55, 0x66, 0x77),  # 5: zona 57 / 4
    (0x66, 0x77, 0x88),  # 6: zona 58 / 5
    (0x77, 0x88, 0x99),  # 7: zona 59 / 6
    (0x18, 0x29, 0x3A),  # 8: trama zona 53 / 1N
    (0x29, 0x3A, 0x4B),  # 9: trama zona 54 / 1S
    (0x3A, 0x4B, 0x5C),  # 10: trama zona 55 / 2
    (0x4B, 0x5C, 0x6D),  # 11: trama zona 56 / 3
    (0x5C, 0x6D, 0x7E),  # 12: trama zona 57 / 4
    (0x6D, 0x7E, 0x8F),  # 13: trama zona 58 / 5
    (0x7E, 0x8F, 0xA0),  # 14: trama zona 59 / 6
    (0x00, 0x00, 0x00),  # 15: límites negros
)

# Vector de prueba multicolor; tampoco define colores finales de producto.
RECOLORED_TEST_VECTOR = (
    (0xA0, 0x10, 0x20),
    (0x10, 0xA0, 0x20),
    (0x10, 0x20, 0xA0),
    (0xA0, 0x80, 0x10),
    (0x80, 0x10, 0xA0),
    (0x10, 0xA0, 0xA0),
    (0x60, 0x60, 0x60),
)

# floor(porcentaje * 255 + 0.5): 0.30 -> 77; 0.70 -> 179.
ZONE_ALPHA = 77
BOUNDARY_ALPHA = 179
ALPHA_TABLE = (0,) + (ZONE_ALPHA,) * 14 + (BOUNDARY_ALPHA,)

ORIGINAL_NAME = "fixture-original.png"
RECOLORED_NAME = "fixture-recolored.png"
TRANSPARENT_NAME = "fixture-transparent.png"
REPORT_NAME = "REPORT.md"
MANIFEST_NAME = "manifest.json"


class TileTemplateError(RuntimeError):
    """Fallo de contrato, integridad, entrada congelada o reproducibilidad."""


@dataclass(frozen=True)
class PngChunk:
    chunk_type: bytes
    data: bytes
    crc: int


@dataclass(frozen=True)
class DecodedIndexedPng:
    width: int
    height: int
    indices: bytes
    palette: tuple[tuple[int, int, int], ...]
    alpha: tuple[int, ...]

    def rgba_bytes(self) -> bytes:
        rgba = bytearray()
        for index in self.indices:
            if index >= len(self.palette):
                raise TileTemplateError(f"índice {index} fuera de PLTE")
            red, green, blue = self.palette[index]
            alpha = self.alpha[index] if index < len(self.alpha) else 255
            rgba.extend((red, green, blue, alpha))
        return bytes(rgba)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise TileTemplateError(f"no se puede leer {path}: {exc}") from exc
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _load_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TileTemplateError(f"no se puede leer {description} {path}: {exc}") from exc


def verify_frozen_geometry() -> dict[str, str]:
    """Comprueba la aprobación y los bytes inmutables sin regenerarlos."""
    manifest = _load_json(GEO004_MANIFEST, "el manifiesto de GEO-004")
    if manifest.get("status") != "approved":
        raise TileTemplateError("GEO-004 no está aprobado")
    if manifest.get("approval", {}).get("approved") is not True:
        raise TileTemplateError("falta la aprobación explícita de GEO-004")
    if manifest.get("geometry_version") != GEOMETRY_VERSION:
        raise TileTemplateError("geometry_version contradice la versión congelada")

    manifest_inputs = manifest.get("inputs", {})
    for name, expected in FROZEN_HASHES.items():
        recorded = manifest_inputs.get(name, {}).get("sha256")
        if recorded != expected:
            raise TileTemplateError(
                f"hash congelado de {name} contradictorio en GEO-004: {recorded}"
            )
        observed = sha256_file(FROZEN_PATHS[name])
        if observed != expected:
            raise TileTemplateError(
                f"hash congelado de {name} modificado: {observed}; esperado {expected}"
            )
    return {
        "geo004_manifest": sha256_file(GEO004_MANIFEST),
        **FROZEN_HASHES,
    }


def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    if len(chunk_type) != 4:
        raise TileTemplateError("el tipo de chunk debe ocupar cuatro bytes")
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def parse_png(content: bytes, *, verify_crc: bool = True) -> tuple[PngChunk, ...]:
    if not content.startswith(PNG_SIGNATURE):
        raise TileTemplateError("firma PNG inválida")
    chunks: list[PngChunk] = []
    offset = len(PNG_SIGNATURE)
    while offset < len(content):
        if len(content) - offset < 12:
            raise TileTemplateError("chunk PNG truncado")
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        chunk_type = content[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(content):
            raise TileTemplateError("longitud de chunk PNG fuera del archivo")
        data = content[data_start:data_end]
        crc = struct.unpack(">I", content[data_end:crc_end])[0]
        expected_crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        if verify_crc and crc != expected_crc:
            name = chunk_type.decode("ascii", errors="replace")
            raise TileTemplateError(f"CRC inválido en {name}")
        chunks.append(PngChunk(chunk_type, data, crc))
        offset = crc_end
        if chunk_type == b"IEND":
            if offset != len(content):
                raise TileTemplateError("bytes residuales después de IEND")
            break
    if not chunks or chunks[-1].chunk_type != b"IEND":
        raise TileTemplateError("falta IEND")
    return tuple(chunks)


def _palette_from_bytes(data: bytes) -> tuple[tuple[int, int, int], ...]:
    if len(data) % 3:
        raise TileTemplateError("PLTE no contiene tripletas RGB completas")
    return tuple(tuple(data[pos : pos + 3]) for pos in range(0, len(data), 3))  # type: ignore[misc]


def validate_contract(content: bytes) -> tuple[PngChunk, ...]:
    chunks = parse_png(content)
    if tuple(chunk.chunk_type for chunk in chunks) != CHUNK_ORDER:
        observed = [chunk.chunk_type.decode("ascii", errors="replace") for chunk in chunks]
        raise TileTemplateError(f"orden o conjunto de chunks no permitido: {observed}")

    expected_ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, BIT_DEPTH, COLOR_TYPE, 0, 0, 0)
    if chunks[0].data != expected_ihdr:
        raise TileTemplateError("IHDR no coincide con 256×256, indexed-8, no entrelazado")
    if len(chunks[1].data) != 48:
        raise TileTemplateError("PLTE debe tener exactamente dieciséis entradas (48 bytes)")
    if len(chunks[2].data) != 16:
        raise TileTemplateError("tRNS debe tener exactamente dieciséis entradas")
    if tuple(chunks[2].data) != ALPHA_TABLE:
        raise TileTemplateError("tRNS no coincide con alpha 0/77/179 congelado")
    if not chunks[3].data:
        raise TileTemplateError("IDAT no puede estar vacío")
    if chunks[4].data:
        raise TileTemplateError("IEND debe estar vacío")
    return chunks


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    distance_left = abs(estimate - left)
    distance_above = abs(estimate - above)
    distance_upper_left = abs(estimate - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def decode_indexed_png(content: bytes) -> DecodedIndexedPng:
    """Decodificador stdlib independiente de Pillow para indexed-8 PNG."""
    chunks = validate_contract(content)
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(chunks[3].data) + decompressor.flush()
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise TileTemplateError("flujo zlib de IDAT incompleto o con bytes residuales")
    stride = WIDTH
    if len(raw) != HEIGHT * (stride + 1):
        raise TileTemplateError("IDAT decodificado no tiene 256 scanlines completas")

    rows: list[bytes] = []
    offset = 0
    previous = bytes(stride)
    for _row_number in range(HEIGHT):
        filter_type = raw[offset]
        filtered = raw[offset + 1 : offset + 1 + stride]
        offset += stride + 1
        reconstructed = bytearray(stride)
        for column, value in enumerate(filtered):
            left = reconstructed[column - 1] if column else 0
            above = previous[column]
            upper_left = previous[column - 1] if column else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise TileTemplateError(f"filtro PNG no soportado: {filter_type}")
            reconstructed[column] = (value + predictor) & 0xFF
        previous = bytes(reconstructed)
        rows.append(previous)

    indices = b"".join(rows)
    if any(index > 15 for index in indices):
        raise TileTemplateError("el ráster usa índices fuera del contrato 0–15")
    return DecodedIndexedPng(
        WIDTH,
        HEIGHT,
        indices,
        _palette_from_bytes(chunks[1].data),
        tuple(chunks[2].data),
    )


def _fixture_indices() -> bytes:
    """Dos polígonos sintéticos, borde exterior y límite común, sin AA."""
    pixels = bytearray(WIDTH * HEIGHT)
    for y in range(48, 208):
        for x in range(32, 224):
            if y <= 50 or y >= 205 or x <= 34 or x >= 221:
                index = 15
            elif 127 <= x <= 129:
                index = 15
            elif x <= 126:
                index = 8 if (x + y) % 12 < 2 else 1
            else:
                index = 9 if (x + y) % 12 < 2 else 2
            pixels[y * WIDTH + x] = index
    return bytes(pixels)


def encode_indexed_png(
    indices: bytes,
    *,
    palette: Sequence[Sequence[int]] = MARKER_PALETTE,
) -> bytes:
    if len(indices) != WIDTH * HEIGHT:
        raise TileTemplateError("el fixture debe contener exactamente 256×256 índices")
    if any(index > 15 for index in indices):
        raise TileTemplateError("solo se permiten índices 0–15")
    normalized = _normalize_palette(palette, expected_entries=16)
    rows = [
        b"\x00" + indices[y * WIDTH : (y + 1) * WIDTH]
        for y in range(HEIGHT)
    ]
    compressed = zlib.compress(b"".join(rows), level=9)
    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, BIT_DEPTH, COLOR_TYPE, 0, 0, 0)
    plte = bytes(component for rgb in normalized for component in rgb)
    return PNG_SIGNATURE + b"".join(
        (
            _make_chunk(b"IHDR", ihdr),
            _make_chunk(b"PLTE", plte),
            _make_chunk(b"tRNS", bytes(ALPHA_TABLE)),
            _make_chunk(b"IDAT", compressed),
            _make_chunk(b"IEND", b""),
        )
    )


def _normalize_palette(
    palette: Sequence[Sequence[int]], *, expected_entries: int
) -> tuple[tuple[int, int, int], ...]:
    if len(palette) != expected_entries:
        raise TileTemplateError(f"se requieren {expected_entries} colores RGB")
    normalized: list[tuple[int, int, int]] = []
    for entry in palette:
        if len(entry) != 3 or any(
            not isinstance(component, int) or isinstance(component, bool) or not 0 <= component <= 255
            for component in entry
        ):
            raise TileTemplateError(f"color RGB inválido: {entry!r}")
        normalized.append((entry[0], entry[1], entry[2]))
    return tuple(normalized)


def recolor_png(content: bytes, zone_colors: Sequence[Sequence[int]]) -> bytes:
    """Sustituye las parejas base/trama, recalcula PLTE y preserva el resto."""
    colors = _normalize_palette(zone_colors, expected_entries=7)
    chunks = validate_contract(content)
    original_plte = bytearray(chunks[1].data)
    for index, color in enumerate(colors, start=1):
        original_plte[index * 3 : index * 3 + 3] = bytes(color)
        original_plte[(index + 7) * 3 : (index + 7) * 3 + 3] = bytes(color)

    result = PNG_SIGNATURE + b"".join(
        _make_chunk(chunk.chunk_type, bytes(original_plte) if chunk.chunk_type == b"PLTE" else chunk.data)
        for chunk in chunks
    )
    result_chunks = validate_contract(result)
    if result_chunks[3].data != chunks[3].data:
        raise TileTemplateError("el recoloreado alteró IDAT")
    for before, after in zip(chunks, result_chunks):
        if before.chunk_type != b"PLTE" and before != after:
            raise TileTemplateError(f"el recoloreado alteró {before.chunk_type!r}")
    return result


def _render_report(fixtures: dict[str, bytes], frozen: dict[str, str]) -> bytes:
    original_chunks = validate_contract(fixtures[ORIGINAL_NAME])
    lines = [
        "# TILES-001 — Formato PNG indexado congelado",
        "",
        f"**Versión:** `{FORMAT_VERSION}`  ",
        f"**Geometría consumida:** `{GEOMETRY_VERSION}`",
        "",
        "## Contrato binario",
        "",
        "PNG 256×256, profundidad 8, color tipo 3 (indexado), compresión 0, filtro 0 e interlace 0 en IHDR. El archivo contiene exactamente un chunk de cada tipo y en este orden: `IHDR` (13 bytes), `PLTE` (48), `tRNS` (16), `IDAT` y `IEND` (0). Cada CRC-32 se calcula sobre `tipo || datos`.",
        "",
        "`PLTE` tiene dieciséis tripletas. Los índices 1–7 son rellenos base, 8–14 son las bandas diagonales de esas mismas zonas y 15 representa límites. El Worker asigna el mismo RGB a ambas variantes para hoy y oscurece 8–14 para mañana. El recoloreador sustituye únicamente esas catorce entradas y el CRC de PLTE; IDAT permanece idéntico.",
        "",
        "## Alpha exacto",
        "",
        "La conversión fijada es `floor(fracción × 255 + 0.5)` (redondeo half up): fondo 0 % → `0`, los catorce índices de zona 30 % → `77` y límites 70 % → `179`.",
        "",
        "## Fixture y limitaciones",
        "",
        "El único ráster de prueba con contenido es sintético: dos zonas rectangulares, bandas diagonales globales, fondo 0 y límites en índice 15. No usa geometría geográfica, etiquetas, iconos ni antialias. El fixture transparente usa solo índice 0.",
        "",
        "## Fixtures",
        "",
    ]
    for name in (ORIGINAL_NAME, RECOLORED_NAME, TRANSPARENT_NAME):
        lines.append(
            f"- `{name}`: SHA-256 `{sha256_bytes(fixtures[name])}`, {len(fixtures[name])} bytes."
        )
    lines.extend(
        [
            "",
            f"El `IDAT` compartido por original/recoloreado mide {len(original_chunks[3].data)} bytes y tiene SHA-256 `{sha256_bytes(original_chunks[3].data)}`.",
            "",
            "## Comandos",
            "",
            "```sh",
            ".venv-geo/bin/python tools/tile_template.py build",
            ".venv-geo/bin/python tools/tile_template.py validate",
            ".venv-geo/bin/python -m unittest tests.test_tile_template -v",
            ".venv-geo/bin/python tools/tile_template.py recolor entrada.png salida.png --colors '#112233' '#223344' '#334455' '#445566' '#556677' '#667788' '#778899'",
            "```",
            "",
            "`validate` comprueba primero la aprobación y los hashes congelados de GEO-004/GEO-003, regenera los artefactos en memoria y exige igualdad byte a byte. Las pruebas decodifican con Pillow y con un decodificador PNG independiente basado en la biblioteca estándar.",
            "",
            "## Entrada congelada",
            "",
            f"- `zones.gpkg`: `{frozen['master']}`.",
            f"- `zones.geojson`: `{frozen['geojson']}`.",
            f"- `crosswalk.csv`: `{frozen['crosswalk']}`.",
            f"- `data/geo-004/manifest.json`: `{frozen['geo004_manifest']}`.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def build_artifacts() -> dict[str, bytes]:
    frozen = verify_frozen_geometry()
    original = encode_indexed_png(_fixture_indices())
    recolored = recolor_png(original, RECOLORED_TEST_VECTOR)
    transparent = encode_indexed_png(bytes(WIDTH * HEIGHT))
    fixtures = {
        ORIGINAL_NAME: original,
        RECOLORED_NAME: recolored,
        TRANSPARENT_NAME: transparent,
    }
    if validate_contract(original)[3].data != validate_contract(recolored)[3].data:
        raise TileTemplateError("IDAT cambió al construir el fixture recoloreado")
    for content in fixtures.values():
        decode_indexed_png(content)

    report = _render_report(fixtures, frozen)
    original_chunks = validate_contract(original)
    manifest = {
        "contract": {
            "alpha_conversion": "floor(fraction * 255 + 0.5)",
            "alpha_entries": list(ALPHA_TABLE),
            "bit_depth": BIT_DEPTH,
            "chunk_lengths": {
                "IHDR": 13,
                "PLTE": 48,
                "tRNS": 16,
                "IEND": 0,
            },
            "chunk_order": [value.decode("ascii") for value in CHUNK_ORDER],
            "color_type": COLOR_TYPE,
            "dimensions_pixels": [WIDTH, HEIGHT],
            "idat_count": 1,
            "index_meaning": {
                "0": "background_transparent",
                "1": "zone_53_1N",
                "2": "zone_54_1S",
                "3": "zone_55_2",
                "4": "zone_56_3",
                "5": "zone_57_4",
                "6": "zone_58_5",
                "7": "zone_59_6",
                "8": "zone_53_1N_hatch",
                "9": "zone_54_1S_hatch",
                "10": "zone_55_2_hatch",
                "11": "zone_56_3_hatch",
                "12": "zone_57_4_hatch",
                "13": "zone_58_5_hatch",
                "14": "zone_59_6_hatch",
                "15": "black_boundaries",
            },
            "marker_palette_rgb": [list(entry) for entry in MARKER_PALETTE],
            "recolor_mutation": "PLTE RGB entries 1-14 and PLTE CRC only; IDAT byte-identical",
        },
        "format_schema_version": 2,
        "format_version": FORMAT_VERSION,
        "geometry_version": GEOMETRY_VERSION,
        "inputs": {
            "crosswalk": {"path": "../crosswalk/crosswalk.csv", "sha256": frozen["crosswalk"]},
            "geo004_manifest": {"path": "../geo-004/manifest.json", "sha256": frozen["geo004_manifest"]},
            "geojson": {"path": "../zones/zones.geojson", "sha256": frozen["geojson"]},
            "master": {"path": "../zones/zones.gpkg", "sha256": frozen["master"]},
        },
        "outputs": {
            name: {
                "dimensions_pixels": [WIDTH, HEIGHT],
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
            for name, content in fixtures.items()
        }
        | {
            REPORT_NAME: {
                "sha256": sha256_bytes(report),
                "size_bytes": len(report),
            }
        },
        "shared_original_recolored_idat": {
            "sha256": sha256_bytes(original_chunks[3].data),
            "size_bytes": len(original_chunks[3].data),
        },
        "software": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "zlib_compile": zlib.ZLIB_VERSION,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        },
        "status": "frozen",
    }
    return fixtures | {REPORT_NAME: report, MANIFEST_NAME: _json_bytes(manifest)}


def build(output_directory: Path = DEFAULT_OUTPUT) -> None:
    artifacts = build_artifacts()
    for name, content in artifacts.items():
        _atomic_write(output_directory / name, content)
    manifest = json.loads(artifacts[MANIFEST_NAME])
    print(f"directorio: {output_directory}")
    print(f"formato: {manifest['format_version']}")
    for name in (ORIGINAL_NAME, RECOLORED_NAME, TRANSPARENT_NAME):
        print(f"{name}: {manifest['outputs'][name]['sha256']}")


def validate(output_directory: Path = DEFAULT_OUTPUT) -> None:
    expected = build_artifacts()
    for name, expected_content in expected.items():
        path = output_directory / name
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise TileTemplateError(f"no se puede leer {path}: {exc}") from exc
        if observed != expected_content:
            raise TileTemplateError(
                f"artefacto no reproducible: {path}; observado {sha256_bytes(observed)}, "
                f"esperado {sha256_bytes(expected_content)}"
            )
    manifest = json.loads(expected[MANIFEST_NAME])
    print(f"directorio: {output_directory}")
    print(f"formato congelado: {manifest['format_version']}")
    print(f"geometry_version: {manifest['geometry_version']}")
    print("artefactos reproducibles: 5; IDAT original/recoloreado: idéntico")


def _parse_color(value: str) -> tuple[int, int, int]:
    candidate = value[1:] if value.startswith("#") else value
    if len(candidate) != 6:
        raise argparse.ArgumentTypeError("el color debe tener formato #RRGGBB")
    try:
        raw = bytes.fromhex(candidate)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("el color debe tener formato #RRGGBB") from exc
    return raw[0], raw[1], raw[2]


def inspect_png(path: Path) -> None:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise TileTemplateError(f"no se puede leer {path}: {exc}") from exc
    chunks = validate_contract(content)
    decoded = decode_indexed_png(content)
    summary = {
        "chunks": [
            {
                "crc": f"{chunk.crc:08x}",
                "length": len(chunk.data),
                "type": chunk.chunk_type.decode("ascii"),
            }
            for chunk in chunks
        ],
        "dimensions_pixels": [decoded.width, decoded.height],
        "format_version": FORMAT_VERSION,
        "idat_sha256": sha256_bytes(chunks[3].data),
        "indices_used": sorted(set(decoded.indices)),
        "sha256": sha256_bytes(content),
    }
    sys.stdout.buffer.write(_json_bytes(summary))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="construye los fixtures TILES-001")
    build_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    validate_parser = commands.add_parser("validate", help="revalida bytes y geometría congelada")
    validate_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    recolor_parser = commands.add_parser("recolor", help="recolorea PLTE[1:15] sin tocar IDAT")
    recolor_parser.add_argument("input", type=Path)
    recolor_parser.add_argument("output", type=Path)
    recolor_parser.add_argument("--colors", nargs=7, type=_parse_color, required=True)
    inspect_parser = commands.add_parser("inspect", help="muestra estructura e índices")
    inspect_parser.add_argument("input", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            build(args.output.resolve())
        elif args.command == "validate":
            validate(args.output.resolve())
        elif args.command == "recolor":
            source = args.input.read_bytes()
            _atomic_write(args.output.resolve(), recolor_png(source, args.colors))
            print(f"salida: {args.output.resolve()}")
        elif args.command == "inspect":
            inspect_png(args.input.resolve())
        else:  # pragma: no cover
            raise TileTemplateError(f"comando no soportado: {args.command}")
    except (OSError, TileTemplateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
