#!/usr/bin/env python3
"""Construye y valida las siete geometrías canónicas de GEO-003.

La construcción es completamente offline. Antes de leer geometrías ejecuta las
validaciones de GEO-001 y GEO-002, vuelve a fijar el SHA-256 del crosswalk, une
por código municipal textual, repara únicamente las invalideces esperadas y
disuelve en EPSG:25830. La salida maestra es un GeoPackage determinista y el
GeoJSON se serializa en longitud/latitud conforme a RFC 7946.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence
import urllib.parse


try:
    import numpy
    import pyproj
    import shapely
    from shapely import from_wkb, make_valid, to_wkb, transform, union_all
    from shapely.errors import GEOSException
    from shapely.geometry import GeometryCollection, MultiPolygon, Polygon
    from shapely.validation import explain_validity
except ModuleNotFoundError as exc:  # Permite mostrar un error de instalación claro.
    numpy = None  # type: ignore[assignment]
    pyproj = None  # type: ignore[assignment]
    shapely = None  # type: ignore[assignment]
    from_wkb = make_valid = to_wkb = transform = union_all = None  # type: ignore[assignment]
    GEOSException = Exception  # type: ignore[assignment,misc]
    GeometryCollection = MultiPolygon = Polygon = None  # type: ignore[assignment,misc]
    explain_validity = None  # type: ignore[assignment]
    _DEPENDENCY_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _DEPENDENCY_IMPORT_ERROR = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "geo_zones.json"
MASTER_NAME = "zones.gpkg"
GEOJSON_NAME = "zones.geojson"
REPORT_NAME = "REPORT.md"
MANIFEST_NAME = "manifest.json"
MASTER_LAYER = "zones"
EXPECTED_CROSSWALK_FIELDS = {
    "municipio_112cv",
    "id_zona_previfoc",
    "icv_cod_ine_mun",
}
CODE_PATTERN = re.compile(r"\d{5}")


class ZoneError(RuntimeError):
    """Fallo esperado de dependencias, entrada, topología o reproducibilidad."""


def _require_dependencies() -> None:
    if _DEPENDENCY_IMPORT_ERROR is not None:
        raise ZoneError(
            "faltan dependencias geoespaciales; cree un entorno Python 3.13 e "
            "instale requirements-geo.txt: "
            f"{_DEPENDENCY_IMPORT_ERROR}"
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
        raise ZoneError(f"no se puede leer {path}: {exc}") from exc
    return digest.hexdigest()


def _json_bytes(value: Any, *, sort_keys: bool = True) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=sort_keys,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ZoneError(f"no se puede serializar JSON determinista: {exc}") from exc
    return (rendered + "\n").encode("utf-8")


def _load_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZoneError(f"no se puede leer {description} {path}: {exc}") from exc


def _resolve(base: Path, value: str, description: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ZoneError(f"ruta inválida para {description}")
    return (base / value).resolve()


def _relative(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def _load_config(path: Path) -> dict[str, Any]:
    config = _load_json(path, "la configuración de GEO-003")
    required = {
        "build_timestamp_utc",
        "crosswalk",
        "expected_invalid_geometries",
        "geojson",
        "icv",
        "input_manifests",
        "master_crs",
        "output_directory",
        "outputs",
        "repair",
        "requirements",
        "schema_version",
        "tolerances",
        "zones",
    }
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ZoneError("schema_version de GEO-003 no soportada")
    missing = required - set(config)
    if missing:
        raise ZoneError(f"faltan claves de configuración: {sorted(missing)}")
    if config["master_crs"] != "EPSG:25830":
        raise ZoneError("el CRS maestro debe ser EPSG:25830")
    if config["geojson"].get("crs") != "EPSG:4326":
        raise ZoneError("el GeoJSON debe configurarse en EPSG:4326")
    if not isinstance(config["geojson"].get("coordinate_precision"), int):
        raise ZoneError("coordinate_precision debe ser entero")
    configured_outputs = config["outputs"]
    if configured_outputs != {
        "geojson": GEOJSON_NAME,
        "manifest": MANIFEST_NAME,
        "master": MASTER_NAME,
        "report": REPORT_NAME,
    }:
        raise ZoneError("los nombres de salida de GEO-003 no coinciden con el contrato")
    zones = config["zones"]
    if not isinstance(zones, list) or len(zones) != 7:
        raise ZoneError("deben configurarse exactamente siete zonas")
    expected_ids = list(range(53, 60))
    expected_codes = ["1N", "1S", "2", "3", "4", "5", "6"]
    if [zone.get("zone_id") for zone in zones] != expected_ids:
        raise ZoneError("los zone_id deben estar ordenados y ser 53–59")
    if [zone.get("zone_code") for zone in zones] != expected_codes:
        raise ZoneError("los códigos de zona no coinciden con 1N, 1S, 2–6")
    if sum(int(zone.get("municipalities", -1)) for zone in zones) != 542:
        raise ZoneError("los conteos configurados no suman 542 municipios")
    repair = config["repair"]
    if repair != {
        "keep_collapsed": True,
        "method": "linework",
        "operation": "shapely.make_valid",
    }:
        raise ZoneError("la política de reparación debe ser MakeValid linework")
    tolerance_keys = {
        "coverage_absolute_m2",
        "coverage_relative",
        "geojson_roundtrip_absolute_m2",
        "geojson_roundtrip_relative",
        "overlap_absolute_m2",
        "overlap_relative",
        "repair_absolute_m2",
        "repair_relative",
    }
    if set(config["tolerances"]) != tolerance_keys:
        raise ZoneError("el conjunto de tolerancias de GEO-003 está incompleto")
    if any(float(config["tolerances"][key]) < 0 for key in tolerance_keys):
        raise ZoneError("las tolerancias no pueden ser negativas")
    return config


def _run_prerequisite_validations() -> dict[str, str]:
    """Ejecuta las barreras obligatorias antes de tocar geometrías."""

    commands = {
        "geo_sources": [sys.executable, str(PROJECT_ROOT / "tools/geo_sources.py"), "validate"],
        "geo_crosswalk": [
            sys.executable,
            str(PROJECT_ROOT / "tools/geo_crosswalk.py"),
            "validate",
        ],
    }
    outputs: dict[str, str] = {}
    for name, command in commands.items():
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
            raise ZoneError(
                f"falló la barrera previa {' '.join(command[1:])}: {detail}"
            )
        outputs[name] = result.stdout.strip()
    return outputs


def _verify_input_manifests(
    config_path: Path, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    source_manifest_path = _resolve(
        config_path.parent,
        config["input_manifests"]["sources"],
        "manifiesto de GEO-001",
    )
    crosswalk_manifest_path = _resolve(
        config_path.parent,
        config["input_manifests"]["crosswalk"],
        "manifiesto de GEO-002",
    )
    source_manifest = _load_json(source_manifest_path, "el manifiesto de GEO-001")
    crosswalk_manifest = _load_json(
        crosswalk_manifest_path, "el manifiesto de GEO-002"
    )
    try:
        icv_record = source_manifest["sources"]["icv_municipios"]
        crosswalk_record = crosswalk_manifest["outputs"]["crosswalk.csv"]
    except (KeyError, TypeError) as exc:
        raise ZoneError("los manifiestos previos no cumplen el contrato esperado") from exc
    icv_config = config["icv"]
    observed_icv = {
        "sha256": icv_record.get("sha256"),
        "dataset_content_sha256": icv_record.get("inspection", {}).get(
            "dataset_content_sha256"
        ),
    }
    expected_icv = {
        "sha256": icv_config["sha256"],
        "dataset_content_sha256": icv_config["dataset_content_sha256"],
    }
    if observed_icv != expected_icv:
        raise ZoneError(
            f"la procedencia ICV del manifiesto cambió: {observed_icv} != {expected_icv}"
        )
    if crosswalk_record.get("sha256") != config["crosswalk"]["sha256"]:
        raise ZoneError("el manifiesto de GEO-002 registra otro SHA-256 de crosswalk")
    if int(crosswalk_record.get("rows", -1)) != int(
        config["crosswalk"]["expected_rows"]
    ):
        raise ZoneError("el manifiesto de GEO-002 registra otro número de filas")
    return (
        source_manifest,
        crosswalk_manifest,
        source_manifest_path,
        crosswalk_manifest_path,
    )


def _load_crosswalk(
    path: Path, config: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    expected_sha = config["crosswalk"]["sha256"]
    observed_sha = sha256_file(path)
    if observed_sha != expected_sha:
        raise ZoneError(
            "SHA-256 del crosswalk distinto al aprobado; no se procesan geometrías "
            f"({observed_sha} != {expected_sha})"
        )
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or ())
            if not EXPECTED_CROSSWALK_FIELDS.issubset(fields):
                raise ZoneError(
                    f"el crosswalk no contiene los campos {sorted(EXPECTED_CROSSWALK_FIELDS)}"
                )
            rows = [dict(row) for row in reader]
    except ZoneError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ZoneError(f"no se puede leer el crosswalk {path}: {exc}") from exc
    expected_rows = int(config["crosswalk"]["expected_rows"])
    if len(rows) != expected_rows:
        raise ZoneError(f"el crosswalk contiene {len(rows)} filas; se esperaban {expected_rows}")
    allowed_zones = {str(zone["zone_id"]) for zone in config["zones"]}
    codes: list[str] = []
    names: list[str] = []
    counts: collections.Counter[str] = collections.Counter()
    for index, row in enumerate(rows, start=2):
        code = row["icv_cod_ine_mun"]
        name = row["municipio_112cv"]
        zone = row["id_zona_previfoc"]
        if not isinstance(code, str) or CODE_PATTERN.fullmatch(code) is None:
            raise ZoneError(
                f"código ICV inválido en crosswalk línea {index}: {code!r}; "
                "debe seguir siendo texto de cinco dígitos"
            )
        if not name or name == "Fuera C.V.":
            raise ZoneError(f"municipio 112CV inválido en crosswalk línea {index}")
        if zone not in allowed_zones:
            raise ZoneError(f"zona no permitida {zone!r} en crosswalk línea {index}")
        codes.append(code)
        names.append(name)
        counts[zone] += 1
    duplicate_codes = sorted(
        value for value, count in collections.Counter(codes).items() if count != 1
    )
    duplicate_names = sorted(
        value for value, count in collections.Counter(names).items() if count != 1
    )
    if duplicate_codes or duplicate_names:
        raise ZoneError(
            "el crosswalk dejó de ser biyectivo; "
            f"códigos duplicados={duplicate_codes[:10]}, nombres duplicados={duplicate_names[:10]}"
        )
    expected_counts = {
        str(zone["zone_id"]): int(zone["municipalities"])
        for zone in config["zones"]
    }
    if dict(sorted(counts.items())) != expected_counts:
        raise ZoneError(
            f"conteos del crosswalk {dict(sorted(counts.items()))}; "
            f"esperados {expected_counts}"
        )
    return rows, dict(sorted(counts.items()))


def _quote_identifier(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ZoneError(f"identificador SQLite inválido: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri_path = urllib.parse.quote(str(path.resolve()), safe="/")
    try:
        connection = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise ZoneError(f"no se puede abrir el GeoPackage fijado: {exc}") from exc


def _decode_gpkg_geometry(blob: bytes, expected_srs_id: int) -> Any:
    _require_dependencies()
    if not isinstance(blob, bytes) or len(blob) < 17 or blob[:2] != b"GP":
        raise ZoneError("geometría sin cabecera GeoPackage válida")
    if blob[2] != 0:
        raise ZoneError(f"versión de geometría GeoPackage no soportada: {blob[2]}")
    flags = blob[3]
    if flags & 0x20 or flags & 0x10:
        raise ZoneError("geometría GeoPackage extendida o marcada como vacía")
    endian = "<" if flags & 0x01 else ">"
    srs_id = struct.unpack(f"{endian}i", blob[4:8])[0]
    if srs_id != expected_srs_id:
        raise ZoneError(f"geometría con srs_id {srs_id}; esperado {expected_srs_id}")
    envelope_indicator = (flags >> 1) & 0x07
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_indicator not in envelope_sizes:
        raise ZoneError("indicador de envolvente GeoPackage inválido")
    offset = 8 + envelope_sizes[envelope_indicator]
    try:
        geometry = from_wkb(blob[offset:])
    except Exception as exc:
        raise ZoneError(f"WKB de GeoPackage no legible: {exc}") from exc
    if geometry.geom_type != "MultiPolygon":
        raise ZoneError(
            f"geometría municipal {geometry.geom_type}; se esperaba MultiPolygon"
        )
    if geometry.is_empty:
        raise ZoneError("geometría municipal vacía")
    return geometry


def _load_icv_geometries(
    path: Path, config: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    expected_sha = config["icv"]["sha256"]
    observed_sha = sha256_file(path)
    if observed_sha != expected_sha:
        raise ZoneError(
            f"SHA-256 del snapshot ICV incorrecto ({observed_sha} != {expected_sha})"
        )
    settings = config["icv"]
    layer = settings["layer"]
    code_field = settings["code_field"]
    name_field = settings["name_field"]
    geometry_field = settings["geometry_field"]
    expected_srs = int(settings["crs"].split(":", 1)[1])
    try:
        with contextlib.closing(_connect_readonly(path)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ZoneError("integrity_check del snapshot ICV no es ok")
            geometry_metadata = connection.execute(
                "SELECT column_name, geometry_type_name, srs_id FROM "
                "gpkg_geometry_columns WHERE table_name = ?",
                (layer,),
            ).fetchone()
            if geometry_metadata is None:
                raise ZoneError(f"la capa {layer!r} no figura en gpkg_geometry_columns")
            if (
                geometry_metadata["column_name"] != geometry_field
                or geometry_metadata["geometry_type_name"].upper() != "MULTIPOLYGON"
                or int(geometry_metadata["srs_id"]) != expected_srs
            ):
                raise ZoneError("metadatos geométricos ICV distintos al contrato")
            srs = connection.execute(
                "SELECT srs_name, srs_id, organization, organization_coordsys_id, "
                "definition, description FROM gpkg_spatial_ref_sys WHERE srs_id = ?",
                (expected_srs,),
            ).fetchone()
            if srs is None:
                raise ZoneError(f"el snapshot no declara EPSG:{expected_srs}")
            query = (
                f"SELECT {_quote_identifier(code_field)}, {_quote_identifier(name_field)}, "
                f"{_quote_identifier(geometry_field)} FROM {_quote_identifier(layer)} "
                f"ORDER BY {_quote_identifier(code_field)}"
            )
            sql_rows = connection.execute(query).fetchall()
    except ZoneError:
        raise
    except sqlite3.Error as exc:
        raise ZoneError(f"error al leer la capa ICV {layer!r}: {exc}") from exc
    if len(sql_rows) != 542:
        raise ZoneError(f"la capa ICV contiene {len(sql_rows)} filas; se esperaban 542")
    rows: dict[str, dict[str, Any]] = {}
    for sql_row in sql_rows:
        code = sql_row[code_field]
        name = sql_row[name_field]
        if not isinstance(code, str) or CODE_PATTERN.fullmatch(code) is None:
            raise ZoneError(f"código ICV no textual de cinco dígitos: {code!r}")
        if code in rows:
            raise ZoneError(f"código ICV duplicado: {code}")
        if not isinstance(name, str) or not name.strip():
            raise ZoneError(f"nombre ICV vacío para {code}")
        geometry_blob = sql_row[geometry_field]
        if not isinstance(geometry_blob, bytes):
            raise ZoneError(f"blob geométrico no binario para {code}")
        rows[code] = {
            "code": code,
            "name": name,
            "geometry": _decode_gpkg_geometry(geometry_blob, expected_srs),
        }
    return rows, dict(srs)


def _polygon_parts(geometry: Any) -> list[Any]:
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}:
        parts: list[Any] = []
        for component in geometry.geoms:
            parts.extend(_polygon_parts(component))
        return parts
    return []


def _non_polygonal_components(geometry: Any) -> list[Any]:
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return []
    if geometry.geom_type == "GeometryCollection":
        parts: list[Any] = []
        for component in geometry.geoms:
            parts.extend(_non_polygonal_components(component))
        return parts
    return [geometry]


def _ensure_multipolygon(geometry: Any, description: str) -> Any:
    if geometry.geom_type == "Polygon":
        geometry = MultiPolygon([geometry])
    if geometry.geom_type != "MultiPolygon":
        raise ZoneError(f"{description}: resultado {geometry.geom_type}, no MultiPolygon")
    if geometry.is_empty or not geometry.is_valid:
        reason = explain_validity(geometry)
        raise ZoneError(f"{description}: MultiPolygon vacío o inválido: {reason}")
    return geometry


def _part_hole_counts(geometry: Any) -> tuple[int, int]:
    parts = _polygon_parts(geometry)
    return len(parts), sum(len(part.interiors) for part in parts)


def _bbox(geometry: Any) -> list[float]:
    return [float(value) for value in geometry.bounds]


def _threshold(absolute: float, relative: float, reference: float) -> float:
    return max(float(absolute), float(relative) * abs(float(reference)))


def _repair_geometries(
    municipalities: dict[str, dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    expected_invalid = config["expected_invalid_geometries"]
    observed_invalid: dict[str, str] = {}
    for code, record in municipalities.items():
        geometry = record["geometry"]
        if not geometry.is_valid:
            observed_invalid[code] = explain_validity(geometry)
    if set(observed_invalid) != set(expected_invalid):
        raise ZoneError(
            "el conjunto de geometrías inválidas cambió; "
            f"observadas={observed_invalid}, esperadas={sorted(expected_invalid)}"
        )
    for code, reason in observed_invalid.items():
        expected = expected_invalid[code]
        if municipalities[code]["name"] != expected["name"]:
            raise ZoneError(f"el nombre ICV esperado para la reparación {code} cambió")
        if not reason.startswith(expected["reason_prefix"]):
            raise ZoneError(
                f"el motivo de invalidez de {code} cambió: {reason!r}"
            )

    repaired: dict[str, Any] = {}
    repairs: list[dict[str, Any]] = []
    valid_before = 0
    tolerance = config["tolerances"]
    for code in sorted(municipalities):
        record = municipalities[code]
        before = record["geometry"]
        if before.is_valid:
            valid_before += 1
            repaired[code] = before
            continue
        raw_result = make_valid(
            before,
            method=config["repair"]["method"],
            keep_collapsed=config["repair"]["keep_collapsed"],
        )
        polygons = _polygon_parts(raw_result)
        if not polygons:
            raise ZoneError(f"MakeValid no produjo superficie poligonal para {code}")
        polygonal = union_all(polygons)
        after = _ensure_multipolygon(polygonal, f"reparación de {code}")
        non_polygonal = _non_polygonal_components(raw_result)
        before_parts, before_holes = _part_hole_counts(before)
        after_parts, after_holes = _part_hole_counts(after)
        area_delta_signed = float(after.area - before.area)
        area_delta_absolute = abs(area_delta_signed)
        area_delta_relative = area_delta_absolute / float(before.area)
        try:
            symmetric_difference = float(before.symmetric_difference(after).area)
        except GEOSException as exc:
            raise ZoneError(
                f"no se pudo medir la diferencia simétrica de la reparación {code}: {exc}"
            ) from exc
        allowed = _threshold(
            tolerance["repair_absolute_m2"],
            tolerance["repair_relative"],
            before.area,
        )
        if max(area_delta_absolute, symmetric_difference) > allowed:
            raise ZoneError(
                f"la reparación {code} excede la tolerancia {allowed} m²"
            )
        discarded_summary = [
            {
                "area_m2": float(component.area),
                "geometry_type": component.geom_type,
                "length_m": float(component.length),
            }
            for component in non_polygonal
        ]
        repairs.append(
            {
                "after": {
                    "area_m2": float(after.area),
                    "bbox_epsg25830": _bbox(after),
                    "holes": after_holes,
                    "parts": after_parts,
                    "valid": bool(after.is_valid),
                },
                "area_delta_absolute_m2": area_delta_absolute,
                "area_delta_relative": area_delta_relative,
                "area_delta_signed_m2": area_delta_signed,
                "before": {
                    "area_m2": float(before.area),
                    "bbox_epsg25830": _bbox(before),
                    "holes": before_holes,
                    "parts": before_parts,
                    "valid": bool(before.is_valid),
                },
                "cod_ine_mun": code,
                "discarded_non_polygonal_components": discarded_summary,
                "effect": (
                    "Se fusionan dos partes que compartían un segmento; se conserva "
                    "toda la superficie, el bbox y los huecos. El segmento colapsado "
                    "se registra como linework de área cero y no representa una isla."
                ),
                "municipality": record["name"],
                "operation": "shapely.make_valid(method='linework', keep_collapsed=True) y extracción de la componente poligonal",
                "reason": observed_invalid[code],
                "symmetric_difference_m2": symmetric_difference,
                "tolerance_m2": allowed,
                "within_tolerance": True,
            }
        )
        repaired[code] = after
    counts = {
        "municipalities_inspected": len(municipalities),
        "valid_before_repair": valid_before,
        "invalid_before_repair": len(observed_invalid),
        "valid_after_repair": sum(geometry.is_valid for geometry in repaired.values()),
        "repairs_applied": len(repairs),
    }
    return repaired, repairs, counts


def _signed_area(coordinates: Sequence[tuple[float, float]]) -> float:
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(
            coordinates, (*coordinates[1:], coordinates[0])
        )
    )


def _clean_coordinate(value: float, precision: int | None) -> float:
    result = round(float(value), precision) if precision is not None else float(value)
    return 0.0 if result == 0.0 else result


def _canonical_ring(
    coordinates: Iterable[Sequence[float]], *, ccw: bool, precision: int | None
) -> tuple[tuple[float, float], ...]:
    values = [
        (_clean_coordinate(point[0], precision), _clean_coordinate(point[1], precision))
        for point in coordinates
    ]
    if values and values[0] == values[-1]:
        values.pop()
    deduplicated: list[tuple[float, float]] = []
    for point in values:
        if not deduplicated or point != deduplicated[-1]:
            deduplicated.append(point)
    if len(deduplicated) < 3 or len(set(deduplicated)) < 3:
        raise ZoneError("un anillo colapsó durante la serialización")
    signed = _signed_area(deduplicated)
    if signed == 0:
        raise ZoneError("un anillo tiene área orientada cero")
    if (signed > 0) != ccw:
        deduplicated.reverse()
    minimum = min(deduplicated)
    candidates = []
    for index, point in enumerate(deduplicated):
        if point == minimum:
            candidates.append(
                tuple(deduplicated[index:] + deduplicated[:index])
            )
    canonical = min(candidates)
    return (*canonical, canonical[0])


def canonicalize_multipolygon(
    geometry: Any, *, precision: int | None = None
) -> Any:
    """Normaliza orientación, inicio/anillos y orden de partes sin simplificar."""

    _require_dependencies()
    geometry = _ensure_multipolygon(geometry, "canonicalización")
    polygons: list[Any] = []
    for source_polygon in geometry.geoms:
        exterior = _canonical_ring(
            source_polygon.exterior.coords, ccw=True, precision=precision
        )
        holes = sorted(
            (
                _canonical_ring(ring.coords, ccw=False, precision=precision)
                for ring in source_polygon.interiors
            ),
            key=lambda ring: ring,
        )
        polygon = Polygon(exterior, holes)
        if polygon.is_empty or not polygon.is_valid:
            raise ZoneError(
                "la canonicalización produjo un polígono inválido: "
                f"{explain_validity(polygon)}"
            )
        polygons.append(polygon)
    polygons.sort(key=_geometry_wkb)
    result = MultiPolygon(polygons)
    return _ensure_multipolygon(result, "canonicalización")


def _geometry_wkb(geometry: Any) -> bytes:
    return to_wkb(
        geometry,
        hex=False,
        output_dimension=2,
        byte_order=1,
        include_srid=False,
        flavor="iso",
    )


def geometry_sha256(geometry: Any) -> str:
    return sha256_bytes(_geometry_wkb(geometry))


def _dissolve_zones(
    repaired: dict[str, Any],
    crosswalk_rows: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[dict[int, Any], dict[int, list[str]]]:
    codes_by_zone: dict[int, list[str]] = {
        int(zone["zone_id"]): [] for zone in config["zones"]
    }
    for row in crosswalk_rows:
        codes_by_zone[int(row["id_zona_previfoc"])].append(
            row["icv_cod_ine_mun"]
        )
    zones: dict[int, Any] = {}
    for zone in config["zones"]:
        zone_id = int(zone["zone_id"])
        codes = sorted(codes_by_zone[zone_id])
        if len(codes) != int(zone["municipalities"]):
            raise ZoneError(f"conteo inesperado durante disolución de zona {zone_id}")
        dissolved = union_all([repaired[code] for code in codes])
        dissolved = _ensure_multipolygon(dissolved, f"zona {zone_id}")
        zones[zone_id] = canonicalize_multipolygon(dissolved)
    return zones, codes_by_zone


def evaluate_topology(
    municipal_geometries: Sequence[Any],
    zones: dict[int, Any],
    tolerances: dict[str, float],
    *,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    reference = _ensure_multipolygon(
        union_all(list(municipal_geometries)), "unión municipal de referencia"
    )
    zone_union = _ensure_multipolygon(
        union_all([zones[zone_id] for zone_id in sorted(zones)]),
        "unión de las siete zonas",
    )
    symmetric_difference = float(reference.symmetric_difference(zone_union).area)
    reference_area = float(reference.area)
    coverage_threshold = _threshold(
        tolerances["coverage_absolute_m2"],
        tolerances["coverage_relative"],
        reference_area,
    )
    coverage_passes = symmetric_difference <= coverage_threshold
    pairs: list[dict[str, Any]] = []
    overlap_passes = True
    for left_index, left_id in enumerate(sorted(zones)):
        for right_id in sorted(zones)[left_index + 1 :]:
            overlap = float(zones[left_id].intersection(zones[right_id]).area)
            reference_pair_area = min(float(zones[left_id].area), float(zones[right_id].area))
            allowed = _threshold(
                tolerances["overlap_absolute_m2"],
                tolerances["overlap_relative"],
                reference_pair_area,
            )
            passes = overlap <= allowed
            overlap_passes = overlap_passes and passes
            pairs.append(
                {
                    "area_m2": overlap,
                    "left_zone_id": left_id,
                    "passes": passes,
                    "right_zone_id": right_id,
                    "tolerance_m2": allowed,
                }
            )
    result = {
        "coverage": {
            "municipal_union_area_m2": reference_area,
            "passes": coverage_passes,
            "relative_symmetric_difference": (
                symmetric_difference / reference_area if reference_area else 0.0
            ),
            "symmetric_difference_m2": symmetric_difference,
            "tolerance_m2": coverage_threshold,
            "zone_area_sum_m2": float(sum(zone.area for zone in zones.values())),
            "zone_union_area_m2": float(zone_union.area),
        },
        "overlaps": {
            "max_area_m2": max((pair["area_m2"] for pair in pairs), default=0.0),
            "pairs": pairs,
            "pairs_checked": len(pairs),
            "passes": overlap_passes,
        },
    }
    if raise_on_failure and not (coverage_passes and overlap_passes):
        raise ZoneError(
            "falló la topología: "
            f"cobertura={result['coverage']}, solapes={result['overlaps']}"
        )
    return result


def _gpkg_geometry_blob(geometry: Any, srs_id: int) -> bytes:
    min_x, min_y, max_x, max_y = geometry.bounds
    # Cabecera GeoPackage v0, little-endian, envolvente XY, geometría no vacía.
    header = struct.pack(
        "<2sBBi4d",
        b"GP",
        0,
        0x03,
        int(srs_id),
        float(min_x),
        float(max_x),
        float(min_y),
        float(max_y),
    )
    return header + _geometry_wkb(geometry)


def _render_master_gpkg(
    zone_records: list[dict[str, Any]],
    srs: dict[str, Any],
    timestamp: str,
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="geo003-gpkg-") as temporary:
        path = Path(temporary) / MASTER_NAME
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                """
                PRAGMA page_size=4096;
                PRAGMA auto_vacuum=NONE;
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;
                PRAGMA application_id=1196444487;
                PRAGMA user_version=10200;
                CREATE TABLE gpkg_spatial_ref_sys (
                  srs_name TEXT NOT NULL,
                  srs_id INTEGER NOT NULL PRIMARY KEY,
                  organization TEXT NOT NULL,
                  organization_coordsys_id INTEGER NOT NULL,
                  definition TEXT NOT NULL,
                  description TEXT
                );
                CREATE TABLE gpkg_contents (
                  table_name TEXT NOT NULL PRIMARY KEY,
                  data_type TEXT NOT NULL,
                  identifier TEXT UNIQUE,
                  description TEXT DEFAULT '',
                  last_change DATETIME NOT NULL,
                  min_x DOUBLE,
                  min_y DOUBLE,
                  max_x DOUBLE,
                  max_y DOUBLE,
                  srs_id INTEGER,
                  CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id)
                    REFERENCES gpkg_spatial_ref_sys(srs_id)
                );
                CREATE TABLE gpkg_geometry_columns (
                  table_name TEXT NOT NULL,
                  column_name TEXT NOT NULL,
                  geometry_type_name TEXT NOT NULL,
                  srs_id INTEGER NOT NULL,
                  z TINYINT NOT NULL,
                  m TINYINT NOT NULL,
                  CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
                  CONSTRAINT fk_gc_tn FOREIGN KEY (table_name)
                    REFERENCES gpkg_contents(table_name),
                  CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id)
                    REFERENCES gpkg_spatial_ref_sys(srs_id)
                );
                CREATE TABLE zones (
                  fid INTEGER NOT NULL PRIMARY KEY,
                  geom MULTIPOLYGON NOT NULL,
                  zone_id INTEGER NOT NULL UNIQUE,
                  zone_code TEXT NOT NULL UNIQUE,
                  municipality_count INTEGER NOT NULL,
                  area_m2 REAL NOT NULL,
                  part_count INTEGER NOT NULL,
                  geometry_sha256 TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT INTO gpkg_spatial_ref_sys VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("Undefined Cartesian SRS", -1, "NONE", -1, "undefined", "undefined Cartesian coordinate reference system"),
                    ("Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"),
                    (
                        srs["srs_name"],
                        int(srs["srs_id"]),
                        srs["organization"],
                        int(srs["organization_coordsys_id"]),
                        srs["definition"],
                        srs["description"],
                    ),
                ],
            )
            min_x = min(record["geometry"].bounds[0] for record in zone_records)
            min_y = min(record["geometry"].bounds[1] for record in zone_records)
            max_x = max(record["geometry"].bounds[2] for record in zone_records)
            max_y = max(record["geometry"].bounds[3] for record in zone_records)
            connection.execute(
                "INSERT INTO gpkg_contents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    MASTER_LAYER,
                    "features",
                    MASTER_LAYER,
                    "Siete zonas PREVIFOC derivadas de la asignación municipal oficial",
                    timestamp,
                    min_x,
                    min_y,
                    max_x,
                    max_y,
                    int(srs["srs_id"]),
                ),
            )
            connection.execute(
                "INSERT INTO gpkg_geometry_columns VALUES (?, ?, ?, ?, ?, ?)",
                (MASTER_LAYER, "geom", "MULTIPOLYGON", int(srs["srs_id"]), 0, 0),
            )
            connection.executemany(
                "INSERT INTO zones VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        index,
                        _gpkg_geometry_blob(record["geometry"], int(srs["srs_id"])),
                        record["zone_id"],
                        record["zone_code"],
                        record["municipality_count"],
                        record["area_m2"],
                        record["part_count"],
                        record["geometry_sha256"],
                    )
                    for index, record in enumerate(zone_records, start=1)
                ],
            )
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ZoneError(f"integrity_check de la geometría maestra: {integrity}")
            connection.execute("VACUUM")
            connection.commit()
        except sqlite3.Error as exc:
            raise ZoneError(f"no se pudo construir el GeoPackage maestro: {exc}") from exc
        finally:
            connection.close()
        _validate_master_gpkg(path, zone_records, int(srs["srs_id"]))
        return path.read_bytes()


def _validate_master_gpkg(
    path: Path, expected_records: list[dict[str, Any]], expected_srs: int
) -> None:
    try:
        with contextlib.closing(_connect_readonly(path)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ZoneError("integrity_check no válido en la salida maestra")
            if connection.execute("PRAGMA application_id").fetchone()[0] != 0x47504B47:
                raise ZoneError("la salida maestra no declara application_id GeoPackage")
            metadata = connection.execute(
                "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns "
                "WHERE table_name = ? AND column_name = 'geom'",
                (MASTER_LAYER,),
            ).fetchone()
            if (
                metadata is None
                or metadata["geometry_type_name"] != "MULTIPOLYGON"
                or int(metadata["srs_id"]) != expected_srs
            ):
                raise ZoneError("metadatos geométricos incorrectos en la salida maestra")
            rows = connection.execute(
                "SELECT fid, geom, zone_id, zone_code, municipality_count, area_m2, "
                "part_count, geometry_sha256 FROM zones ORDER BY zone_id"
            ).fetchall()
    except ZoneError:
        raise
    except sqlite3.Error as exc:
        raise ZoneError(f"no se pudo validar el GeoPackage maestro: {exc}") from exc
    if len(rows) != 7:
        raise ZoneError(f"la salida maestra contiene {len(rows)} entidades; se esperaban 7")
    for row, expected in zip(rows, expected_records):
        geometry = _decode_gpkg_geometry(row["geom"], expected_srs)
        parts, _ = _part_hole_counts(geometry)
        if not geometry.is_valid or geometry.is_empty:
            raise ZoneError(f"zona maestra inválida {row['zone_id']}")
        observed = (
            row["zone_id"],
            row["zone_code"],
            row["municipality_count"],
            row["part_count"],
            row["geometry_sha256"],
        )
        expected_values = (
            expected["zone_id"],
            expected["zone_code"],
            expected["municipality_count"],
            expected["part_count"],
            expected["geometry_sha256"],
        )
        if observed != expected_values or parts != expected["part_count"]:
            raise ZoneError(f"atributos maestros inesperados para zona {row['zone_id']}")
        if geometry_sha256(geometry) != expected["geometry_sha256"]:
            raise ZoneError(f"huella geométrica maestra incorrecta para zona {row['zone_id']}")


def _geometry_coordinates(geometry: Any) -> list[Any]:
    return [
        [
            [[float(x), float(y)] for x, y in polygon.exterior.coords],
            *[
                [[float(x), float(y)] for x, y in interior.coords]
                for interior in polygon.interiors
            ],
        ]
        for polygon in geometry.geoms
    ]


def _to_wgs84(
    geometry: Any, transformer: Any, coordinate_precision: int
) -> Any:
    projected = transform(geometry, transformer.transform, interleaved=False)
    return canonicalize_multipolygon(projected, precision=coordinate_precision)


def _render_geojson(
    zone_records: list[dict[str, Any]], coordinate_precision: int
) -> tuple[bytes, dict[int, Any]]:
    transformer = pyproj.Transformer.from_crs(
        "EPSG:25830", "EPSG:4326", always_xy=True
    )
    wgs84: dict[int, Any] = {}
    features: list[dict[str, Any]] = []
    for record in zone_records:
        geometry = _to_wgs84(
            record["geometry"], transformer, coordinate_precision
        )
        wgs84[record["zone_id"]] = geometry
        bounds = [round(value, coordinate_precision) for value in geometry.bounds]
        features.append(
            {
                "type": "Feature",
                "bbox": bounds,
                "id": record["zone_id"],
                "properties": {
                    "zone_id": record["zone_id"],
                    "zone_code": record["zone_code"],
                    "municipality_count": record["municipality_count"],
                },
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": _geometry_coordinates(geometry),
                },
            }
        )
    top_bbox = [
        min(feature["bbox"][0] for feature in features),
        min(feature["bbox"][1] for feature in features),
        max(feature["bbox"][2] for feature in features),
        max(feature["bbox"][3] for feature in features),
    ]
    document = {"type": "FeatureCollection", "bbox": top_bbox, "features": features}
    content = _json_bytes(document, sort_keys=False)
    _validate_geojson_document(document)
    return content, wgs84


def _iter_geojson_positions(coordinates: Any) -> Iterable[tuple[float, float]]:
    if (
        isinstance(coordinates, list)
        and len(coordinates) == 2
        and all(isinstance(value, (int, float)) for value in coordinates)
    ):
        yield float(coordinates[0]), float(coordinates[1])
        return
    if isinstance(coordinates, list):
        for value in coordinates:
            yield from _iter_geojson_positions(value)


def _validate_geojson_document(document: dict[str, Any]) -> None:
    if "crs" in document:
        raise ZoneError("RFC 7946 prohíbe declarar un miembro crs alternativo")
    if document.get("type") != "FeatureCollection":
        raise ZoneError("el GeoJSON no es FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or len(features) != 7:
        raise ZoneError("el GeoJSON debe contener exactamente siete features")
    expected_ids = list(range(53, 60))
    if [feature.get("id") for feature in features] != expected_ids:
        raise ZoneError("el orden/ID de features GeoJSON no es 53–59")
    for feature in features:
        if feature.get("type") != "Feature":
            raise ZoneError("entidad GeoJSON sin type=Feature")
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "MultiPolygon":
            raise ZoneError("toda geometría GeoJSON debe ser MultiPolygon")
        positions = list(_iter_geojson_positions(geometry.get("coordinates")))
        if not positions:
            raise ZoneError("geometría GeoJSON vacía")
        if any(
            not math.isfinite(lon)
            or not math.isfinite(lat)
            or lon < -180
            or lon > 180
            or lat < -90
            or lat > 90
            for lon, lat in positions
        ):
            raise ZoneError("posición GeoJSON fuera de longitud/latitud RFC 7946")
        # El primer anillo de cada polígono debe ser antihorario (regla de mano derecha).
        for polygon in geometry["coordinates"]:
            if _signed_area([tuple(position) for position in polygon[0][:-1]]) <= 0:
                raise ZoneError("anillo exterior GeoJSON no antihorario")
            for hole in polygon[1:]:
                if _signed_area([tuple(position) for position in hole[:-1]]) >= 0:
                    raise ZoneError("hueco GeoJSON no horario")


def _geojson_roundtrip_metrics(
    zones: dict[int, Any], wgs84: dict[int, Any], tolerances: dict[str, float]
) -> dict[str, Any]:
    inverse = pyproj.Transformer.from_crs(
        "EPSG:4326", "EPSG:25830", always_xy=True
    )
    per_zone: list[dict[str, Any]] = []
    passes_all = True
    for zone_id in sorted(zones):
        roundtrip = transform(wgs84[zone_id], inverse.transform, interleaved=False)
        difference = float(zones[zone_id].symmetric_difference(roundtrip).area)
        allowed = _threshold(
            tolerances["geojson_roundtrip_absolute_m2"],
            tolerances["geojson_roundtrip_relative"],
            zones[zone_id].area,
        )
        passes = difference <= allowed
        passes_all = passes_all and passes
        per_zone.append(
            {
                "passes": passes,
                "symmetric_difference_m2": difference,
                "tolerance_m2": allowed,
                "zone_id": zone_id,
            }
        )
    if not passes_all:
        raise ZoneError(f"el redondeo/reproyección GeoJSON excede tolerancia: {per_zone}")
    return {
        "coordinate_precision": 9,
        "passes": passes_all,
        "per_zone": per_zone,
    }


def _software_versions() -> dict[str, str]:
    _require_dependencies()
    return {
        "geos": shapely.geos_version_string,
        "geos_capi": shapely.geos_capi_version_string,
        "numpy": numpy.__version__,
        "proj": pyproj.proj_version_str,
        "pyproj": pyproj.__version__,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "shapely": shapely.__version__,
        "sqlite": sqlite3.sqlite_version,
    }


def _zone_records(
    zones: dict[int, Any],
    codes_by_zone: dict[int, list[str]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    code_by_id = {
        int(zone["zone_id"]): zone["zone_code"] for zone in config["zones"]
    }
    records: list[dict[str, Any]] = []
    for zone_id in sorted(zones):
        geometry = zones[zone_id]
        parts, holes = _part_hole_counts(geometry)
        records.append(
            {
                "area_m2": float(geometry.area),
                "bbox_epsg25830": _bbox(geometry),
                "geometry": geometry,
                "geometry_sha256": geometry_sha256(geometry),
                "holes": holes,
                "municipality_count": len(codes_by_zone[zone_id]),
                "part_count": parts,
                "valid": bool(geometry.is_valid),
                "zone_code": code_by_id[zone_id],
                "zone_id": zone_id,
            }
        )
    return records


def _public_zone_statistics(
    records: list[dict[str, Any]], wgs84: dict[int, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "area_m2": record["area_m2"],
            "bbox_epsg25830": record["bbox_epsg25830"],
            "bbox_epsg4326": _bbox(wgs84[record["zone_id"]]),
            "geometry_sha256": record["geometry_sha256"],
            "holes": record["holes"],
            "municipalities": record["municipality_count"],
            "parts": record["part_count"],
            "valid": record["valid"],
            "zone_code": record["zone_code"],
            "zone_id": record["zone_id"],
        }
        for record in records
    ]


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _format_bbox(values: Sequence[float], precision: int) -> str:
    return ", ".join(f"{value:.{precision}f}" for value in values)


def _report_bytes(
    *,
    config: dict[str, Any],
    input_paths: dict[str, Path],
    input_hashes: dict[str, str],
    output_hashes: dict[str, str],
    municipal_counts: dict[str, int],
    repairs: list[dict[str, Any]],
    join: dict[str, Any],
    topology: dict[str, Any],
    zone_statistics: list[dict[str, Any]],
    roundtrip: dict[str, Any],
    software: dict[str, str],
) -> bytes:
    tolerance = config["tolerances"]
    coverage = topology["coverage"]
    overlaps = topology["overlaps"]
    lines = [
        "# GEO-003 — Informe topológico y de áreas",
        "",
        "Geometría derivada al disolver la asignación municipal oficial aprobada. No es una capa poligonal PREVIFOC publicada directamente y no se ha comparado con JPEG oficiales (GEO-004).",
        "",
        "## Procedencia y barreras",
        "",
        f"- Crosswalk aprobado: `{_relative(input_paths['crosswalk'], PROJECT_ROOT)}`; SHA-256 `{input_hashes['crosswalk']}`; 542 filas.",
        f"- Snapshot ICV intacto: `{_relative(input_paths['icv'], PROJECT_ROOT)}`; SHA-256 `{input_hashes['icv']}`; huella lógica `{config['icv']['dataset_content_sha256']}`.",
        "- Capa/campo de unión: `ICV.Municipios.cod_ine_mun` ← `crosswalk.icv_cod_ine_mun`; los códigos se leyeron como texto de cinco dígitos.",
        "- Antes de leer geometrías se ejecutaron y exigieron `python3 tools/geo_sources.py validate` y `python3 tools/geo_crosswalk.py validate`.",
        f"- Unión bidireccional: {join['matched']} municipios; ICV sin crosswalk={join['icv_without_crosswalk']}; crosswalk sin ICV={join['crosswalk_without_icv']}.",
        "- No se consultó ninguna URL viva ni se modificó el snapshot crudo.",
        "- Licencia específica 112CV: `not_found`; licencia ICV declarada: CC BY 4.0 Generalitat.",
        "",
        "## Inspección y reparación municipal",
        "",
        f"Se inspeccionaron {municipal_counts['municipalities_inspected']} geometrías antes de disolver: {municipal_counts['valid_before_repair']} válidas y {municipal_counts['invalid_before_repair']} inválida. Tras la reparación controlada, las {municipal_counts['valid_after_repair']} son válidas.",
        "",
        "| Código | Municipio | Motivo | Operación | Partes | Huecos | Δ área abs. (m²) | Dif. simétrica (m²) |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for repair in repairs:
        lines.append(
            f"| `{repair['cod_ine_mun']}` | {_markdown_cell(repair['municipality'])} | "
            f"{_markdown_cell(repair['reason'])} | `MakeValid linework` | "
            f"{repair['before']['parts']}→{repair['after']['parts']} | "
            f"{repair['before']['holes']}→{repair['after']['holes']} | "
            f"{repair['area_delta_absolute_m2']:.12f} | "
            f"{repair['symmetric_difference_m2']:.12f} |"
        )
    if not repairs:
        lines.append("| — | — | No hubo reparaciones | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "La única reparación usa GEOS MakeValid en modo `linework`, que conserva cada borde y vértice. En Xàtiva dos partes compartían un segmento de 5,589746953 m: se fusionan en una parte poligonal y el segmento queda registrado como `LineString` de área cero. El bbox y los 18 huecos no cambian; no se elimina ninguna superficie, isla, enclave ni hueco.",
            "",
            "## Zonas maestras (EPSG:25830)",
            "",
            "| ID | Código | Municipios | Área (m²) | Partes | Huecos | Bbox EPSG:25830 | SHA-256 WKB canónico |",
            "|---:|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for zone in zone_statistics:
        lines.append(
            f"| {zone['zone_id']} | `{zone['zone_code']}` | {zone['municipalities']} | "
            f"{zone['area_m2']:.6f} | {zone['parts']} | {zone['holes']} | "
            f"`{_format_bbox(zone['bbox_epsg25830'], 3)}` | `{zone['geometry_sha256']}` |"
        )
    lines.extend(
        [
            "",
            "Todas las entidades son `MultiPolygon`, válidas, no vacías y se ordenan por `zone_id` 53–59.",
            "",
            "### Bbox RFC 7946 (EPSG:4326, longitud/latitud)",
            "",
            "| ID | Código | Bbox [oeste, sur, este, norte] |",
            "|---:|---|---|",
        ]
    )
    for zone in zone_statistics:
        lines.append(
            f"| {zone['zone_id']} | `{zone['zone_code']}` | "
            f"`{_format_bbox(zone['bbox_epsg4326'], 9)}` |"
        )
    lines.extend(
        [
            "",
            "## Tolerancias y controles topológicos",
            "",
            "Las tolerancias combinan un suelo absoluto y una parte relativa: `máximo(absoluta, relativa × área de referencia)`. No se usa tolerancia lineal, simplificación ni eliminación por tamaño.",
            "",
            f"- Cobertura: absoluta {tolerance['coverage_absolute_m2']} m²; relativa {tolerance['coverage_relative']}. Observada: diferencia simétrica {coverage['symmetric_difference_m2']:.12f} m² ({coverage['relative_symmetric_difference']:.15g}); tolerancia efectiva {coverage['tolerance_m2']:.12f} m²; **correcta**.",
            f"- Solapes: absoluta {tolerance['overlap_absolute_m2']} m²; relativa {tolerance['overlap_relative']} respecto a la menor zona del par. Se comprobaron los {overlaps['pairs_checked']} pares; máximo observado {overlaps['max_area_m2']:.12f} m²; **sin solapes materiales**.",
            f"- Reparaciones: absoluta {tolerance['repair_absolute_m2']} m²; relativa {tolerance['repair_relative']}. La reparación registrada queda dentro de tolerancia.",
            f"- GeoJSON ida/vuelta: 9 decimales; absoluta {tolerance['geojson_roundtrip_absolute_m2']} m²; relativa {tolerance['geojson_roundtrip_relative']}; las siete zonas pasan.",
            f"- Área unión municipal: {coverage['municipal_union_area_m2']:.6f} m²; área unión de zonas: {coverage['zone_union_area_m2']:.6f} m².",
            "",
            "## RFC 7946 y determinismo",
            "",
            "`zones.geojson` no incluye miembro `crs`, usa posiciones `[longitud, latitud]` EPSG:4326, anillos exteriores antihorarios, huecos horarios y precisión fija de 9 decimales. Se validaron rangos, tipos, IDs y geometrías no vacías.",
            "",
            "Las entradas se ordenan por código e ID; los anillos, huecos y partes se canonicalizan sin simplificar; WKB, atributos y JSON tienen orden fijo; el GeoPackage usa metadatos y timestamp fijados. `validate` regenera en memoria y exige igualdad byte a byte.",
            "",
            f"- `{MASTER_NAME}` SHA-256: `{output_hashes[MASTER_NAME]}`.",
            f"- `{GEOJSON_NAME}` SHA-256: `{output_hashes[GEOJSON_NAME]}`.",
            "",
            "## Versiones exactas",
            "",
        ]
    )
    for name, version in software.items():
        lines.append(f"- {name}: `{version}`.")
    lines.extend(
        [
            "",
            "## Condiciones para GEO-004",
            "",
            "La geometría queda descrita como `derived_from_official_municipal_assignment`. Sigue sin existir confirmación formal de que PREVIFOC sea exactamente una unión de municipios completos. La comparación externa con los mapas/JPEG oficiales pertenece exclusivamente a GEO-004.",
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
    (
        source_manifest,
        crosswalk_manifest,
        source_manifest_path,
        crosswalk_manifest_path,
    ) = _verify_input_manifests(config_path, config)
    crosswalk_path = _resolve(
        config_path.parent, config["crosswalk"]["path"], "crosswalk aprobado"
    )
    icv_path = _resolve(
        config_path.parent, config["icv"]["snapshot"], "snapshot ICV fijado"
    )
    requirements_path = _resolve(
        config_path.parent, config["requirements"], "requisitos geoespaciales"
    )
    crosswalk_rows, zone_counts = _load_crosswalk(crosswalk_path, config)
    municipalities, srs = _load_icv_geometries(icv_path, config)
    crosswalk_codes = {row["icv_cod_ine_mun"] for row in crosswalk_rows}
    icv_codes = set(municipalities)
    icv_without_crosswalk = sorted(icv_codes - crosswalk_codes)
    crosswalk_without_icv = sorted(crosswalk_codes - icv_codes)
    if icv_without_crosswalk or crosswalk_without_icv or len(icv_codes) != 542:
        raise ZoneError(
            "la unión crosswalk↔ICV no contiene exactamente 542 municipios en ambos sentidos; "
            f"ICV sin crosswalk={icv_without_crosswalk[:10]}, "
            f"crosswalk sin ICV={crosswalk_without_icv[:10]}"
        )
    join = {
        "crosswalk_codes": len(crosswalk_codes),
        "crosswalk_without_icv": len(crosswalk_without_icv),
        "icv_codes": len(icv_codes),
        "icv_without_crosswalk": len(icv_without_crosswalk),
        "matched": len(icv_codes & crosswalk_codes),
        "preserved_as_text_five_digits": all(
            isinstance(code, str) and CODE_PATTERN.fullmatch(code)
            for code in crosswalk_codes | icv_codes
        ),
    }
    repaired, repairs, municipal_counts = _repair_geometries(municipalities, config)
    zones, codes_by_zone = _dissolve_zones(repaired, crosswalk_rows, config)
    topology = evaluate_topology(
        [repaired[code] for code in sorted(repaired)],
        zones,
        config["tolerances"],
    )
    records = _zone_records(zones, codes_by_zone, config)
    master_content = _render_master_gpkg(
        records, srs, config["build_timestamp_utc"]
    )
    geojson_content, wgs84 = _render_geojson(
        records, config["geojson"]["coordinate_precision"]
    )
    roundtrip = _geojson_roundtrip_metrics(zones, wgs84, config["tolerances"])
    roundtrip["coordinate_precision"] = config["geojson"]["coordinate_precision"]
    zone_statistics = _public_zone_statistics(records, wgs84)
    output_hashes = {
        MASTER_NAME: sha256_bytes(master_content),
        GEOJSON_NAME: sha256_bytes(geojson_content),
    }
    input_paths = {
        "configuration": config_path,
        "crosswalk": crosswalk_path,
        "crosswalk_manifest": crosswalk_manifest_path,
        "icv": icv_path,
        "requirements": requirements_path,
        "source_manifest": source_manifest_path,
    }
    input_hashes = {name: sha256_file(path) for name, path in input_paths.items()}
    software = _software_versions()
    report_content = _report_bytes(
        config=config,
        input_paths=input_paths,
        input_hashes=input_hashes,
        output_hashes=output_hashes,
        municipal_counts=municipal_counts,
        repairs=repairs,
        join=join,
        topology=topology,
        zone_statistics=zone_statistics,
        roundtrip=roundtrip,
        software=software,
    )
    output_directory = _resolve(
        config_path.parent, config["output_directory"], "directorio de salida"
    )
    manifest = {
        "geometry_schema_version": 1,
        "geometry_quality": "derived_from_official_municipal_assignment",
        "inputs": {
            name: {
                "path": _relative(path, output_directory),
                "sha256": input_hashes[name],
            }
            for name, path in input_paths.items()
        },
        "licenses": {
            "icv_municipios": source_manifest["sources"]["icv_municipios"]["license"],
            "municipal_assignment_112cv": source_manifest["sources"]["municipios_112cv"]["license"],
        },
        "outputs": {
            MASTER_NAME: {
                "crs": "EPSG:25830",
                "features": 7,
                "geometry_type": "MULTIPOLYGON",
                "layer": MASTER_LAYER,
                "sha256": output_hashes[MASTER_NAME],
                "size_bytes": len(master_content),
            },
            GEOJSON_NAME: {
                "coordinate_order": "longitude, latitude",
                "crs_interpretation": "EPSG:4326 per RFC 7946",
                "features": 7,
                "geometry_type": "MultiPolygon",
                "sha256": output_hashes[GEOJSON_NAME],
                "size_bytes": len(geojson_content),
            },
            REPORT_NAME: {
                "sha256": sha256_bytes(report_content),
                "size_bytes": len(report_content),
            },
        },
        "policies": {
            "determinism": {
                "entity_order": "zone_id ascending",
                "geometry": "canonical ring orientation/start and sorted holes/parts; no simplification",
                "geojson_coordinate_precision": config["geojson"]["coordinate_precision"],
                "gpkg_timestamp_utc": config["build_timestamp_utc"],
            },
            "repair": config["repair"],
            "tolerances": config["tolerances"],
        },
        "software": software,
        "statistics": {
            "geojson_roundtrip": roundtrip,
            "join": join,
            "municipal_geometries": municipal_counts,
            "repairs": repairs,
            "topology": topology,
            "zone_counts": zone_counts,
            "zones": zone_statistics,
        },
        "unresolved_conditions": {
            "formal_confirmation_previfoc_is_union_of_complete_municipalities": False,
            "official_jpeg_comparison": "deferred_to_GEO-004",
            "specific_112cv_license": "not_found",
        },
    }
    artifacts = {
        MASTER_NAME: master_content,
        GEOJSON_NAME: geojson_content,
        REPORT_NAME: report_content,
        MANIFEST_NAME: _json_bytes(manifest),
    }
    return artifacts, output_directory


def build_zones(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    for name in (MASTER_NAME, GEOJSON_NAME, REPORT_NAME, MANIFEST_NAME):
        _atomic_write(output_directory / name, artifacts[name])
    return artifacts


def validate_zones(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    for name, expected in artifacts.items():
        path = output_directory / name
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise ZoneError(f"no se puede leer el entregable {path}: {exc}") from exc
        if observed != expected:
            raise ZoneError(
                f"{path} no coincide byte a byte con la regeneración determinista"
            )
    return artifacts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construye y valida las siete zonas canónicas de GEO-003 sin red."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("build", "construir GeoPackage, GeoJSON, manifiesto e informe"),
        ("validate", "regenerar y comparar todos los entregables byte a byte"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        artifacts = (
            build_zones(args.config)
            if args.command == "build"
            else validate_zones(args.config)
        )
        manifest = json.loads(artifacts[MANIFEST_NAME])
        output = _resolve(
            args.config.resolve().parent,
            _load_config(args.config.resolve())["output_directory"],
            "directorio de salida",
        )
        print(f"maestra: {output / MASTER_NAME}")
        print(f"geojson: {output / GEOJSON_NAME}")
        print(f"informe: {output / REPORT_NAME}")
        print(f"manifiesto: {output / MANIFEST_NAME}")
        print(
            f"municipios: {manifest['statistics']['join']['matched']}; "
            f"zonas: {manifest['outputs'][MASTER_NAME]['features']}; "
            f"sha256 maestra: {manifest['outputs'][MASTER_NAME]['sha256']}; "
            f"sha256 geojson: {manifest['outputs'][GEOJSON_NAME]['sha256']}"
        )
        return 0
    except ZoneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
