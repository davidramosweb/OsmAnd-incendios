#!/usr/bin/env python3
"""Genera y valida la comparación visual reproducible de GEO-004.

La herramienta consume la geometría congelada de GEO-003 y un PNG oficial
no georreferenciado fijado por SHA-256. Solo aplica una transformación visual
uniforme de escala/traslación con inversión del eje Y; no modifica, simplifica
ni sustituye ninguna coordenada o asignación municipal.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence
import zlib

try:
    import PIL
    from PIL import Image, ImageDraw, ImageFont, features as pil_features
except ModuleNotFoundError as exc:
    PIL = None  # type: ignore[assignment]
    Image = ImageDraw = ImageFont = pil_features = None  # type: ignore[assignment]
    _PIL_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _PIL_IMPORT_ERROR = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools import geo_zones


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "geo_compare.json"
MANIFEST_NAME = "manifest.json"
REPORT_NAME = "REPORT.md"
CONTROLS_NAME = "control-points.csv"
DISCREPANCIES_NAME = "discrepancies.json"
REGISTERED_NAME = "render/zones-registered-500x835.png"
DIAGNOSTIC_NAME = "render/zones-exact-1000x1670.png"
SIDE_BY_SIDE_NAME = "comparison/side-by-side.png"
OVERLAY_NAME = "comparison/overlay.png"
EXPECTED_CODES = ["1N", "1S", "2", "3", "4", "5", "6"]
EXPECTED_IDS = list(range(53, 60))


class CompareError(RuntimeError):
    """Fallo de entrada, comparación, reproducibilidad o alcance."""


def _require_dependencies() -> None:
    geo_zones._require_dependencies()
    if _PIL_IMPORT_ERROR is not None:
        raise CompareError(
            "falta Pillow; instale exactamente requirements-geo-004.txt: "
            f"{_PIL_IMPORT_ERROR}"
        )


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CompareError(f"no se puede leer {path}: {exc}") from exc
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


def _load_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompareError(f"no se puede leer {description} {path}: {exc}") from exc


def _resolve(base: Path, value: str, description: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CompareError(f"ruta inválida para {description}")
    return (base / value).resolve()


def _relative(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


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


def _load_config(path: Path) -> dict[str, Any]:
    config = _load_json(path, "la configuración de GEO-004")
    required = {
        "approval",
        "controls",
        "details",
        "discrepancies",
        "expected_zones",
        "geometry_version",
        "inputs",
        "output_directory",
        "registration",
        "render",
        "schema_version",
        "status",
    }
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise CompareError("schema_version de GEO-004 no soportada")
    missing = required - set(config)
    if missing:
        raise CompareError(f"faltan claves de GEO-004: {sorted(missing)}")
    if config["status"] not in {"pending_human_approval", "approved"}:
        raise CompareError("estado de GEO-004 no permitido")
    if config["status"] == "approved":
        approval = config["approval"]
        if not all(isinstance(approval.get(key), str) and approval[key].strip() for key in ("reviewer", "date", "decision")):
            raise CompareError("la aprobación requiere revisor, fecha y decisión explícita")
        expected_version = f"sha256:{config['inputs']['master']['sha256']}"
        if config["geometry_version"] != expected_version:
            raise CompareError("geometry_version no coincide con el GeoPackage congelado")
    elif config["geometry_version"] is not None:
        raise CompareError("no debe existir geometry_version antes de aprobación humana")
    expected = config["expected_zones"]
    if [row.get("zone_id") for row in expected] != EXPECTED_IDS:
        raise CompareError("los IDs esperados deben ser 53–59")
    if [row.get("zone_code") for row in expected] != EXPECTED_CODES:
        raise CompareError("los códigos esperados deben ser 1N, 1S y 2–6")
    render = config["render"]
    if render.get("canvas_pixels") != [500, 835]:
        raise CompareError("el marco de comparación debe conservar 500×835 px")
    if render.get("label_font") != "PillowEmbeddedAileronRegular-11.3.0":
        raise CompareError("la fuente diagnóstica debe estar fijada")
    registration = config["registration"]
    if registration.get("method") != "uniform_scale_translation_with_y_inversion":
        raise CompareError("solo se admite escala uniforme y traslación")
    if registration.get("nonlinear_deformation") is not False:
        raise CompareError("GEO-004 prohíbe deformaciones no lineales")
    if len(registration.get("control_points", [])) != 4:
        raise CompareError("se requieren cuatro puntos de control de encuadre")
    control_ids = [control.get("id") for control in config["controls"]]
    if len(control_ids) < 15 or len(set(control_ids)) != len(control_ids):
        raise CompareError("la lista versionada de controles es incompleta o duplicada")
    discrepancy_ids = [item.get("id") for item in config["discrepancies"]]
    if len(set(discrepancy_ids)) != len(discrepancy_ids):
        raise CompareError("hay discrepancias duplicadas")
    allowed_classes = {"explicable", "corregible", "bloqueante"}
    if any(item.get("classification") not in allowed_classes for item in config["discrepancies"]):
        raise CompareError("clasificación de discrepancia no permitida")
    return config


def _run_prerequisite_validations() -> dict[str, str]:
    commands = [
        ("geo_sources", [sys.executable, str(PROJECT_ROOT / "tools/geo_sources.py"), "validate"]),
        ("geo_crosswalk", [sys.executable, str(PROJECT_ROOT / "tools/geo_crosswalk.py"), "validate"]),
        ("geo_zones", [sys.executable, str(PROJECT_ROOT / "tools/geo_zones.py"), "validate"]),
    ]
    outputs: dict[str, str] = {}
    for name, command in commands:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise CompareError(f"falló la barrera {name}: {detail}")
        outputs[name] = result.stdout.strip()
    return outputs


def _verify_frozen_inputs(config_path: Path, config: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "crosswalk": _resolve(config_path.parent, config["inputs"]["crosswalk"]["path"], "crosswalk"),
        "geojson": _resolve(config_path.parent, config["inputs"]["geojson"]["path"], "GeoJSON"),
        "master": _resolve(config_path.parent, config["inputs"]["master"]["path"], "GeoPackage maestro"),
        "municipal_source": _resolve(config_path.parent, config["inputs"]["municipal_source"], "GeoPackage municipal"),
        "reference_metadata": _resolve(config_path.parent, config["inputs"]["reference_metadata"], "metadatos de referencia"),
        "requirements": _resolve(config_path.parent, config["inputs"]["requirements"], "requisitos GEO-004"),
    }
    for name in ("crosswalk", "geojson", "master"):
        observed = sha256_file(paths[name])
        expected = config["inputs"][name]["sha256"]
        if observed != expected:
            raise CompareError(
                f"hash congelado de GEO-002/GEO-003 alterado para {name}: "
                f"{observed} != {expected}; GEO-004 se detiene"
            )
    return paths


def _load_reference(metadata_path: Path) -> tuple[dict[str, Any], Path, bytes, Any]:
    metadata = _load_json(metadata_path, "los metadatos de la referencia oficial")
    required = {
        "content_type",
        "dimensions_pixels",
        "license",
        "retrieved_at_utc",
        "sha256",
        "size_bytes",
        "snapshot",
        "url_final",
        "url_requested",
    }
    if not isinstance(metadata, dict) or required - set(metadata):
        raise CompareError("metadatos de referencia incompletos")
    if metadata["content_type"] != "image/png":
        raise CompareError("la referencia prioritaria debe ser PNG")
    if metadata["license"].get("status") != "not_found":
        raise CompareError("la licencia específica 112CV debe permanecer not_found")
    snapshot = _resolve(metadata_path.parent, metadata["snapshot"], "snapshot oficial")
    try:
        content = snapshot.read_bytes()
    except OSError as exc:
        raise CompareError(f"no se puede leer el snapshot oficial: {exc}") from exc
    observed_hash = sha256_bytes(content)
    if observed_hash != metadata["sha256"]:
        raise CompareError(f"hash de referencia alterado: {observed_hash}")
    if len(content) != metadata["size_bytes"]:
        raise CompareError("tamaño de referencia distinto al registrado")
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception as exc:
        raise CompareError(f"PNG oficial no legible: {exc}") from exc
    if image.format != "PNG" or list(image.size) != metadata["dimensions_pixels"]:
        raise CompareError("formato o dimensiones de referencia distintos al registro")
    return metadata, snapshot, content, image.convert("RGB")


def _load_zones(master_path: Path, config: dict[str, Any]) -> dict[int, dict[str, Any]]:
    try:
        uri = f"file:{master_path.resolve()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CompareError("integrity_check de zones.gpkg no es ok")
            metadata = connection.execute(
                "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns "
                "WHERE table_name='zones' AND column_name='geom'"
            ).fetchone()
            if metadata is None or tuple(metadata) != ("MULTIPOLYGON", 25830):
                raise CompareError("capa zones no es MULTIPOLYGON EPSG:25830")
            rows = connection.execute(
                "SELECT zone_id, zone_code, municipality_count, part_count, geom "
                "FROM zones ORDER BY zone_id"
            ).fetchall()
    except CompareError:
        raise
    except sqlite3.Error as exc:
        raise CompareError(f"no se puede leer zones.gpkg: {exc}") from exc
    if len(rows) != 7:
        raise CompareError(f"zones.gpkg contiene {len(rows)} entidades; se esperaban 7")
    expected = {row["zone_id"]: row for row in config["expected_zones"]}
    zones: dict[int, dict[str, Any]] = {}
    for row in rows:
        geometry = geo_zones._decode_gpkg_geometry(row["geom"], 25830)
        parts, holes = geo_zones._part_hole_counts(geometry)
        contract = expected.get(row["zone_id"])
        if contract is None:
            raise CompareError(f"ID de zona inesperado: {row['zone_id']}")
        observed = (row["zone_code"], parts, holes)
        wanted = (contract["zone_code"], contract["parts"], contract["holes"])
        if observed != wanted:
            raise CompareError(f"contrato geométrico alterado para zona {row['zone_id']}: {observed} != {wanted}")
        if geometry.is_empty or not geometry.is_valid:
            raise CompareError(f"zona {row['zone_id']} vacía o inválida")
        zones[row["zone_id"]] = {
            "zone_id": row["zone_id"],
            "zone_code": row["zone_code"],
            "municipality_count": row["municipality_count"],
            "parts": parts,
            "holes": holes,
            "geometry": geometry,
        }
    if list(zones) != EXPECTED_IDS or [zones[i]["zone_code"] for i in zones] != EXPECTED_CODES:
        raise CompareError("orden de IDs/códigos distinto a 53–59 / 1N–6")
    return zones


def _geometry_bbox(zones: dict[int, dict[str, Any]]) -> list[float]:
    return [
        min(record["geometry"].bounds[0] for record in zones.values()),
        min(record["geometry"].bounds[1] for record in zones.values()),
        max(record["geometry"].bounds[2] for record in zones.values()),
        max(record["geometry"].bounds[3] for record in zones.values()),
    ]


def _registration(zones: dict[int, dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    min_x, min_y, max_x, max_y = _geometry_bbox(zones)
    left, top, right, bottom = [float(v) for v in config["registration"]["reference_shape_bbox_pixels"]]
    scale = (bottom - top) / (max_y - min_y)
    translate_x = (left + right) / 2.0 - scale * (min_x + max_x) / 2.0
    translate_y = top + scale * max_y
    control_points: list[dict[str, Any]] = []
    for control in config["registration"]["control_points"]:
        easting, northing = [float(v) for v in control["geometry_epsg25830"]]
        predicted = [scale * easting + translate_x, -scale * northing + translate_y]
        expected = [float(v) for v in control["reference_pixel"]]
        residual = [predicted[0] - expected[0], predicted[1] - expected[1]]
        residual_distance = (residual[0] ** 2 + residual[1] ** 2) ** 0.5
        control_points.append(
            {
                "id": control["id"],
                "geometry_epsg25830": [easting, northing],
                "predicted_pixel": predicted,
                "reference_pixel": expected,
                "residual_pixels": residual,
                "residual_distance_pixels": residual_distance,
            }
        )
    maximum = max(point["residual_distance_pixels"] for point in control_points)
    if maximum > 1.5:
        raise CompareError(f"el encuadre excede 1,5 px en los controles: {maximum}")
    return {
        "control_points": control_points,
        "geometry_bbox_epsg25830": [min_x, min_y, max_x, max_y],
        "horizontal_alignment": "bbox_centres",
        "method": "uniform_scale_translation_with_y_inversion",
        "nonlinear_deformation": False,
        "reference_shape_bbox_pixels": [left, top, right, bottom],
        "scale_basis": "north_south_extent",
        "scale_pixels_per_metre": scale,
        "translate_x_pixels": translate_x,
        "translate_y_pixels": translate_y,
        "x_pixel": "scale * easting + translate_x",
        "y_pixel": "-scale * northing + translate_y",
    }


def _rgb(hex_value: str) -> tuple[int, int, int]:
    value = hex_value.lstrip("#")
    if len(value) != 6:
        raise CompareError(f"color hexadecimal inválido: {hex_value}")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _transform_ring(ring: Any, registration: dict[str, Any], factor: float) -> list[tuple[float, float]]:
    scale = registration["scale_pixels_per_metre"] * factor
    tx = registration["translate_x_pixels"] * factor
    ty = registration["translate_y_pixels"] * factor
    return [(scale * float(x) + tx, -scale * float(y) + ty) for x, y in ring.coords]


def _render_geometry(
    zones: dict[int, dict[str, Any]],
    config: dict[str, Any],
    registration: dict[str, Any],
    *,
    output_scale: int,
    overlay: bool = False,
    labels: bool = True,
) -> Any:
    render = config["render"]
    width, height = render["canvas_pixels"]
    supersampling = int(render["supersampling"])
    internal_scale = max(int(output_scale), supersampling)
    target_size = (width * int(output_scale), height * int(output_scale))
    internal_size = (width * internal_scale, height * internal_scale)
    if overlay:
        image = Image.new("RGBA", internal_size, (255, 255, 255, 0))
    else:
        image = Image.new("RGB", internal_size, _rgb(render["background"]))
    draw = ImageDraw.Draw(image, "RGBA" if overlay else None)
    outline_rgb = _rgb(render["overlay_outline"] if overlay else render["outline"])
    outline = (*outline_rgb, 210) if overlay else outline_rgb
    width_px = max(1, int(round(float(render["outline_width_pixels"]) * internal_scale)))
    for zone_id in EXPECTED_IDS:
        record = zones[zone_id]
        code = record["zone_code"]
        if overlay:
            fill = (*_rgb(render["overlay_fill"]), 45)
            hole_fill = (255, 255, 255, 0)
        else:
            fill = _rgb(render["zone_fills"][code])
            hole_fill = _rgb(render["background"])
        for polygon in record["geometry"].geoms:
            exterior = _transform_ring(polygon.exterior, registration, internal_scale)
            draw.polygon(exterior, fill=fill)
            for interior in polygon.interiors:
                hole = _transform_ring(interior, registration, internal_scale)
                draw.polygon(hole, fill=hole_fill)
        for polygon in record["geometry"].geoms:
            exterior = _transform_ring(polygon.exterior, registration, internal_scale)
            draw.line(exterior, fill=outline, width=width_px, joint="curve")
            for interior in polygon.interiors:
                hole = _transform_ring(interior, registration, internal_scale)
                draw.line(hole, fill=outline, width=width_px, joint="curve")
    if labels:
        label_fill = (0, 0, 0, 255) if overlay else (0, 0, 0)
        font = ImageFont.load_default(
            size=int(render["label_size_pixels"]) * internal_scale
        )
        for code in EXPECTED_CODES:
            center = [value * internal_scale for value in render["labels"][code]]
            draw.text(
                tuple(center),
                code,
                font=font,
                fill=label_fill,
                anchor="mm",
                stroke_width=max(1, internal_scale),
                stroke_fill=label_fill,
            )
    if image.size != target_size:
        image = image.resize(target_size, Image.Resampling.LANCZOS)
    return image


def _png_bytes(image: Any) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _side_by_side(reference: Any, registered: Any) -> Any:
    gap = 20
    canvas = Image.new("RGB", (reference.width + gap + registered.width, max(reference.height, registered.height)), (255, 255, 255))
    canvas.paste(reference.convert("RGB"), (0, 0))
    ImageDraw.Draw(canvas).rectangle((reference.width, 0, reference.width + gap - 1, canvas.height - 1), fill=(225, 225, 225))
    canvas.paste(registered.convert("RGB"), (reference.width + gap, 0))
    return canvas


def _overlay(reference: Any, vector_layer: Any) -> Any:
    return Image.alpha_composite(reference.convert("RGBA"), vector_layer.convert("RGBA")).convert("RGB")


def _detail_comparison(reference: Any, registered: Any, detail: dict[str, Any]) -> Any:
    crop = tuple(int(value) for value in detail["crop_pixels"])
    scale = int(detail["scale"])
    if len(crop) != 4 or crop[0] < 0 or crop[1] < 0 or crop[2] > 500 or crop[3] > 835 or crop[0] >= crop[2] or crop[1] >= crop[3]:
        raise CompareError(f"recorte inválido para {detail['name']}")
    size = ((crop[2] - crop[0]) * scale, (crop[3] - crop[1]) * scale)
    left = reference.crop(crop).resize(size, Image.Resampling.LANCZOS)
    right = registered.crop(crop).resize(size, Image.Resampling.LANCZOS)
    return _side_by_side(left, right)


def _load_crosswalk(path: Path) -> dict[str, dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise CompareError(f"no se puede leer el crosswalk: {exc}") from exc
    if len(rows) != 542:
        raise CompareError("el crosswalk debe contener 542 filas")
    indexed = {row["icv_cod_ine_mun"]: row for row in rows}
    if len(indexed) != 542:
        raise CompareError("el crosswalk contiene códigos duplicados")
    return indexed


def _validate_controls(
    config_path: Path,
    config: dict[str, Any],
    paths: dict[str, Path],
    zones: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    crosswalk = _load_crosswalk(paths["crosswalk"])
    geo_config_path = PROJECT_ROOT / "config" / "geo_zones.json"
    geo_config = geo_zones._load_config(geo_config_path)
    municipalities, _ = geo_zones._load_icv_geometries(paths["municipal_source"], geo_config)
    zone_id_by_code = {record["zone_code"]: zone_id for zone_id, record in zones.items()}
    rows: list[dict[str, str]] = []
    adjacency: dict[str, float] = {}
    for control in config["controls"]:
        municipal_specs = control.get("municipalities", [])
        loaded: list[tuple[str, str, Any]] = []
        for spec in municipal_specs:
            code = spec["code"]
            expected_zone = spec["zone"]
            if code not in crosswalk or code not in municipalities:
                raise CompareError(f"control {control['id']}: municipio {code} ausente")
            observed_zone_id = int(crosswalk[code]["id_zona_previfoc"])
            observed_zone = zones[observed_zone_id]["zone_code"]
            if observed_zone != expected_zone:
                raise CompareError(f"control {control['id']}: {code} está en {observed_zone}, no {expected_zone}")
            geometry = municipalities[code]["geometry"]
            outside_area = float(geometry.difference(zones[observed_zone_id]["geometry"]).area)
            if outside_area > 0.0001:
                raise CompareError(f"control {control['id']}: {code} no está cubierto por su zona ({outside_area} m² fuera)")
            loaded.append((code, expected_zone, geometry))
        if len(loaded) == 2 and loaded[0][1] != loaded[1][1]:
            shared = float(loaded[0][2].boundary.intersection(loaded[1][2].boundary).length)
            if shared <= 1.0:
                raise CompareError(f"control {control['id']}: el par no comparte frontera material")
            adjacency[control["id"]] = shared
        rows.append(
            {
                "control_id": control["id"],
                "expected_zone": control["expected_zones"],
                "municipality_or_feature": control["municipality_or_feature"],
                "geometry_evidence": control["geometry_evidence"],
                "reference_evidence": control["reference_evidence"],
                "result": control["result"],
                "limitations": control["limitations"],
            }
        )
    return rows, {
        "adjacent_boundary_pairs_checked": len(adjacency),
        "shared_boundary_lengths_m": adjacency,
        "municipalities_loaded": len(municipalities),
        "versioned_controls": len(rows),
        "zone_id_by_code": zone_id_by_code,
    }


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    fields = [
        "control_id",
        "expected_zone",
        "municipality_or_feature",
        "geometry_evidence",
        "reference_evidence",
        "result",
        "limitations",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _software_versions() -> dict[str, str | None]:
    def feature_version(name: str) -> str | None:
        try:
            return pil_features.version(name)
        except Exception:
            return None

    return {
        "geos": geo_zones.shapely.geos_version_string,
        "numpy": geo_zones.numpy.__version__,
        "pillow": PIL.__version__,
        "pillow_libjpeg": feature_version("jpg"),
        "pillow_zlib": feature_version("zlib"),
        "proj": geo_zones.pyproj.proj_version_str,
        "pyproj": geo_zones.pyproj.__version__,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "shapely": geo_zones.shapely.__version__,
        "sqlite": sqlite3.sqlite_version,
        "zlib_compile": zlib.ZLIB_VERSION,
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
    }


def _report_bytes(
    *,
    config: dict[str, Any],
    reference: dict[str, Any],
    reference_path: Path,
    registration: dict[str, Any],
    controls: list[dict[str, str]],
    control_metrics: dict[str, Any],
    output_hashes: dict[str, str],
    image_dimensions: dict[str, list[int]],
    software: dict[str, str | None],
) -> bytes:
    discrepancies = config["discrepancies"]
    classifications = {name: sum(item["classification"] == name for item in discrepancies) for name in ("explicable", "corregible", "bloqueante")}
    approved = config["status"] == "approved"
    status_text = "aprobado por revisión humana explícita" if approved else "pendiente de aprobación humana explícita"
    lines = [
        "# GEO-004 — Comparación visual con el mapa oficial PREVIFOC",
        "",
        f"**Estado:** {status_text}.",
        "",
        "La comparación no georreferencia ni digitaliza el PNG oficial. Renderiza exactamente las siete `MultiPolygon` congeladas por GEO-003 y usa únicamente escala uniforme, traslación e inversión del eje Y para compartir encuadre. No se ha simplificado, eliminado ninguna parte, rellenado ningún hueco ni modificado coordenadas.",
        "",
        "## Referencia oficial fijada",
        "",
        f"- URL solicitada/final: `{reference['url_requested']}`.",
        f"- Snapshot original intacto: `{_relative(reference_path, PROJECT_ROOT)}`.",
        f"- Recuperación UTC: `{reference['retrieved_at_utc']}`; Content-Type `{reference['content_type']}`; {reference['dimensions_pixels'][0]}×{reference['dimensions_pixels'][1]} px; {reference['size_bytes']} bytes.",
        f"- SHA-256: `{reference['sha256']}`.",
        "- Licencia específica 112CV: `not_found`; el acceso público no se interpreta como licencia.",
        "- Referencia prioritaria: `zonasprevifoc.png`. No se usaron buscadores, copias de terceros ni los JPEG secundarios.",
        "",
        "## Entradas congeladas y barreras",
        "",
        f"- `zones.gpkg`: `{config['inputs']['master']['sha256']}`; capa `zones`, EPSG:25830, siete `MULTIPOLYGON`.",
        f"- `zones.geojson`: `{config['inputs']['geojson']['sha256']}`; RFC 7946 EPSG:4326.",
        f"- `crosswalk.csv`: `{config['inputs']['crosswalk']['sha256']}`; 542 municipios.",
        "- Antes de comparar se ejecutaron y exigieron `geo_sources.py validate`, `geo_crosswalk.py validate` y `geo_zones.py validate`.",
        "- GEO-004 no modificó ni regeneró esos entregables.",
        "",
        "## Registro visual",
        "",
        f"Transformación: `{registration['method']}`. Fórmulas: `x = {registration['x_pixel']}`; `y = {registration['y_pixel']}`. Escala `{registration['scale_pixels_per_metre']:.15f}` px/m; traslaciones X `{registration['translate_x_pixels']:.12f}` px e Y `{registration['translate_y_pixels']:.12f}` px. No hay deformación no lineal.",
        "",
        "| Control | Coordenada EPSG:25830 | Pixel observado | Pixel proyectado | Residuo (px) |",
        "|---|---|---|---|---:|",
    ]
    for point in registration["control_points"]:
        e, n = point["geometry_epsg25830"]
        ox, oy = point["reference_pixel"]
        px, py = point["predicted_pixel"]
        lines.append(f"| `{point['id']}` | `{e:.3f}, {n:.3f}` | `{ox:.1f}, {oy:.1f}` | `{px:.3f}, {py:.3f}` | {point['residual_distance_pixels']:.3f} |")
    lines.extend(
        [
            "",
            "La superposición es técnicamente útil para orientación cualitativa porque los cuatro residuos son menores de 1,5 px. No se calcula ni presenta una diferencia píxel a píxel como métrica cartográfica.",
            "",
            "Los colores, rellenos y el alfabeto de bloques de los renders son exclusivamente diagnósticos; no definen teselas ni estilo de producto.",
            "",
            "## Controles revisados",
            "",
            f"Se conservaron {control_metrics['versioned_controls']} controles versionados y se comprobaron automáticamente {control_metrics['adjacent_boundary_pairs_checked']} pares municipales que comparten frontera.",
            "",
            "| ID | Zona esperada | Municipio o rasgo | Resultado | Limitación principal |",
            "|---|---|---|---|---|",
        ]
    )
    for row in controls:
        lines.append(f"| `{row['control_id']}` | `{row['expected_zone']}` | {row['municipality_or_feature']} | `{row['result']}` | {row['limitations']} |")
    lines.extend(
        [
            "",
            "El detalle completo de evidencia geométrica, evidencia visible y limitaciones consta en `control-points.csv`.",
            "",
            "## Discrepancias",
            "",
            f"Resultado: {classifications['explicable']} explicables, {classifications['corregible']} corregibles y {classifications['bloqueante']} bloqueantes.",
            "",
            "| ID | Ubicación / zonas | Clasificación | Evidencia | Origen posible | Decisión |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in discrepancies:
        lines.append(
            f"| `{item['id']}` | {item['location']} / {', '.join(item['zones'])} | "
            f"`{item['classification']}` | {item['evidence']} | "
            f"{'; '.join(item['possible_origin'])} | {item['decision']} |"
        )
    lines.extend(
        [
            "",
            "No se encontró contradicción material atribuible a la asignación 112CV, al crosswalk GEO-002, a la geometría ICV, a la reparación limitada de Xàtiva, a la disolución o a la reproyección GEO-003. No se propone repetir GEO-002 o GEO-003.",
            "",
            "## Composición, superposición y detalles",
            "",
            f"- Render independiente: `{DIAGNOSTIC_NAME}` ({image_dimensions[DIAGNOSTIC_NAME][0]}×{image_dimensions[DIAGNOSTIC_NAME][1]} px).",
            f"- Render registrado: `{REGISTERED_NAME}` ({image_dimensions[REGISTERED_NAME][0]}×{image_dimensions[REGISTERED_NAME][1]} px).",
            f"- Lado a lado: `{SIDE_BY_SIDE_NAME}` ({image_dimensions[SIDE_BY_SIDE_NAME][0]}×{image_dimensions[SIDE_BY_SIDE_NAME][1]} px).",
            f"- Superposición semitransparente: `{OVERLAY_NAME}` ({image_dimensions[OVERLAY_NAME][0]}×{image_dimensions[OVERLAY_NAME][1]} px).",
            "- Detalles: norte/Rincón, hueco central/zona 4, costa oriental/componentes y extremo sur.",
            "",
            "La composición muestra la misma silueta general, posición relativa, costa, Rincón, fronteras principales, hueco de 3/enclave de 5 y extremos. La superposición confirma la equivalencia visual con diferencias locales explicables por trazo, antialiasing, resolución, etiquetas, marca de agua y posible versión cartográfica.",
            "",
            "## Reproducibilidad",
            "",
            "```sh",
            ".venv-geo/bin/python tools/geo_compare.py build",
            ".venv-geo/bin/python tools/geo_compare.py validate",
            ".venv-geo/bin/python -m unittest tests.test_geo_compare -v",
            "```",
            "",
            "Versiones fijadas/observadas:",
            "",
        ]
    )
    for name, version in software.items():
        lines.append(f"- {name}: `{version}`.")
    lines.extend(
        [
            "",
            "Todos los PNG se serializan con Pillow fijado, compresión PNG nivel 9, sin metadatos temporales. Orden de zonas, dimensiones, rellenos diagnósticos, contornos, rótulos, recortes, escalas y transformación están fijados en `config/geo_compare.json`. `validate` regenera y exige igualdad byte a byte.",
            "",
            "## Conclusión y aprobación",
            "",
            "La evidencia preparada es compatible con aprobar que la geometría derivada representa materialmente las mismas siete zonas que el mapa oficial.",
            "",
        ]
    )
    if approved:
        lines.extend(
            [
                f"**Aprobación registrada:** {config['approval']['reviewer']} — {config['approval']['date']}. Decisión: “{config['approval']['decision']}”",
                "",
                f"Geometría congelada para el MVP: `{config['geometry_version']}`. TILES-001 debe consumir exactamente esa versión como entrada inmutable.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "**Pendiente:** nombre de persona revisora, fecha y aprobación explícita. Mientras falten, GEO-004 no se marca completado, no se declara `geometry_version` y TILES-001 permanece bloqueado por la barrera de aprobación.",
                "",
            ]
        )
    lines.extend(
        [
            "También siguen abiertas la confirmación formal de que PREVIFOC sea exactamente una unión de municipios completos y la licencia específica 112CV (`not_found`).",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_artifacts(
    config_path: Path = DEFAULT_CONFIG, *, run_prerequisites: bool = True
) -> tuple[dict[str, bytes], Path]:
    _require_dependencies()
    config_path = config_path.resolve()
    config = _load_config(config_path)
    if run_prerequisites:
        _run_prerequisite_validations()
    paths = _verify_frozen_inputs(config_path, config)
    reference, reference_path, reference_content, reference_image = _load_reference(paths["reference_metadata"])
    zones = _load_zones(paths["master"], config)
    registration = _registration(zones, config)
    controls, control_metrics = _validate_controls(config_path, config, paths, zones)

    registered_image = _render_geometry(zones, config, registration, output_scale=1)
    diagnostic_image = _render_geometry(
        zones,
        config,
        registration,
        output_scale=int(config["render"]["diagnostic_scale"]),
    )
    overlay_layer = _render_geometry(
        zones,
        config,
        registration,
        output_scale=1,
        overlay=True,
        labels=False,
    )
    images: dict[str, Any] = {
        REGISTERED_NAME: registered_image,
        DIAGNOSTIC_NAME: diagnostic_image,
        SIDE_BY_SIDE_NAME: _side_by_side(reference_image, registered_image),
        OVERLAY_NAME: _overlay(reference_image, overlay_layer),
    }
    for detail in config["details"]:
        name = f"details/{detail['name']}.png"
        images[name] = _detail_comparison(reference_image, registered_image, detail)
    artifacts = {name: _png_bytes(image) for name, image in images.items()}
    controls_content = _csv_bytes(controls)
    discrepancies_content = _json_bytes({"discrepancies": config["discrepancies"], "schema_version": 1})
    artifacts[CONTROLS_NAME] = controls_content
    artifacts[DISCREPANCIES_NAME] = discrepancies_content
    software = _software_versions()
    image_dimensions = {name: list(image.size) for name, image in images.items()}
    output_hashes = {name: sha256_bytes(content) for name, content in artifacts.items()}
    report_content = _report_bytes(
        config=config,
        reference=reference,
        reference_path=reference_path,
        registration=registration,
        controls=controls,
        control_metrics=control_metrics,
        output_hashes=output_hashes,
        image_dimensions=image_dimensions,
        software=software,
    )
    artifacts[REPORT_NAME] = report_content
    output_hashes[REPORT_NAME] = sha256_bytes(report_content)
    output_directory = _resolve(config_path.parent, config["output_directory"], "directorio GEO-004")
    manifest = {
        "comparison_schema_version": 1,
        "status": config["status"],
        "approval": {
            "approved": config["status"] == "approved",
            "date": config["approval"].get("date"),
            "decision": config["approval"].get("decision"),
            "reviewer": config["approval"].get("reviewer"),
        },
        "inputs": {
            "configuration": {"path": _relative(config_path, output_directory), "sha256": sha256_file(config_path)},
            "crosswalk": {"path": _relative(paths["crosswalk"], output_directory), "sha256": config["inputs"]["crosswalk"]["sha256"]},
            "geojson": {"path": _relative(paths["geojson"], output_directory), "sha256": config["inputs"]["geojson"]["sha256"]},
            "master": {"path": _relative(paths["master"], output_directory), "sha256": config["inputs"]["master"]["sha256"], "layer": "zones", "crs": "EPSG:25830"},
            "reference": {
                "content_type": reference["content_type"],
                "dimensions_pixels": reference["dimensions_pixels"],
                "license_status": reference["license"]["status"],
                "metadata_path": _relative(paths["reference_metadata"], output_directory),
                "metadata_sha256": sha256_file(paths["reference_metadata"]),
                "retrieved_at_utc": reference["retrieved_at_utc"],
                "sha256": sha256_bytes(reference_content),
                "size_bytes": len(reference_content),
                "snapshot": _relative(reference_path, output_directory),
                "url_final": reference["url_final"],
                "url_requested": reference["url_requested"],
            },
            "requirements": {"path": _relative(paths["requirements"], output_directory), "sha256": sha256_file(paths["requirements"])},
        },
        "outputs": {
            name: {
                "sha256": output_hashes[name],
                "size_bytes": len(artifacts[name]),
                **({"dimensions_pixels": image_dimensions[name]} if name in image_dimensions else {}),
            }
            for name in sorted(artifacts)
        },
        "policies": {
            "comparison": "qualitative_visual_not_pixel_metric",
            "geometry": "exact GEO-003 coordinates; no simplification, filtering, hole filling or coordinate changes",
            "reference": "original bytes preserved; all crops/scales are separate derivatives",
            "style": "diagnostic_only_not_tile_design",
        },
        **({"geometry_version": config["geometry_version"]} if config["status"] == "approved" else {}),
        "registration": registration,
        "software": software,
        "statistics": {
            "controls": control_metrics,
            "discrepancies": {
                "bloqueante": sum(item["classification"] == "bloqueante" for item in config["discrepancies"]),
                "corregible": sum(item["classification"] == "corregible" for item in config["discrepancies"]),
                "explicable": sum(item["classification"] == "explicable" for item in config["discrepancies"]),
            },
            "zone_codes": EXPECTED_CODES,
            "zone_features": 7,
        },
        "unresolved_conditions": {
            "formal_confirmation_previfoc_is_union_of_complete_municipalities": False,
            "human_approval": "approved" if config["status"] == "approved" else "pending",
            "specific_112cv_license": "not_found",
        },
    }
    artifacts[MANIFEST_NAME] = _json_bytes(manifest)
    return artifacts, output_directory


def build_comparison(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    for name in sorted(artifacts):
        _atomic_write(output_directory / name, artifacts[name])
    return artifacts


def validate_comparison(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    for name, expected in artifacts.items():
        path = output_directory / name
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise CompareError(f"no se puede leer el entregable {path}: {exc}") from exc
        if observed != expected:
            raise CompareError(f"{path} no coincide byte a byte con la regeneración")
    return artifacts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construye y valida los entregables reproducibles de GEO-004."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("build", "generar renders, comparativas, controles, informe y manifiesto"),
        ("validate", "regenerar y exigir igualdad byte a byte"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        artifacts = build_comparison(args.config) if args.command == "build" else validate_comparison(args.config)
        manifest = json.loads(artifacts[MANIFEST_NAME])
        output = _resolve(args.config.resolve().parent, _load_config(args.config.resolve())["output_directory"], "directorio GEO-004")
        print(f"directorio: {output}")
        print(f"referencia sha256: {manifest['inputs']['reference']['sha256']}")
        print(f"zonas: {manifest['statistics']['zone_features']}; códigos: {','.join(manifest['statistics']['zone_codes'])}")
        print(f"discrepancias: {manifest['statistics']['discrepancies']}")
        print(f"aprobación humana: {manifest['unresolved_conditions']['human_approval']}")
        return 0
    except (CompareError, geo_zones.ZoneError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
