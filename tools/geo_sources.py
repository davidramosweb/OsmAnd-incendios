#!/usr/bin/env python3
"""Descarga, valida y fija las dos fuentes geograficas de GEO-001.

Solo usa la biblioteca estandar de Python. La promocion es transaccional respecto
al manifiesto: primero descarga y valida ambas fuentes en un directorio temporal,
despues conserva los cuerpos por su SHA-256 y finalmente reemplaza el manifiesto.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import time
from typing import Any, Iterable
import urllib.error
import urllib.parse
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "geo_sources.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "sources"
MANIFEST_NAME = "manifest.json"
REPORT_NAME = "REPORT.md"
RELEVANT_HEADERS = (
    "Content-Type",
    "Content-Length",
    "Content-Disposition",
    "Date",
    "ETag",
    "Last-Modified",
    "Cache-Control",
    "Expires",
    "Pragma",
    "Retry-After",
    "Vary",
)


class GeoSourcesError(RuntimeError):
    """Error esperado y apto para mostrar desde la linea de comandos."""


class DownloadError(GeoSourcesError):
    """Fallo HTTP, de red, de timeout o de tamano."""


class ValidationError(GeoSourcesError):
    """El cuerpo recibido no cumple el contrato de la fuente."""


def _utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def _load_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"no se puede leer la configuracion {path}: {exc}") from exc
    if config.get("schema_version") != 1:
        raise ValidationError("schema_version de configuracion no soportada")
    sources = config.get("sources")
    if not isinstance(sources, dict) or set(sources) != {
        "municipios_112cv",
        "icv_municipios",
    }:
        raise ValidationError(
            "la configuracion debe contener solo municipios_112cv e icv_municipios"
        )
    client = config.get("client")
    if not isinstance(client, dict) or not client.get("user_agent"):
        raise ValidationError("falta client.user_agent para identificar la descarga")
    return config


def _selected_headers(headers: Any) -> dict[str, str]:
    selected: dict[str, str] = {}
    for name in RELEVANT_HEADERS:
        values = headers.get_all(name, [])
        if values:
            selected[name.lower()] = ", ".join(values)
    return selected


def _download_one(
    source_id: str,
    source: dict[str, Any],
    target: Path,
    user_agent: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        source["url"],
        headers={
            "Accept": source["accept"],
            "User-Agent": user_agent,
        },
        method="GET",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise DownloadError(f"{source_id}: HTTP inesperado {status}")
            content_length = response.headers.get("Content-Length")
            max_bytes = int(source["max_bytes"])
            if content_length:
                try:
                    advertised_size = int(content_length)
                except ValueError as exc:
                    raise DownloadError(
                        f"{source_id}: Content-Length no numerico: {content_length!r}"
                    ) from exc
                if advertised_size > max_bytes:
                    raise DownloadError(
                        f"{source_id}: Content-Length {advertised_size} supera "
                        f"el limite {max_bytes}"
                    )

            size = 0
            with target.open("wb") as stream:
                while True:
                    if time.monotonic() - started > timeout_seconds:
                        raise DownloadError(
                            f"{source_id}: timeout total de {timeout_seconds:g} s"
                        )
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise DownloadError(
                            f"{source_id}: respuesta supera el limite {max_bytes} bytes"
                        )
                    stream.write(chunk)
            if size == 0:
                raise DownloadError(f"{source_id}: respuesta vacia")
            return {
                "final_url": response.geturl(),
                "http_status": status,
                "response_headers": _selected_headers(response.headers),
                "retrieved_at_utc": _utc_now(),
                "size_bytes": size,
            }
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        detail = f"; Retry-After={retry_after}" if retry_after else ""
        exc.close()
        raise DownloadError(
            f"{source_id}: HTTP {exc.code} {exc.reason}{detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"{source_id}: error de red: {exc.reason}") from exc
    except TimeoutError as exc:
        raise DownloadError(
            f"{source_id}: timeout de {timeout_seconds:g} s"
        ) from exc
    except OSError as exc:
        raise DownloadError(f"{source_id}: error de E/S: {exc}") from exc


def _content_type(metadata: dict[str, Any]) -> str:
    raw = metadata.get("response_headers", {}).get("content-type", "")
    return raw.split(";", 1)[0].strip().lower()


def _require_content_type(
    source_id: str, metadata: dict[str, Any] | None, allowed: set[str]
) -> str | None:
    if metadata is None:
        return None
    observed = _content_type(metadata)
    if observed not in allowed:
        raise ValidationError(
            f"{source_id}: Content-Type inesperado {observed or '(ausente)'}; "
            f"esperado uno de {sorted(allowed)}"
        )
    return observed


def _validate_municipios(
    path: Path,
    source: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = "municipios_112cv"
    media_type = _require_content_type(source_id, metadata, {"application/json"})
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{source_id}: el JSON no es UTF-8") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{source_id}: JSON invalido: {exc}") from exc
    if not isinstance(data, list):
        raise ValidationError(f"{source_id}: la raiz JSON no es un array")

    expected = source["expected"]
    required_fields = set(expected["required_fields"])
    allowed_zones = {int(value) for value in expected["allowed_zone_ids"]}
    outside_expected = expected["outside_record"]
    names: list[str] = []
    fields: set[str] = set()
    assigned: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []

    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValidationError(f"{source_id}: fila {index} no es un objeto")
        missing = required_fields - row.keys()
        if missing:
            raise ValidationError(
                f"{source_id}: fila {index} sin campos {sorted(missing)}"
            )
        fields.update(row)
        name = row["municipio"]
        zone = row["idZonaPrevifoc"]
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(f"{source_id}: municipio vacio en fila {index}")
        if not isinstance(zone, int) or isinstance(zone, bool):
            raise ValidationError(
                f"{source_id}: idZonaPrevifoc no entero en fila {index}"
            )
        names.append(name)
        if zone in allowed_zones:
            assigned.append(row)
        elif zone == 0:
            outside.append(row)
        else:
            raise ValidationError(
                f"{source_id}: zona no permitida {zone} en {name!r}"
            )

    duplicate_names = sorted(
        name for name, count in collections.Counter(names).items() if count != 1
    )
    if duplicate_names:
        raise ValidationError(
            f"{source_id}: municipios duplicados: {duplicate_names[:5]}"
        )
    if len(assigned) != int(expected["assigned_municipalities"]):
        raise ValidationError(
            f"{source_id}: hay {len(assigned)} municipios asignados; "
            f"se esperaban {expected['assigned_municipalities']}"
        )
    if outside != [outside_expected]:
        raise ValidationError(
            f"{source_id}: el registro Fuera C.V. no coincide exactamente: {outside!r}"
        )

    zone_counts = collections.Counter(row["idZonaPrevifoc"] for row in assigned)
    expected_counts = {
        int(zone): int(count) for zone, count in expected["zone_counts"].items()
    }
    if dict(zone_counts) != expected_counts:
        raise ValidationError(
            f"{source_id}: conteos por zona {dict(sorted(zone_counts.items()))}; "
            f"esperados {dict(sorted(expected_counts.items()))}"
        )

    samples: list[dict[str, Any]] = []
    by_name = {row["municipio"]: row for row in data}
    for value in source.get("manual_sample_values", []):
        if value not in by_name:
            raise ValidationError(
                f"{source_id}: falta la muestra manual configurada {value!r}"
            )
        samples.append(by_name[value])

    canonical_rows = sorted(data, key=lambda row: row["municipio"])
    dataset_content_sha256 = hashlib.sha256(_json_bytes(canonical_rows)).hexdigest()

    return {
        "assigned_municipalities": len(assigned),
        "dataset_content_sha256": dataset_content_sha256,
        "fields": sorted(fields),
        "format": "JSON",
        "manual_samples": samples,
        "media_type": media_type,
        "outside_cv_records": len(outside),
        "rows": len(data),
        "zone_counts": {
            str(zone): zone_counts[zone] for zone in sorted(zone_counts)
        },
    }


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValidationError("identificador SQLite invalido")
    return '"' + value.replace('"', '""') + '"'


def _read_gpkg_geometry_header(blob: bytes, expected_srs_id: int) -> None:
    if len(blob) < 17 or blob[:2] != b"GP":
        raise ValidationError("icv_municipios: geometria sin cabecera GeoPackage")
    if blob[2] != 0:
        raise ValidationError(
            f"icv_municipios: version de geometria GeoPackage no soportada {blob[2]}"
        )
    flags = blob[3]
    if flags & 0x20:
        raise ValidationError("icv_municipios: geometria GeoPackage extendida inesperada")
    if flags & 0x10:
        raise ValidationError("icv_municipios: geometria marcada como vacia")
    endian = "<" if flags & 0x01 else ">"
    srs_id = struct.unpack(f"{endian}i", blob[4:8])[0]
    if srs_id != expected_srs_id:
        raise ValidationError(
            f"icv_municipios: geometria con srs_id {srs_id}; esperado {expected_srs_id}"
        )
    envelope_indicator = (flags >> 1) & 0x07
    envelope_sizes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    if envelope_indicator not in envelope_sizes:
        raise ValidationError(
            f"icv_municipios: indicador de envolvente invalido {envelope_indicator}"
        )
    wkb_offset = 8 + envelope_sizes[envelope_indicator]
    if len(blob) < wkb_offset + 9:
        raise ValidationError("icv_municipios: WKB truncado")
    wkb_endian_byte = blob[wkb_offset]
    if wkb_endian_byte not in (0, 1):
        raise ValidationError("icv_municipios: byte order WKB invalido")
    wkb_endian = "<" if wkb_endian_byte == 1 else ">"
    geometry_type = struct.unpack(
        f"{wkb_endian}I", blob[wkb_offset + 1 : wkb_offset + 5]
    )[0]
    if geometry_type % 1000 != 6:
        raise ValidationError(
            f"icv_municipios: WKB no es MULTIPOLYGON (tipo {geometry_type})"
        )
    geometry_count = struct.unpack(
        f"{wkb_endian}I", blob[wkb_offset + 5 : wkb_offset + 9]
    )[0]
    if geometry_count == 0:
        raise ValidationError("icv_municipios: MULTIPOLYGON sin poligonos")


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri_path = urllib.parse.quote(str(path.resolve()), safe="/")
    try:
        connection = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise ValidationError(f"icv_municipios: SQLite no legible: {exc}") from exc


def _validate_gpkg(
    path: Path,
    source: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = "icv_municipios"
    media_type = _require_content_type(
        source_id,
        metadata,
        {"application/geopackage+sqlite3", "application/octet-stream"},
    )
    try:
        with path.open("rb") as stream:
            signature = stream.read(16)
    except OSError as exc:
        raise ValidationError(f"{source_id}: no se puede leer {path}: {exc}") from exc
    if not signature.startswith(b"SQLite format 3\x00"):
        raise ValidationError(f"{source_id}: el cuerpo no es SQLite/GeoPackage")

    expected = source["expected"]
    layer = expected["layer"]
    quoted_layer = _quote_identifier(layer)
    expected_srs = int(expected["crs"]["organization_coordsys_id"])
    try:
        with contextlib.closing(_connect_readonly(path)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValidationError(
                    f"{source_id}: integrity_check no valido: {integrity}"
                )
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            user_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if application_id != 0x47504B47:
                raise ValidationError(
                    f"{source_id}: application_id {application_id} no es GeoPackage"
                )

            contents = connection.execute(
                "SELECT table_name, data_type, identifier, description, last_change, "
                "min_x, min_y, max_x, max_y, srs_id FROM gpkg_contents "
                "WHERE table_name = ?",
                (layer,),
            ).fetchone()
            if contents is None or contents["data_type"] != "features":
                raise ValidationError(
                    f"{source_id}: no existe la capa vectorial {layer!r}"
                )
            geometry = connection.execute(
                "SELECT table_name, column_name, geometry_type_name, srs_id, z, m "
                "FROM gpkg_geometry_columns WHERE table_name = ?",
                (layer,),
            ).fetchone()
            if geometry is None:
                raise ValidationError(
                    f"{source_id}: {layer!r} no figura en gpkg_geometry_columns"
                )
            geometry_type = geometry["geometry_type_name"].upper()
            if geometry_type != expected["geometry_type"]:
                raise ValidationError(
                    f"{source_id}: geometria {geometry_type}; "
                    f"esperada {expected['geometry_type']}"
                )
            if int(geometry["srs_id"]) != expected_srs:
                raise ValidationError(
                    f"{source_id}: srs_id {geometry['srs_id']}; esperado {expected_srs}"
                )

            crs = connection.execute(
                "SELECT srs_name, srs_id, organization, organization_coordsys_id, "
                "definition, description FROM gpkg_spatial_ref_sys WHERE srs_id = ?",
                (expected_srs,),
            ).fetchone()
            if crs is None:
                raise ValidationError(f"{source_id}: CRS {expected_srs} no declarado")
            if (
                crs["organization"] != expected["crs"]["organization"]
                or int(crs["organization_coordsys_id"]) != expected_srs
            ):
                raise ValidationError(
                    f"{source_id}: declaracion CRS inesperada: "
                    f"{crs['organization']}:{crs['organization_coordsys_id']}"
                )

            schema_rows = connection.execute(
                f"PRAGMA table_info({quoted_layer})"
            ).fetchall()
            fields = [row["name"] for row in schema_rows]
            missing_fields = set(expected["required_fields"]) - set(fields)
            if missing_fields:
                raise ValidationError(
                    f"{source_id}: faltan campos {sorted(missing_fields)}"
                )
            name_field = expected["name_field"]
            code_field = expected["code_field"]
            geometry_field = geometry["column_name"]
            count_row = connection.execute(
                f"SELECT COUNT(*) AS features, "
                f"SUM(CASE WHEN {_quote_identifier(geometry_field)} IS NULL "
                f"OR length({_quote_identifier(geometry_field)}) = 0 THEN 1 ELSE 0 END) "
                f"AS empty_blobs, "
                f"COUNT(DISTINCT {_quote_identifier(name_field)}) AS distinct_names, "
                f"SUM(CASE WHEN {_quote_identifier(name_field)} IS NULL "
                f"OR trim({_quote_identifier(name_field)}) = '' THEN 1 ELSE 0 END) "
                f"AS missing_names, "
                f"COUNT(DISTINCT {_quote_identifier(code_field)}) AS distinct_codes, "
                f"SUM(CASE WHEN {_quote_identifier(code_field)} IS NULL "
                f"OR trim({_quote_identifier(code_field)}) = '' THEN 1 ELSE 0 END) "
                f"AS missing_codes FROM {quoted_layer}"
            ).fetchone()
            feature_count = int(count_row["features"])
            if feature_count != int(expected["feature_count"]):
                raise ValidationError(
                    f"{source_id}: {feature_count} geometrias; "
                    f"se esperaban {expected['feature_count']}"
                )
            for metric in (
                "empty_blobs",
                "missing_names",
                "missing_codes",
            ):
                if int(count_row[metric] or 0) != 0:
                    raise ValidationError(
                        f"{source_id}: metrica {metric} = {count_row[metric]}"
                    )
            if int(count_row["distinct_names"]) != feature_count:
                raise ValidationError(f"{source_id}: nombres municipales no unicos")
            if int(count_row["distinct_codes"]) != feature_count:
                raise ValidationError(f"{source_id}: codigos municipales no unicos")

            geometry_query = (
                f"SELECT {_quote_identifier(geometry_field)} FROM {quoted_layer}"
            )
            for row in connection.execute(geometry_query):
                blob = row[0]
                if not isinstance(blob, bytes):
                    raise ValidationError(
                        f"{source_id}: valor geometrico no binario"
                    )
                _read_gpkg_geometry_header(blob, expected_srs)

            manual_field = source.get("manual_sample_field")
            samples: list[dict[str, Any]] = []
            if manual_field and source.get("manual_sample_values"):
                if manual_field not in fields:
                    raise ValidationError(
                        f"{source_id}: campo de muestra {manual_field!r} ausente"
                    )
                sample_fields = [
                    field
                    for field in (
                        code_field,
                        name_field,
                        "nom_mun_cas",
                        "nom_mun_val",
                        manual_field,
                    )
                    if field in fields
                ]
                for value in source["manual_sample_values"]:
                    result = connection.execute(
                        f"SELECT {', '.join(_quote_identifier(f) for f in sample_fields)} "
                        f"FROM {quoted_layer} WHERE {_quote_identifier(manual_field)} = ?",
                        (value,),
                    ).fetchall()
                    if len(result) != 1:
                        raise ValidationError(
                            f"{source_id}: la muestra {value!r} produce {len(result)} filas"
                        )
                    samples.append(dict(result[0]))

            semantic_fields = [field for field in fields if field != "fid"]
            content_digest = hashlib.sha256()
            content_digest.update(
                _json_bytes(
                    {
                        "crs": dict(crs),
                        "fields": [
                            {
                                "name": row["name"],
                                "type": row["type"],
                            }
                            for row in schema_rows
                            if row["name"] != "fid"
                        ],
                        "geometry_column": geometry_field,
                        "geometry_type": geometry_type,
                        "layer": layer,
                    }
                )
            )
            semantic_query = (
                f"SELECT {', '.join(_quote_identifier(field) for field in semantic_fields)} "
                f"FROM {quoted_layer} ORDER BY {_quote_identifier(code_field)}"
            )
            for semantic_row in connection.execute(semantic_query):
                normalized_values: list[Any] = []
                for value in semantic_row:
                    if isinstance(value, bytes):
                        normalized_values.append(
                            {
                                "sha256": hashlib.sha256(value).hexdigest(),
                                "size_bytes": len(value),
                            }
                        )
                    else:
                        normalized_values.append(value)
                content_digest.update(_json_bytes(normalized_values))

            return {
                "application_id": application_id,
                "code_field": code_field,
                "crs": dict(crs),
                "dataset_content_sha256": content_digest.hexdigest(),
                "feature_count": feature_count,
                "fields": [
                    {
                        "name": row["name"],
                        "nullable": not bool(row["notnull"]),
                        "primary_key": bool(row["pk"]),
                        "type": row["type"],
                    }
                    for row in schema_rows
                ],
                "format": "OGC GeoPackage",
                "geometry_column": geometry_field,
                "geometry_type": geometry_type,
                "integrity_check": integrity,
                "layer": layer,
                "layer_bounds": {
                    "max_x": contents["max_x"],
                    "max_y": contents["max_y"],
                    "min_x": contents["min_x"],
                    "min_y": contents["min_y"],
                },
                "layer_last_change": contents["last_change"],
                "manual_samples": samples,
                "media_type": media_type,
                "name_field": name_field,
                "non_empty_geometries": feature_count,
                "user_version": user_version,
            }
    except sqlite3.Error as exc:
        raise ValidationError(f"{source_id}: GeoPackage inesperado: {exc}") from exc


def _validate_source(
    path: Path,
    source: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if source["kind"] == "municipios_json":
        return _validate_municipios(path, source, metadata)
    if source["kind"] == "geopackage":
        return _validate_gpkg(path, source, metadata)
    raise ValidationError(f"tipo de fuente no soportado: {source.get('kind')!r}")


def _source_record(
    source_id: str,
    source: dict[str, Any],
    metadata: dict[str, Any],
    inspection: dict[str, Any],
    digest: str,
    snapshot_path: str,
    user_agent: str,
) -> dict[str, Any]:
    return {
        "catalog_url": source.get("catalog_url"),
        "final_url": metadata["final_url"],
        "format": inspection["format"],
        "http": {
            "response_headers": metadata["response_headers"],
            "status": metadata["http_status"],
        },
        "inspection": inspection,
        "license": source["license"],
        "publisher": source["publisher"],
        "request": {
            "accept": source["accept"],
            "user_agent": user_agent,
        },
        "retrieved_at_utc": metadata["retrieved_at_utc"],
        "sha256": digest,
        "size_bytes": metadata["size_bytes"],
        "snapshot": snapshot_path,
        "source_id": source_id,
        "url": source["url"],
    }


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report_markdown(manifest: dict[str, Any]) -> str:
    municipios = manifest["sources"]["municipios_112cv"]
    icv = manifest["sources"]["icv_municipios"]
    mi = municipios["inspection"]
    gi = icv["inspection"]
    lines = [
        "# GEO-001 — Informe de fuentes fijadas",
        "",
        f"Generado en UTC: `{manifest['created_at_utc']}`.",
        "",
        "Este informe inspecciona las dos entradas por separado. No crea un crosswalk, no une nombres y no genera zonas.",
        "",
        "## Snapshots",
        "",
        "| Fuente | Cuerpo original | SHA-256 | Recuperación UTC |",
        "|---|---|---|---|",
        f"| 112CV municipios | `{municipios['snapshot']}` | `{municipios['sha256']}` | `{municipios['retrieved_at_utc']}` |",
        f"| ICV municipios | `{icv['snapshot']}` | `{icv['sha256']}` | `{icv['retrieved_at_utc']}` |",
        "",
        "La columna SHA-256 anterior identifica los bytes originales. La huella lógica determinista de cada dataset, independiente del orden del JSON y del `last_change` que el WFS inserta al generar cada GPKG, es:",
        "",
        f"- 112CV: `{mi['dataset_content_sha256']}`.",
        f"- ICV: `{gi['dataset_content_sha256']}`.",
        "",
        "## 112CV `municipios`",
        "",
        f"- Formato observado: {mi['format']} (`{mi['media_type']}`).",
        f"- Filas: {mi['rows']}; municipios asignados: {mi['assigned_municipalities']}; registros `Fuera C.V.`: {mi['outside_cv_records']}.",
        f"- Campos: {', '.join(f'`{field}`' for field in mi['fields'])}.",
        "- Conteos por `idZonaPrevifoc`: "
        + ", ".join(f"{zone}={count}" for zone, count in mi["zone_counts"].items())
        + ".",
        f"- Licencia: {municipios['license']['status']}; "
        f"{municipios['license'].get('note', 'sin nota adicional')}",
        "",
        "### Muestras observadas (112CV)",
        "",
        "| municipio | idZonaPrevifoc | idZonaAvisoMeteo | idZonaEmergencia |",
        "|---|---:|---:|---:|",
    ]
    for sample in mi["manual_samples"]:
        lines.append(
            "| {municipio} | {idZonaPrevifoc} | {idZonaAvisoMeteo} | {idZonaEmergencia} |".format(
                **{key: _markdown_cell(value) for key, value in sample.items()}
            )
        )
    lines.extend(
        [
            "",
            "## ICV `ICV.Municipios`",
            "",
            f"- Formato observado: {gi['format']} (`{gi['media_type']}`).",
            f"- Capa: `{gi['layer']}`; geometría: `{gi['geometry_type']}` en `{gi['geometry_column']}`.",
            f"- Geometrías: {gi['feature_count']}; no vacías: {gi['non_empty_geometries']}; `integrity_check`: `{gi['integrity_check']}`.",
            f"- Campo de nombre seleccionado: `{gi['name_field']}`; código municipal oficial: `{gi['code_field']}`.",
            f"- CRS declarado dentro del GPKG: `{gi['crs']['organization']}:{gi['crs']['organization_coordsys_id']}` — {gi['crs']['srs_name']}.",
            f"- Licencia declarada: `{icv['license'].get('declared_license')}`. "
            f"Atribución: {icv['license'].get('attribution', 'no indicada en este fixture')}",
            "",
            "### Campos observados (ICV)",
            "",
            "| Campo | Tipo | Nulo permitido | Clave primaria |",
            "|---|---|---|---|",
        ]
    )
    for field in gi["fields"]:
        lines.append(
            f"| `{_markdown_cell(field['name'])}` | `{_markdown_cell(field['type'])}` | "
            f"{'sí' if field['nullable'] else 'no'} | "
            f"{'sí' if field['primary_key'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "### Muestras observadas (ICV)",
            "",
            "Estas filas son una inspección independiente y no constituyen correspondencias aprobadas para GEO-002.",
            "",
            "| cod_ine_mun | nom_mun | nom_mun_cas | nom_mun_val | noms_mun |",
            "|---|---|---|---|---|",
        ]
    )
    for sample in gi["manual_samples"]:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(sample.get(field, ""))
                for field in (
                    "cod_ine_mun",
                    "nom_mun",
                    "nom_mun_cas",
                    "nom_mun_val",
                    "noms_mun",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Observaciones para GEO-002",
            "",
            "- Consumir exclusivamente las rutas y hashes del manifiesto, no una URL viva.",
            "- El JSON 112CV no contiene código INE; los nombres no deben unirse por igualdad ni similitud sin una tabla revisada.",
            "- El ICV ofrece nombres en varias formas y `cod_ine_mun`; GEO-002 debe decidir y revisar cada correspondencia.",
            "- La licencia específica de los datos 112CV sigue sin estar publicada o verificada.",
            "- El WFS del ICV genera un `gpkg_contents.last_change` nuevo en cada petición. Por ello dos descargas con las mismas entidades pueden tener distinto SHA-256 crudo; `inspection.dataset_content_sha256` permite comprobar la igualdad lógica sin alterar ni normalizar el snapshot original.",
            "",
        ]
    )
    return "\n".join(lines)


def download_sources(
    config_path: Path,
    output_root: Path,
    *,
    timeout_override: float | None = None,
    user_agent_override: str | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    output_root = output_root.resolve()
    config = _load_config(config_path)
    user_agent = user_agent_override or config["client"]["user_agent"]
    timeout_seconds = (
        timeout_override
        if timeout_override is not None
        else float(config["client"]["timeout_seconds"])
    )
    if timeout_seconds <= 0:
        raise ValidationError("el timeout debe ser mayor que cero")
    if not user_agent.strip():
        raise ValidationError("el User-Agent no puede estar vacio")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staged: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(
        prefix=".geo-sources-", dir=output_root.parent
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        for source_id, source in config["sources"].items():
            extension = source["file_extension"]
            temporary_path = temporary_root / f"{source_id}.{extension}"
            metadata = _download_one(
                source_id,
                source,
                temporary_path,
                user_agent,
                timeout_seconds,
            )
            inspection = _validate_source(temporary_path, source, metadata)
            digest = sha256_file(temporary_path)
            staged[source_id] = {
                "digest": digest,
                "inspection": inspection,
                "metadata": metadata,
                "path": temporary_path,
            }

        source_records: dict[str, Any] = {}
        output_root.mkdir(parents=True, exist_ok=True)
        for source_id, source in config["sources"].items():
            item = staged[source_id]
            extension = source["file_extension"]
            relative_snapshot = Path("snapshots") / source_id / (
                f"{item['digest']}.{extension}"
            )
            final_snapshot = output_root / relative_snapshot
            final_snapshot.parent.mkdir(parents=True, exist_ok=True)
            if final_snapshot.exists():
                existing_digest = sha256_file(final_snapshot)
                if existing_digest != item["digest"]:
                    raise ValidationError(
                        f"colision de snapshot en {final_snapshot}: "
                        f"{existing_digest} != {item['digest']}"
                    )
            else:
                os.replace(item["path"], final_snapshot)
            if not final_snapshot.is_file():
                raise ValidationError(
                    f"no se ha podido promover el snapshot {final_snapshot}"
                )
            promoted_digest = sha256_file(final_snapshot)
            if promoted_digest != item["digest"]:
                raise ValidationError(
                    f"hash tras promocion incorrecto en {final_snapshot}: "
                    f"{promoted_digest} != {item['digest']}"
                )
            source_records[source_id] = _source_record(
                source_id,
                source,
                item["metadata"],
                item["inspection"],
                item["digest"],
                relative_snapshot.as_posix(),
                user_agent,
            )

        manifest = {
            "config": os.path.relpath(config_path, output_root),
            "config_sha256": sha256_file(config_path),
            "created_at_utc": _utc_now(),
            "manifest_schema_version": 1,
            "sources": source_records,
        }
        # El manifiesto se promociona al final. Si cualquier descarga o validacion
        # anterior falla, el manifiesto y sus snapshots referenciados quedan intactos.
        _atomic_write(output_root / REPORT_NAME, _report_markdown(manifest).encode("utf-8"))
        _atomic_write(output_root / MANIFEST_NAME, _json_bytes(manifest))
        return manifest


def _safe_snapshot_path(output_root: Path, relative: str) -> Path:
    candidate = (output_root / relative).resolve()
    try:
        candidate.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValidationError(f"ruta de snapshot fuera del directorio: {relative!r}") from exc
    return candidate


def validate_manifest(config_path: Path, manifest_path: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    manifest_path = manifest_path.resolve()
    config = _load_config(config_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"no se puede leer {manifest_path}: {exc}") from exc
    if manifest.get("manifest_schema_version") != 1:
        raise ValidationError("version de manifiesto no soportada")
    config_digest = sha256_file(config_path)
    if manifest.get("config_sha256") != config_digest:
        raise ValidationError(
            f"el hash de configuracion del manifiesto no coincide: "
            f"{manifest.get('config_sha256')} != {config_digest}"
        )
    output_root = manifest_path.parent
    records = manifest.get("sources", {})
    if set(records) != set(config["sources"]):
        raise ValidationError("las fuentes del manifiesto no coinciden con la configuracion")
    for source_id, source in config["sources"].items():
        record = records[source_id]
        snapshot = _safe_snapshot_path(output_root, record["snapshot"])
        if not snapshot.is_file():
            raise ValidationError(f"falta snapshot {snapshot}")
        observed_digest = sha256_file(snapshot)
        if observed_digest != record["sha256"]:
            raise ValidationError(
                f"hash incorrecto para {source_id}: {observed_digest} != {record['sha256']}"
            )
        if snapshot.stat().st_size != int(record["size_bytes"]):
            raise ValidationError(f"tamano incorrecto para {source_id}")
        inspection = _validate_source(snapshot, source)
        expected_inspection = dict(record["inspection"])
        # El media type procede de HTTP y no esta disponible al revalidar offline.
        inspection["media_type"] = expected_inspection.get("media_type")
        if inspection != expected_inspection:
            raise ValidationError(
                f"la inspeccion offline de {source_id} no coincide con el manifiesto"
            )
    return manifest


def _print_summary(manifest: dict[str, Any], output_root: Path) -> None:
    print(f"manifiesto: {output_root / MANIFEST_NAME}")
    print(f"informe: {output_root / REPORT_NAME}")
    for source_id, record in manifest["sources"].items():
        print(f"{source_id}: {record['sha256']}  {record['snapshot']}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Descarga y valida las fuentes oficiales fijadas por GEO-001."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    download = subparsers.add_parser(
        "download", help="descargar ambas fuentes y promoverlas solo si son validas"
    )
    download.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    download.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    download.add_argument("--timeout", type=float)
    download.add_argument("--user-agent")
    validate = subparsers.add_parser(
        "validate", help="revalidar sin red los snapshots del manifiesto"
    )
    validate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate.add_argument(
        "--manifest", type=Path, default=DEFAULT_OUTPUT / MANIFEST_NAME
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "download":
            manifest = download_sources(
                args.config,
                args.output,
                timeout_override=args.timeout,
                user_agent_override=args.user_agent,
            )
            _print_summary(manifest, args.output.resolve())
        else:
            manifest = validate_manifest(args.config, args.manifest)
            _print_summary(manifest, args.manifest.resolve().parent)
        return 0
    except GeoSourcesError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
