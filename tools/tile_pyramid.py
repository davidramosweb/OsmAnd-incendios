#!/usr/bin/env python3
"""Genera y valida la pirámide XYZ indexada congelada de TILES-002."""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence

try:
    import pyproj
    import shapely
    from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Polygon, box
    from shapely.ops import transform as transform_geometry, unary_union
    from shapely.strtree import STRtree
    from PIL import Image, ImageChops, ImageDraw
except ModuleNotFoundError as exc:  # pragma: no cover - mensaje comprobado por CLI
    raise SystemExit(f"faltan dependencias de requirements-geo-004.txt: {exc}") from exc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import geo_zones, tile_template


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "tiles-002"
MASTER_PATH = PROJECT_ROOT / "data" / "zones" / "zones.gpkg"
FORMAT_VERSION = tile_template.FORMAT_VERSION
GEOMETRY_VERSION = tile_template.GEOMETRY_VERSION

MIN_ZOOM = 6
MAX_ZOOM = 14
TILE_SIZE = 256
BOUNDARY_WIDTH = 2
OVERSCAN = 8
HATCH_SPACING = 12
HATCH_WIDTH = 2
MAX_ASSETS = 19_000
CONTROL_MAX_DIMENSION = 1536

WEB_MERCATOR_HALF_WORLD = 20037508.342789244
WEB_MERCATOR_WORLD = WEB_MERCATOR_HALF_WORLD * 2.0
ZONE_IDS = tuple(range(53, 60))
ZONE_CODES = ("1N", "1S", "2", "3", "4", "5", "6")

TRANSPARENT_NAME = "transparent.png"
INVENTORY_NAME = "tiles.sha256"
REPORT_NAME = "REPORT.md"
MANIFEST_NAME = "manifest.json"
CONTROL_ZOOMS = (6, 10, 14)


class TilePyramidError(RuntimeError):
    """Fallo de entrada, contrato XYZ, render, inventario o reproducibilidad."""


@dataclass(frozen=True)
class ProjectedPolygon:
    zone_id: int
    zone_index: int
    geometry: Polygon


@dataclass
class RenderDataset:
    polygons: tuple[ProjectedPolygon, ...]
    polygon_geometries: tuple[Polygon, ...]
    polygon_tree: STRtree
    boundaries: tuple[Any, ...]
    boundary_tree: STRtree
    bounds: tuple[float, float, float, float]
    zone_geometries: dict[int, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise TilePyramidError(f"no se puede leer {path}: {exc}") from exc
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _run_prerequisites() -> None:
    commands = (
        ("geo_sources.py", "validate"),
        ("geo_crosswalk.py", "validate"),
        ("geo_zones.py", "validate"),
        ("geo_compare.py", "validate"),
        ("tile_template.py", "validate"),
    )
    # No resolver el symlink del venv: el ejecutable base no ve sus site-packages.
    python = Path(sys.executable)
    for script, command in commands:
        completed = subprocess.run(
            [str(python), str(PROJECT_ROOT / "tools" / script), command],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if completed.returncode != 0:
            raise TilePyramidError(f"barrera obligatoria fallida: {script} {command}")


def _polygon_parts(geometry: Any) -> Iterable[Polygon]:
    if isinstance(geometry, Polygon):
        yield geometry
    elif isinstance(geometry, (MultiPolygon, GeometryCollection)):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def _line_parts(geometry: Any) -> Iterable[Any]:
    if isinstance(geometry, LineString):
        if not geometry.is_empty:
            yield geometry
    elif isinstance(geometry, (MultiLineString, GeometryCollection)):
        for part in geometry.geoms:
            yield from _line_parts(part)


def dataset_from_projected(zone_geometries: dict[int, Any]) -> RenderDataset:
    records: list[ProjectedPolygon] = []
    boundaries: list[Any] = []
    for zone_id in sorted(zone_geometries):
        if zone_id not in ZONE_IDS:
            raise TilePyramidError(f"zone_id fuera del contrato: {zone_id}")
        zone_index = zone_id - 52
        for polygon in _polygon_parts(zone_geometries[zone_id]):
            if polygon.is_empty or not polygon.is_valid:
                raise TilePyramidError(f"polígono vacío o inválido en zona {zone_id}")
            records.append(ProjectedPolygon(zone_id, zone_index, polygon))
            boundaries.extend(_line_parts(polygon.boundary))
    if not records or not boundaries:
        raise TilePyramidError("el dataset proyectado no contiene superficies y límites")
    polygon_geometries = tuple(record.geometry for record in records)
    min_x = min(geometry.bounds[0] for geometry in polygon_geometries)
    min_y = min(geometry.bounds[1] for geometry in polygon_geometries)
    max_x = max(geometry.bounds[2] for geometry in polygon_geometries)
    max_y = max(geometry.bounds[3] for geometry in polygon_geometries)
    return RenderDataset(
        tuple(records),
        polygon_geometries,
        STRtree(polygon_geometries),
        tuple(boundaries),
        STRtree(boundaries),
        (min_x, min_y, max_x, max_y),
        dict(sorted(zone_geometries.items())),
    )


def load_projected_dataset() -> RenderDataset:
    """Lee EPSG:25830 y lo reproyecta solo en memoria para el render."""
    tile_template.verify_frozen_geometry()
    try:
        uri = f"file:{MASTER_PATH.resolve()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise TilePyramidError("integrity_check de zones.gpkg no es ok")
            metadata = connection.execute(
                "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns "
                "WHERE table_name='zones' AND column_name='geom'"
            ).fetchone()
            if metadata is None or tuple(metadata) != ("MULTIPOLYGON", 25830):
                raise TilePyramidError("zones.gpkg no conserva MULTIPOLYGON EPSG:25830")
            rows = connection.execute(
                "SELECT zone_id, zone_code, geom FROM zones ORDER BY zone_id"
            ).fetchall()
    except TilePyramidError:
        raise
    except sqlite3.Error as exc:
        raise TilePyramidError(f"no se puede leer zones.gpkg: {exc}") from exc
    if [row["zone_id"] for row in rows] != list(ZONE_IDS):
        raise TilePyramidError("zones.gpkg no contiene exactamente IDs 53–59 ordenados")
    if [row["zone_code"] for row in rows] != list(ZONE_CODES):
        raise TilePyramidError("zones.gpkg no contiene exactamente códigos 1N–6")

    transformer = pyproj.Transformer.from_crs(25830, 3857, always_xy=True)
    projected: dict[int, Any] = {}
    for row in rows:
        canonical = geo_zones._decode_gpkg_geometry(row["geom"], 25830)
        mercator = transform_geometry(transformer.transform, canonical)
        if mercator.is_empty or not mercator.is_valid:
            raise TilePyramidError(f"reproyección inválida de zona {row['zone_id']}")
        projected[row["zone_id"]] = mercator
    return dataset_from_projected(projected)


def validate_zoom(zoom: int) -> None:
    if isinstance(zoom, bool) or not isinstance(zoom, int) or not MIN_ZOOM <= zoom <= MAX_ZOOM:
        raise TilePyramidError(f"zoom fuera de TILES-002: {zoom}; permitido z{MIN_ZOOM}–z{MAX_ZOOM}")


def tile_bounds(zoom: int, x: int, y: int) -> tuple[float, float, float, float]:
    validate_zoom(zoom)
    limit = 1 << zoom
    if not 0 <= x < limit or not 0 <= y < limit:
        raise TilePyramidError(f"coordenada XYZ fuera de z{zoom}: {x}/{y}")
    span = WEB_MERCATOR_WORLD / limit
    left = -WEB_MERCATOR_HALF_WORLD + x * span
    right = left + span
    top = WEB_MERCATOR_HALF_WORLD - y * span
    bottom = top - span
    return left, bottom, right, top


def mercator_to_global_pixel(zoom: int, mercator_x: float, mercator_y: float) -> tuple[float, float]:
    validate_zoom(zoom)
    scale = TILE_SIZE * (1 << zoom)
    pixel_x = (mercator_x + WEB_MERCATOR_HALF_WORLD) / WEB_MERCATOR_WORLD * scale
    pixel_y = (WEB_MERCATOR_HALF_WORLD - mercator_y) / WEB_MERCATOR_WORLD * scale
    return pixel_x, pixel_y


def mercator_to_tile(zoom: int, mercator_x: float, mercator_y: float) -> tuple[int, int]:
    pixel_x, pixel_y = mercator_to_global_pixel(zoom, mercator_x, mercator_y)
    limit = 1 << zoom
    return (
        min(limit - 1, max(0, math.floor(pixel_x / TILE_SIZE))),
        min(limit - 1, max(0, math.floor(pixel_y / TILE_SIZE))),
    )


def enumerate_tiles(dataset: RenderDataset, zoom: int) -> tuple[tuple[int, int], ...]:
    validate_zoom(zoom)
    min_x, min_y, max_x, max_y = dataset.bounds
    min_tile_x, max_tile_y = mercator_to_tile(zoom, min_x, min_y)
    max_tile_x, min_tile_y = mercator_to_tile(zoom, max_x, max_y)
    result: list[tuple[int, int]] = []
    for x in range(min_tile_x, max_tile_x + 1):
        for y in range(min_tile_y, max_tile_y + 1):
            query = box(*tile_bounds(zoom, x, y))
            if len(dataset.polygon_tree.query(query, predicate="intersects")):
                result.append((x, y))
    return tuple(result)


def _pixel_point(
    zoom: int,
    x_origin: int,
    y_origin: int,
    margin: int,
    coordinate: tuple[float, float],
) -> tuple[float, float]:
    global_x, global_y = mercator_to_global_pixel(zoom, coordinate[0], coordinate[1])
    return (
        global_x - x_origin * TILE_SIZE + margin,
        global_y - y_origin * TILE_SIZE + margin,
    )


def _draw_polygon_mask(
    draw: ImageDraw.ImageDraw,
    geometry: Any,
    transform: Any,
) -> None:
    for polygon in _polygon_parts(geometry):
        exterior = [transform(coordinate) for coordinate in polygon.exterior.coords]
        if len(exterior) >= 3:
            draw.polygon(exterior, fill=255)
        for ring in polygon.interiors:
            interior = [transform(coordinate) for coordinate in ring.coords]
            if len(interior) >= 3:
                draw.polygon(interior, fill=0)


def _draw_lines(draw: ImageDraw.ImageDraw, geometry: Any, transform: Any) -> None:
    for line in _line_parts(geometry):
        coordinates = [transform(coordinate) for coordinate in line.coords]
        if len(coordinates) >= 2:
            draw.line(coordinates, fill=15, width=BOUNDARY_WIDTH, joint="curve")


def _global_hatch_mask(
    size: tuple[int, int], global_origin_x: int, global_origin_y: int
) -> Image.Image:
    """Crea bandas x+y constantes, alineadas en la rejilla global XYZ."""
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    origin_sum = global_origin_x + global_origin_y
    first = -height - ((-height + origin_sum) % HATCH_SPACING)
    for diagonal in range(first, width + height + HATCH_SPACING, HATCH_SPACING):
        draw.line(
            ((diagonal, 0), (diagonal - height, height)),
            fill=255,
            width=HATCH_WIDTH,
        )
    return mask


def render_window_indices(
    dataset: RenderDataset,
    zoom: int,
    x: int,
    y: int,
    *,
    width_tiles: int = 1,
    height_tiles: int = 1,
) -> tuple[int, int, bytes]:
    validate_zoom(zoom)
    limit = 1 << zoom
    if width_tiles < 1 or height_tiles < 1 or x < 0 or y < 0 or x + width_tiles > limit or y + height_tiles > limit:
        raise TilePyramidError("ventana XYZ inválida")
    width = width_tiles * TILE_SIZE
    height = height_tiles * TILE_SIZE
    raster = Image.new("L", (width + 2 * OVERSCAN, height + 2 * OVERSCAN), 0)

    left, bottom, _, top = tile_bounds(zoom, x, y)
    _, bottom_last, right, _ = tile_bounds(
        zoom, x + width_tiles - 1, y + height_tiles - 1
    )
    pixel_span = WEB_MERCATOR_WORLD / ((1 << zoom) * TILE_SIZE)
    clip_box = box(
        left - OVERSCAN * pixel_span,
        bottom_last - OVERSCAN * pixel_span,
        right + OVERSCAN * pixel_span,
        top + OVERSCAN * pixel_span,
    )
    transform = lambda coordinate: _pixel_point(zoom, x, y, OVERSCAN, coordinate)
    hatch = _global_hatch_mask(
        raster.size,
        x * TILE_SIZE - OVERSCAN,
        y * TILE_SIZE - OVERSCAN,
    )

    queried_polygons = sorted(int(value) for value in dataset.polygon_tree.query(clip_box, predicate="intersects"))
    for zone_index in range(1, 8):
        selected = [value for value in queried_polygons if dataset.polygons[value].zone_index == zone_index]
        if not selected:
            continue
        mask = Image.new("L", raster.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        for value in selected:
            clipped = dataset.polygon_geometries[value].intersection(clip_box)
            _draw_polygon_mask(mask_draw, clipped, transform)
        raster.paste(zone_index, mask=mask)
        raster.paste(zone_index + 7, mask=ImageChops.multiply(mask, hatch))

    boundary_draw = ImageDraw.Draw(raster)
    for value in sorted(int(item) for item in dataset.boundary_tree.query(clip_box, predicate="intersects")):
        clipped = dataset.boundaries[value].intersection(clip_box)
        _draw_lines(boundary_draw, clipped, transform)

    cropped = raster.crop((OVERSCAN, OVERSCAN, OVERSCAN + width, OVERSCAN + height))
    return width, height, cropped.tobytes()


def render_tile_indices(dataset: RenderDataset, zoom: int, x: int, y: int) -> bytes:
    width, height, indices = render_window_indices(dataset, zoom, x, y)
    if (width, height) != (TILE_SIZE, TILE_SIZE):  # pragma: no cover
        raise TilePyramidError("render de tesela con dimensiones inesperadas")
    return indices


def _rgba_image_from_indices(indices: bytes) -> Image.Image:
    rgba = bytearray()
    for index in indices:
        red, green, blue = tile_template.MARKER_PALETTE[index]
        rgba.extend((red, green, blue, tile_template.ALPHA_TABLE[index]))
    return Image.frombytes("RGBA", (TILE_SIZE, TILE_SIZE), bytes(rgba))


def _overview(
    output: Path,
    zoom: int,
    tiles: tuple[tuple[int, int], ...],
) -> tuple[str, bytes, dict[str, Any]]:
    min_x = min(x for x, _ in tiles)
    max_x = max(x for x, _ in tiles)
    min_y = min(y for _, y in tiles)
    max_y = max(y for _, y in tiles)
    columns = max_x - min_x + 1
    rows = max_y - min_y + 1
    scale = max(1, min(TILE_SIZE, CONTROL_MAX_DIMENSION // max(columns + 2, rows + 2)))
    canvas = Image.new("RGBA", ((columns + 2) * scale, (rows + 2) * scale), (0, 0, 0, 0))
    for x, y in tiles:
        content = (output / str(zoom) / str(x) / f"{y}.png").read_bytes()
        with Image.open(io.BytesIO(content)) as tile:
            tile.load()
            reduced = tile.convert("RGBA").resize((scale, scale), Image.Resampling.NEAREST)
        canvas.alpha_composite(reduced, ((x - min_x + 1) * scale, (y - min_y + 1) * scale))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=False, compress_level=9)
    name = f"controls/z{zoom}-overview.png"
    return name, buffer.getvalue(), {
        "dimensions_pixels": list(canvas.size),
        "source_tile_pixel_size": scale,
        "tile_bounds_xyz": [min_x, min_y, max_x, max_y],
    }


def _extract_tile(indices: bytes, width_tiles: int, column: int, row: int) -> bytes:
    width = width_tiles * TILE_SIZE
    result = bytearray()
    start_x = column * TILE_SIZE
    start_y = row * TILE_SIZE
    for pixel_y in range(start_y, start_y + TILE_SIZE):
        offset = pixel_y * width + start_x
        result.extend(indices[offset : offset + TILE_SIZE])
    return bytes(result)


def _continuity_checks(
    dataset: RenderDataset,
    tiles_by_zoom: dict[int, tuple[tuple[int, int], ...]],
    tile_edges: dict[tuple[int, int, int], tuple[bytes, bytes, bytes, bytes]],
    output: Path,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
        available = set(tiles_by_zoom[zoom])
        checks_before_zoom = len(checks)
        for direction, delta, window in (
            ("east", (1, 0), (2, 1)),
            ("south", (0, 1), (1, 2)),
        ):
            candidates: list[tuple[int, int, int]] = []
            for x, y in sorted(available):
                neighbor = (x + delta[0], y + delta[1])
                if neighbor not in available:
                    continue
                first = tile_edges[(zoom, x, y)]
                second = tile_edges[(zoom, *neighbor)]
                if direction == "east":
                    score = sum(left != 0 or right != 0 for left, right in zip(first[3], second[2]))
                else:
                    score = sum(top != 0 or bottom != 0 for top, bottom in zip(first[1], second[0]))
                candidates.append((score, x, y))
            if not candidates:
                unavailable.append({"direction": direction, "reason": "no adjacent covered pair", "zoom": zoom})
                continue
            score, x, y = max(candidates)
            width_tiles, height_tiles = window
            width, _, combined = render_window_indices(
                dataset, zoom, x, y, width_tiles=width_tiles, height_tiles=height_tiles
            )
            for row in range(height_tiles):
                for column in range(width_tiles):
                    observed = _extract_tile(combined, width_tiles, column, row)
                    path = output / str(zoom) / str(x + column) / f"{y + row}.png"
                    expected = tile_template.decode_indexed_png(path.read_bytes()).indices
                    if observed != expected:
                        raise TilePyramidError(
                            f"discontinuidad byte a byte z{zoom} {x}/{y} {direction}"
                        )
            checks.append({
                "direction": direction,
                "nontransparent_edge_score": score,
                "origin_xyz": [x, y],
                "zoom": zoom,
            })
        if len(checks) == checks_before_zoom:
            raise TilePyramidError(f"z{zoom} no tiene ninguna pareja adyacente cubierta")
    return {
        "method": "individual tiles equal the corresponding crops of a shared 2-tile render",
        "pairs_checked": len(checks),
        "checks": checks,
        "unavailable_directions": unavailable,
    }


def _seam_detail(
    output: Path,
    continuity: dict[str, Any],
) -> tuple[str, bytes, dict[str, Any]]:
    zoom = 14
    east = next(item for item in continuity["checks"] if item["zoom"] == zoom and item["direction"] == "east")
    x, y = east["origin_xyz"]
    canvas = Image.new("RGBA", (TILE_SIZE * 2, TILE_SIZE), (0, 0, 0, 0))
    for column in range(2):
        path = output / str(zoom) / str(x + column) / f"{y}.png"
        indices = tile_template.decode_indexed_png(path.read_bytes()).indices
        image = _rgba_image_from_indices(indices)
        canvas.alpha_composite(image, (column * TILE_SIZE, 0))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=False, compress_level=9)
    return "controls/z14-seam-detail.png", buffer.getvalue(), {
        "dimensions_pixels": [512, 256],
        "origin_xyz": [x, y],
        "direction": "east",
    }


def _visual_checks(
    output: Path,
    tiles_by_zoom: dict[int, tuple[tuple[int, int], ...]],
    indices_observed: set[int],
) -> dict[str, Any]:
    corner_pixels = 0
    white_pixels = 0
    samples: dict[str, Any] = {}
    for zoom, tiles in tiles_by_zoom.items():
        chosen = (tiles[0], tiles[len(tiles) // 2], tiles[-1])
        decoded_samples = []
        for x, y in chosen:
            path = output / str(zoom) / str(x) / f"{y}.png"
            content = path.read_bytes()
            tile_template.validate_contract(content)
            decoded = tile_template.decode_indexed_png(content)
            if decoded.palette != tile_template.MARKER_PALETTE:
                raise TilePyramidError(f"PLTE no congelado en muestra z{zoom}/{x}/{y}")
            if decoded.alpha != tile_template.ALPHA_TABLE:
                raise TilePyramidError(f"tRNS no congelado en muestra z{zoom}/{x}/{y}")
            indices = decoded.indices
            corners = (indices[0], indices[TILE_SIZE - 1], indices[-TILE_SIZE], indices[-1])
            corner_pixels += len(corners)
            decoded_samples.append({"xyz": [x, y], "indices_used": sorted(set(indices)), "corner_indices": list(corners)})
            white_pixels += sum(
                tile_template.MARKER_PALETTE[index] == (255, 255, 255)
                and tile_template.ALPHA_TABLE[index] != 0
                for index in indices
            )
        samples[str(zoom)] = decoded_samples
    if white_pixels:
        raise TilePyramidError("se detectaron píxeles blancos visibles")
    missing = set(range(1, 16)) - indices_observed
    if missing:
        raise TilePyramidError(f"la muestra multizoom no usa índices esperados: {sorted(missing)}")
    return {
        "automatic_samples_per_zoom": 3,
        "corner_pixels_checked": corner_pixels,
        "exterior_alpha": 0,
        "visible_white_pixels": white_pixels,
        "indices_observed": sorted(indices_observed),
        "samples": samples,
    }


def _boundary_pixel_check(
    output: Path,
    zoom: int,
    coordinate: tuple[float, float],
) -> dict[str, Any]:
    x, y = mercator_to_tile(zoom, *coordinate)
    global_x, global_y = mercator_to_global_pixel(zoom, *coordinate)
    for candidate_x in range(max(0, x - 1), min((1 << zoom) - 1, x + 1) + 1):
        for candidate_y in range(max(0, y - 1), min((1 << zoom) - 1, y + 1) + 1):
            path = output / str(zoom) / str(candidate_x) / f"{candidate_y}.png"
            if not path.is_file():
                continue
            indices = tile_template.decode_indexed_png(path.read_bytes()).indices
            local_x = math.floor(global_x - candidate_x * TILE_SIZE)
            local_y = math.floor(global_y - candidate_y * TILE_SIZE)
            for radius_y in range(max(0, local_y - 3), min(TILE_SIZE - 1, local_y + 3) + 1):
                for radius_x in range(max(0, local_x - 3), min(TILE_SIZE - 1, local_x + 3) + 1):
                    if indices[radius_y * TILE_SIZE + radius_x] == 15:
                        return {
                            "mercator": [coordinate[0], coordinate[1]],
                            "pixel_xyz": [radius_x, radius_y],
                            "tile_xyz": [zoom, candidate_x, candidate_y],
                        }
    raise TilePyramidError(f"no se rasterizó el límite cerca de {coordinate} en z{zoom}")


def _geographic_checks(
    dataset: RenderDataset,
    output: Path,
    tiles_by_zoom: dict[int, tuple[tuple[int, int], ...]],
) -> dict[str, Any]:
    union = unary_union(list(dataset.zone_geometries.values()))
    external = union.boundary
    external_lines = list(_line_parts(external))
    coast_coordinate = max(
        (coordinate for line in external_lines for coordinate in line.coords),
        key=lambda coordinate: (coordinate[0], -coordinate[1]),
    )
    coast = _boundary_pixel_check(output, MAX_ZOOM, coast_coordinate)

    internal: list[dict[str, Any]] = []
    for left_id in ZONE_IDS:
        for right_id in ZONE_IDS:
            if right_id <= left_id:
                continue
            shared = dataset.zone_geometries[left_id].boundary.intersection(
                dataset.zone_geometries[right_id].boundary
            )
            if shared.is_empty or shared.length <= 0:
                continue
            point = shared.interpolate(0.5, normalized=True)
            check = _boundary_pixel_check(output, MAX_ZOOM, (point.x, point.y))
            internal.append({"zone_ids": [left_id, right_id], "shared_length_m": shared.length} | check)
    if not internal:
        raise TilePyramidError("no se localizaron límites internos para comprobar")

    min_x, min_y, max_x, max_y = dataset.bounds
    north_tile = mercator_to_tile(MAX_ZOOM, (min_x + max_x) / 2, max_y)
    south_tile = mercator_to_tile(MAX_ZOOM, (min_x + max_x) / 2, min_y)
    if north_tile[1] >= south_tile[1]:
        raise TilePyramidError("Y XYZ está invertida: el norte no tiene Y menor")

    available = set(tiles_by_zoom[MAX_ZOOM])
    min_tile_x = min(x for x, _ in available)
    min_tile_y = min(y for _, y in available)
    exterior_candidate = None
    for distance in range(1, 5):
        candidate = (min_tile_x - distance, min_tile_y)
        if candidate not in available and candidate[0] >= 0:
            exterior_candidate = candidate
            break
    if exterior_candidate is None:
        raise TilePyramidError("no se pudo seleccionar una tesela exterior")
    exterior_indices = render_tile_indices(dataset, MAX_ZOOM, *exterior_candidate)
    if set(exterior_indices) != {0}:
        raise TilePyramidError("el exterior de cobertura no es totalmente transparente")
    return {
        "coast_east_extreme": coast,
        "internal_boundaries": internal,
        "internal_boundaries_checked": len(internal),
        "orientation_xyz": {
            "north_y": north_tile[1],
            "south_y": south_tile[1],
            "passes": True,
        },
        "transparent_exterior_xyz": [MAX_ZOOM, *exterior_candidate],
    }


def _render_report(manifest: dict[str, Any]) -> bytes:
    counts = manifest["pyramid"]["by_zoom"]
    count_lines = [
        f"| {zoom} | {counts[str(zoom)]['tiles']} | {counts[str(zoom)]['bytes']} |"
        for zoom in range(MIN_ZOOM, MAX_ZOOM + 1)
    ]
    lines = [
        "# TILES-002 — Pirámide XYZ estática",
        "",
        f"**Formato:** `{FORMAT_VERSION}`  ",
        f"**Geometría:** `{GEOMETRY_VERSION}`  ",
        "**CRS canónico:** `EPSG:25830` (sin modificar)  ",
        "**CRS de render:** `EPSG:3857` (solo en memoria)",
        "",
        "## Resultado",
        "",
        "| Zoom | Teselas | Bytes PNG |",
        "|---:|---:|---:|",
        *count_lines,
        "",
        f"Teselas con cobertura: **{manifest['pyramid']['tile_assets']}**. Tesela transparente compartida: **1**. Assets totales del entregable: **{manifest['assets']['total']}**, por debajo del límite de {MAX_ASSETS}. Los PNG de despliegue ocupan **{manifest['pyramid']['tile_bytes'] + manifest['pyramid']['transparent']['size_bytes']} bytes**; el total exacto del entregable se registra en `manifest.json`.",
        "",
        "## Algoritmo XYZ y rasterizado",
        "",
        "La capa `zones` se abre en modo solo lectura y se exige `MULTIPOLYGON EPSG:25830`. Sus siete geometrías se reproyectan a EPSG:3857 exclusivamente en memoria. Para cada z6–z14 se calcula el rango candidato desde la envolvente y se conserva una tesela solo si un polígono exacto la intersecta. La ruta es `{z}/{x}/{y}.png`; Y aumenta hacia el sur (XYZ, nunca TMS).",
        "",
        "Los rellenos se dibujan con índices 1–7 y una banda diagonal global de 2 px cada 12 px usa 8–14. Todos los anillos originales se trazan después con índice 15, negro, ancho fijo de 2 px y bordes duros. El patrón se alinea en coordenadas de píxel globales para no crear discontinuidades entre teselas. `tools/tile_template.py` codifica cada matriz con el contrato binario congelado y vuelve a decodificar muestras.",
        "",
        "## Estrategia anti-seams",
        "",
        f"Todas las coordenadas se convierten a una única rejilla global de píxeles Web Mercator. Cada ventana se rasteriza con 8 px de overscan y se recorta al centro exacto; el recorte geométrico queda fuera de la tesela publicada. Se compararon teselas individuales contra los recortes de un render compartido de dos teselas en cada dirección adyacente existente. Las {manifest['verification']['continuity']['pairs_checked']} parejas fueron idénticas byte a byte; z6 no tiene pareja vertical cubierta y se registra sin inventar un asset fuera de cobertura.",
        "",
        "## Verificación visual y automática",
        "",
        "Los mosaicos `controls/z6-overview.png`, `z10-overview.png` y `z14-overview.png` se montan desde las teselas XYZ reales, con Y creciente hacia abajo y un marco transparente. `controls/z14-seam-detail.png` conserva dos teselas contiguas a resolución nativa. Se revisan costa, límites internos, trama, cuatro esquinas, continuidad, orientación norte-sur, transparencia exterior y ausencia de blanco visible. Tres muestras de cada zoom se decodifican con el validador TILES-001; los índices observados son 0–15 y los alpha siguen siendo 0/77/179.",
        "",
        "## Reproducibilidad",
        "",
        "```sh",
        ".venv-geo/bin/python tools/tile_pyramid.py build",
        ".venv-geo/bin/python tools/tile_pyramid.py validate",
        ".venv-geo/bin/python -m unittest tests.test_tile_pyramid -v",
        ".venv-geo/bin/python -m unittest discover -s tests -v",
        "```",
        "",
        "`build` y `validate` ejecutan primero las cinco barreras GEO-001→TILES-001. `validate` regenera la pirámide completa en un directorio temporal y exige el mismo conjunto de rutas y bytes. `tiles.sha256` fija cada ruta de tesela y su SHA-256; su propio hash actúa como huella compacta de la pirámide.",
        "",
        "## Limitaciones",
        "",
        "El borde y la trama no usan antialias y su grosor cartográfico varía con el zoom. Los RGB 1–14 son marcadores reemplazables, no el estilo final. No se sirve HTTP ni se genera TMS/MBTiles.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _stable_manifest_bytes(manifest: dict[str, Any], bytes_without_manifest: int) -> bytes:
    current = 0
    for _ in range(20):
        manifest["assets"]["bytes_total"] = bytes_without_manifest + current
        content = json_bytes(manifest)
        if len(content) == current:
            return content
        current = len(content)
    raise TilePyramidError("el tamaño autorreferente del manifiesto no converge")


def generate(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    dataset = load_projected_dataset()
    transparent = tile_template.encode_indexed_png(bytes(TILE_SIZE * TILE_SIZE))
    (output / TRANSPARENT_NAME).write_bytes(transparent)

    tile_edges: dict[tuple[int, int, int], tuple[bytes, bytes, bytes, bytes]] = {}
    indices_observed: set[int] = set()
    tiles_by_zoom: dict[int, tuple[tuple[int, int], ...]] = {}
    inventory_lines: list[str] = []
    by_zoom: dict[str, Any] = {}
    tile_bytes_total = 0
    tile_count = 0
    for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
        tiles = enumerate_tiles(dataset, zoom)
        if not tiles:
            raise TilePyramidError(f"z{zoom} no enumera ninguna tesela")
        tiles_by_zoom[zoom] = tiles
        zoom_lines: list[str] = []
        zoom_bytes = 0
        for x, y in tiles:
            indices = render_tile_indices(dataset, zoom, x, y)
            content = tile_template.encode_indexed_png(indices)
            tile_template.validate_contract(content)
            relative = f"{zoom}/{x}/{y}.png"
            path = output / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            indices_observed.update(indices)
            tile_edges[(zoom, x, y)] = (
                indices[:TILE_SIZE],
                indices[-TILE_SIZE:],
                indices[0::TILE_SIZE],
                indices[TILE_SIZE - 1::TILE_SIZE],
            )
            digest = sha256_bytes(content)
            line = f"{digest}  {relative}\n"
            inventory_lines.append(line)
            zoom_lines.append(line)
            zoom_bytes += len(content)
        by_zoom[str(zoom)] = {
            "bounds_xyz": [
                min(x for x, _ in tiles), min(y for _, y in tiles),
                max(x for x, _ in tiles), max(y for _, y in tiles),
            ],
            "bytes": zoom_bytes,
            "inventory_sha256": sha256_bytes("".join(zoom_lines).encode("utf-8")),
            "tiles": len(tiles),
        }
        tile_count += len(tiles)
        tile_bytes_total += zoom_bytes

    if tile_count + 1 >= MAX_ASSETS:
        raise TilePyramidError(f"la pirámide supera el límite de assets: {tile_count + 1}")
    inventory = "".join(inventory_lines).encode("utf-8")
    (output / INVENTORY_NAME).write_bytes(inventory)

    continuity = _continuity_checks(dataset, tiles_by_zoom, tile_edges, output)
    visual = _visual_checks(output, tiles_by_zoom, indices_observed)
    geographic = _geographic_checks(dataset, output, tiles_by_zoom)
    controls: dict[str, Any] = {}
    for zoom in CONTROL_ZOOMS:
        name, content, metadata = _overview(output, zoom, tiles_by_zoom[zoom])
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        controls[name] = metadata | {"sha256": sha256_bytes(content), "size_bytes": len(content)}
    name, content, metadata = _seam_detail(output, continuity)
    (output / name).write_bytes(content)
    controls[name] = metadata | {"sha256": sha256_bytes(content), "size_bytes": len(content)}

    frozen = tile_template.verify_frozen_geometry()
    manifest: dict[str, Any] = {
        "assets": {
            "bytes_total": 0,
            "deployment_templates": tile_count + 1,
            "limit": MAX_ASSETS,
            "passes_limit": True,
            "total": tile_count + 1 + 1 + 1 + 1 + len(controls),
        },
        "controls": controls,
        "format_version": FORMAT_VERSION,
        "geometry_version": GEOMETRY_VERSION,
        "inputs": {
            "crosswalk": {"path": "../crosswalk/crosswalk.csv", "sha256": frozen["crosswalk"]},
            "geo004_manifest": {"path": "../geo-004/manifest.json", "sha256": frozen["geo004_manifest"]},
            "geojson": {"path": "../zones/zones.geojson", "sha256": frozen["geojson"]},
            "master": {"crs": "EPSG:25830", "path": "../zones/zones.gpkg", "sha256": frozen["master"]},
        },
        "pyramid": {
            "by_zoom": by_zoom,
            "crs_render": "EPSG:3857",
            "inventory": {"path": INVENTORY_NAME, "sha256": sha256_bytes(inventory), "size_bytes": len(inventory)},
            "path_template": "{z}/{x}/{y}.png",
            "tile_assets": tile_count,
            "tile_bytes": tile_bytes_total,
            "tile_size": [TILE_SIZE, TILE_SIZE],
            "transparent": {"path": TRANSPARENT_NAME, "sha256": sha256_bytes(transparent), "size_bytes": len(transparent)},
            "xyz_y_axis": "north_to_south_not_inverted",
            "zooms": [MIN_ZOOM, MAX_ZOOM],
        },
        "render": {
            "boundary_index": 15,
            "hatch_indices": list(range(8, 15)),
            "hatch_spacing_pixels": HATCH_SPACING,
            "hatch_width_pixels": HATCH_WIDTH,
            "boundary_width_pixels": BOUNDARY_WIDTH,
            "canonical_crs_unchanged": "EPSG:25830",
            "fill_indices": {str(zone_id): zone_id - 52 for zone_id in ZONE_IDS},
            "overscan_pixels": OVERSCAN,
            "strategy": "global Web Mercator pixel grid; clipped with overscan; central crop",
        },
        "schema_version": 1,
        "software": {
            "geos": shapely.geos_version_string,
            "pillow": Image.__version__ if hasattr(Image, "__version__") else None,
            "proj": pyproj.proj_version_str,
            "pyproj": pyproj.__version__,
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "shapely": shapely.__version__,
        },
        "status": "complete",
        "verification": {
            "continuity": continuity,
            "geographic": geographic,
            "visual": visual,
            "determinism": "validate regenerates and compares every path byte-for-byte",
            "png_contract_samples_per_zoom": 3,
        },
    }
    report = _render_report(manifest)
    (output / REPORT_NAME).write_bytes(report)
    manifest["reports"] = {
        REPORT_NAME: {"sha256": sha256_bytes(report), "size_bytes": len(report)}
    }
    bytes_without_manifest = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    manifest_content = _stable_manifest_bytes(manifest, bytes_without_manifest)
    (output / MANIFEST_NAME).write_bytes(manifest_content)
    return json.loads(manifest_content)


def _file_inventory(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def build(output: Path = DEFAULT_OUTPUT, *, run_prerequisites: bool = True) -> None:
    if run_prerequisites:
        _run_prerequisites()
    if output.exists():
        raise TilePyramidError(f"el destino ya existe; no se sustituye automáticamente: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    staging.rmdir()
    try:
        manifest = generate(staging)
        os.replace(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(f"directorio: {output}")
    print(f"teselas: {manifest['pyramid']['tile_assets']}; assets totales: {manifest['assets']['total']}")
    print(f"bytes totales: {manifest['assets']['bytes_total']}")
    print(f"inventario sha256: {manifest['pyramid']['inventory']['sha256']}")


def validate(output: Path = DEFAULT_OUTPUT, *, run_prerequisites: bool = True) -> None:
    if run_prerequisites:
        _run_prerequisites()
    if not output.is_dir():
        raise TilePyramidError(f"no existe el directorio TILES-002: {output}")
    with tempfile.TemporaryDirectory(prefix="tiles-002-validate-") as temporary:
        expected_root = Path(temporary) / "tiles-002"
        expected_manifest = generate(expected_root)
        observed = _file_inventory(output)
        expected = _file_inventory(expected_root)
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))[:10]
        extra = sorted(set(observed) - set(expected))[:10]
        raise TilePyramidError(f"rutas no reproducibles; faltan={missing}, sobran={extra}")
    for name in sorted(expected):
        if observed[name] != expected[name]:
            raise TilePyramidError(
                f"bytes no reproducibles en {name}: {sha256_bytes(observed[name])} != {sha256_bytes(expected[name])}"
            )
    for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
        metadata = expected_manifest["pyramid"]["by_zoom"][str(zoom)]
        if metadata["tiles"] <= 0:
            raise TilePyramidError(f"conteo vacío en z{zoom}")
    print(f"directorio: {output}")
    print(f"reproducibilidad byte a byte: {len(expected)} archivos conformes")
    print(f"teselas: {expected_manifest['pyramid']['tile_assets']}; assets: {expected_manifest['assets']['total']}/{MAX_ASSETS}")
    print(f"continuidad: {expected_manifest['verification']['continuity']['pairs_checked']} parejas conformes")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("build", "genera la pirámide completa"), ("validate", "regenera y compara todos los bytes")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
        command.add_argument("--skip-prerequisites", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build":
            build(args.output.resolve(), run_prerequisites=not args.skip_prerequisites)
        elif args.command == "validate":
            validate(args.output.resolve(), run_prerequisites=not args.skip_prerequisites)
    except (OSError, TilePyramidError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
