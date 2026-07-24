#!/usr/bin/env python3
"""Construye y valida el crosswalk municipal auditable de GEO-002.

La herramienta trabaja exclusivamente con el manifiesto y los snapshots fijados
por GEO-001. Una fila solo puede resolverse por igualdad literal inequívoca con
una variante de nombre publicada por el ICV o mediante un alias explícito y
aprobado. La normalización se usa únicamente para sugerir candidatos al mostrar
un error; nunca asigna un código.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from typing import Any, Iterable
import unicodedata
import urllib.parse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "geo_crosswalk.json"
CROSSWALK_NAME = "crosswalk.csv"
MANIFEST_NAME = "manifest.json"
REPORT_NAME = "REPORT.md"
SOURCE_IDS = ("municipios_112cv", "icv_municipios")
REVIEW_FIELDS = (
    "municipio_112cv",
    "cod_ine_mun",
    "review_categories",
    "icv_noms_mun_observed",
    "decision",
    "reviewed_at",
    "review_note",
)
CROSSWALK_FIELDS = (
    "municipio_112cv",
    "id_zona_previfoc",
    "icv_cod_ine_mun",
    "icv_nom_mun",
    "icv_nom_mun_cas",
    "icv_nom_mun_val",
    "icv_noms_mun",
    "match_method",
    "match_fields",
    "alias_reason",
    "review_status",
    "review_categories",
    "review_note",
)
APOSTROPHE_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u02bc": "'",
        "\u0060": "'",
        "\u00b4": "'",
    }
)
POSTPOSED_ARTICLE = re.compile(
    r",\s*(?:el|la|els|les|los|las|l')(?=/|$)", re.IGNORECASE
)


class CrosswalkError(RuntimeError):
    """Fallo esperado de configuración, entrada, asignación o validación."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CrosswalkError(f"no se puede leer {path}: {exc}") from exc
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


def _load_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrosswalkError(f"no se puede leer {description} {path}: {exc}") from exc


def _resolve_from(base: Path, value: str, description: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CrosswalkError(f"ruta no válida para {description}")
    return (base / value).resolve()


def _safe_relative_path(base: Path, value: str, description: str) -> Path:
    candidate = _resolve_from(base, value, description)
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise CrosswalkError(
            f"{description} queda fuera del directorio permitido: {value!r}"
        ) from exc
    return candidate


def _relative(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


def _load_config(path: Path) -> dict[str, Any]:
    config = _load_json(path, "la configuración")
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise CrosswalkError("schema_version de configuración no soportada")
    required = {
        "aliases",
        "expected",
        "icv",
        "output_directory",
        "provenance",
        "required_manual_samples",
        "reviews",
        "schema_version",
        "source_manifest",
    }
    missing = required - set(config)
    if missing:
        raise CrosswalkError(f"faltan claves de configuración: {sorted(missing)}")
    if set(config["provenance"]) != set(SOURCE_IDS):
        raise CrosswalkError(
            f"provenance debe contener exactamente {list(SOURCE_IDS)}"
        )
    expected = config["expected"]
    if not isinstance(expected, dict):
        raise CrosswalkError("expected debe ser un objeto")
    allowed = expected.get("allowed_zone_ids")
    zone_counts = expected.get("zone_counts")
    if (
        not isinstance(allowed, list)
        or not allowed
        or not isinstance(zone_counts, dict)
        or {str(value) for value in allowed} != set(zone_counts)
    ):
        raise CrosswalkError("allowed_zone_ids y zone_counts no son coherentes")
    icv = config["icv"]
    if not isinstance(icv, dict) or not icv.get("name_fields"):
        raise CrosswalkError("falta la configuración de campos ICV")
    return config


def _load_fixed_sources(
    config_path: Path, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Path], str, Path]:
    manifest_path = _resolve_from(
        config_path.parent, config["source_manifest"], "source_manifest"
    )
    manifest = _load_json(manifest_path, "el manifiesto de GEO-001")
    if (
        not isinstance(manifest, dict)
        or manifest.get("manifest_schema_version") != 1
        or set(manifest.get("sources", {})) != set(SOURCE_IDS)
    ):
        raise CrosswalkError("el manifiesto de GEO-001 no cumple el esquema esperado")

    snapshots: dict[str, Path] = {}
    for source_id in SOURCE_IDS:
        record = manifest["sources"][source_id]
        fixed = config["provenance"][source_id]
        for key, manifest_key in (
            ("snapshot", "snapshot"),
            ("sha256", "sha256"),
            ("dataset_content_sha256", None),
        ):
            observed = (
                record["inspection"].get(key)
                if manifest_key is None
                else record.get(manifest_key)
            )
            if observed != fixed.get(key):
                raise CrosswalkError(
                    f"{source_id}: {key} del manifiesto no coincide con la "
                    f"procedencia fijada ({observed!r} != {fixed.get(key)!r})"
                )
        snapshot = _safe_relative_path(
            manifest_path.parent, record["snapshot"], f"snapshot {source_id}"
        )
        if not snapshot.is_file():
            raise CrosswalkError(f"falta el snapshot fijado {snapshot}")
        digest = sha256_file(snapshot)
        if digest != record["sha256"]:
            raise CrosswalkError(
                f"{source_id}: SHA-256 crudo incorrecto ({digest} != {record['sha256']})"
            )
        if snapshot.stat().st_size != int(record["size_bytes"]):
            raise CrosswalkError(f"{source_id}: tamaño distinto al manifiesto")
        snapshots[source_id] = snapshot
    return manifest, snapshots, sha256_file(manifest_path), manifest_path


def _load_112cv(path: Path, expected: dict[str, Any]) -> list[dict[str, Any]]:
    data = _load_json(path, "el snapshot 112CV")
    if not isinstance(data, list):
        raise CrosswalkError("la raíz del snapshot 112CV no es un array")
    required_fields = {
        "municipio",
        "idZonaPrevifoc",
        "idZonaAvisoMeteo",
        "idZonaEmergencia",
    }
    allowed_zones = {int(value) for value in expected["allowed_zone_ids"]}
    outside_expected = expected["outside_record"]
    assigned: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    all_names: list[str] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict) or not required_fields.issubset(row):
            raise CrosswalkError(f"fila 112CV {index} inválida o incompleta")
        name = row["municipio"]
        zone = row["idZonaPrevifoc"]
        if not isinstance(name, str) or not name.strip():
            raise CrosswalkError(f"nombre 112CV vacío en la fila {index}")
        if not isinstance(zone, int) or isinstance(zone, bool):
            raise CrosswalkError(f"zona 112CV no entera para {name!r}")
        all_names.append(name)
        if zone in allowed_zones:
            assigned.append(row)
        elif zone == 0:
            outside.append(row)
        else:
            raise CrosswalkError(f"zona 112CV no permitida {zone} para {name!r}")

    duplicate_names = sorted(
        name
        for name, count in collections.Counter(all_names).items()
        if count != 1
    )
    if duplicate_names:
        raise CrosswalkError(f"nombres 112CV duplicados: {duplicate_names[:10]}")
    if outside != [outside_expected]:
        raise CrosswalkError(
            "Fuera C.V. debe existir una vez, coincidir exactamente con el contrato "
            "y quedar excluido"
        )
    expected_count = int(expected["municipality_count"])
    if len(assigned) != expected_count:
        raise CrosswalkError(
            f"hay {len(assigned)} municipios 112CV; se esperaban {expected_count}"
        )
    zone_counts = collections.Counter(row["idZonaPrevifoc"] for row in assigned)
    expected_counts = {
        int(zone): int(count) for zone, count in expected["zone_counts"].items()
    }
    if dict(zone_counts) != expected_counts:
        raise CrosswalkError(
            f"conteos 112CV por zona {dict(sorted(zone_counts.items()))}; "
            f"esperados {dict(sorted(expected_counts.items()))}"
        )
    return assigned


def _quote_identifier(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CrosswalkError(f"identificador SQLite inválido: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri_path = urllib.parse.quote(str(path.resolve()), safe="/")
    try:
        connection = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise CrosswalkError(f"no se puede abrir el GeoPackage fijado: {exc}") from exc


def _load_icv(path: Path, settings: dict[str, Any], expected_count: int) -> list[dict[str, Any]]:
    layer = settings["layer"]
    code_field = settings["code_field"]
    geometry_field = settings["geometry_field"]
    name_fields = list(settings["name_fields"])
    selected = [code_field, geometry_field, *name_fields]
    if len(set(selected)) != len(selected):
        raise CrosswalkError("los campos ICV configurados no son únicos")
    try:
        with contextlib.closing(_connect_readonly(path)) as connection:
            schema = {
                row["name"]
                for row in connection.execute(
                    f"PRAGMA table_info({_quote_identifier(layer)})"
                )
            }
            missing = set(selected) - schema
            if missing:
                raise CrosswalkError(f"faltan campos ICV: {sorted(missing)}")
            query = (
                "SELECT "
                + ", ".join(_quote_identifier(field) for field in selected)
                + f" FROM {_quote_identifier(layer)} ORDER BY {_quote_identifier(code_field)}"
            )
            rows = [dict(row) for row in connection.execute(query)]
    except sqlite3.Error as exc:
        raise CrosswalkError(f"error al leer la capa ICV {layer!r}: {exc}") from exc

    if len(rows) != expected_count:
        raise CrosswalkError(
            f"la capa ICV contiene {len(rows)} filas; se esperaban {expected_count}"
        )
    codes: list[str] = []
    for row in rows:
        code = row[code_field]
        if not isinstance(code, str) or re.fullmatch(r"\d{5}", code) is None:
            raise CrosswalkError(
                f"código ICV inválido {code!r}; debe ser texto de cinco dígitos"
            )
        if row[geometry_field] is None or len(row[geometry_field]) == 0:
            raise CrosswalkError(f"geometría ICV vacía para el código {code}")
        if not isinstance(row[name_fields[0]], str) or not row[name_fields[0]].strip():
            raise CrosswalkError(f"nombre ICV principal vacío para el código {code}")
        for field in name_fields:
            if row[field] is not None and not isinstance(row[field], str):
                raise CrosswalkError(f"{field} no textual para el código {code}")
        codes.append(code)
    duplicate_codes = sorted(
        code for code, count in collections.Counter(codes).items() if count != 1
    )
    if duplicate_codes:
        raise CrosswalkError(f"códigos ICV duplicados: {duplicate_codes[:10]}")
    return rows


def normalize_candidate_name(value: str) -> str:
    """Normalización explicable usada solo para sugerir candidatos."""

    normalized = unicodedata.normalize("NFKC", value).translate(APOSTROPHE_TRANSLATION)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def _candidate_keys(value: str) -> set[str]:
    whole = normalize_candidate_name(value)
    return {whole, *(part for part in whole.split("/") if part)}


def _exact_index(
    icv_rows: list[dict[str, Any]], code_field: str, name_fields: list[str]
) -> dict[str, dict[str, list[str]]]:
    index: dict[str, dict[str, list[str]]] = {}
    for row in icv_rows:
        for field in name_fields:
            value = row[field]
            if value:
                index.setdefault(value, {}).setdefault(row[code_field], []).append(field)
    return index


def _normalized_candidate_index(
    icv_rows: list[dict[str, Any]], code_field: str, name_fields: list[str]
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for row in icv_rows:
        for field in name_fields:
            value = row[field]
            if value:
                for key in _candidate_keys(value):
                    index.setdefault(key, set()).add(row[code_field])
    return index


def _load_aliases(
    path: Path,
    config: dict[str, Any],
    source_names: set[str],
    icv_by_code: dict[str, dict[str, Any]],
    exact_index: dict[str, dict[str, list[str]]],
) -> dict[str, dict[str, Any]]:
    document = _load_json(path, "el fichero de aliases")
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise CrosswalkError("schema_version del fichero de aliases no soportada")
    applies_to = document.get("applies_to", {})
    expected_applies_to = {
        "municipios_112cv_sha256": config["provenance"]["municipios_112cv"]["sha256"],
        "icv_municipios_sha256": config["provenance"]["icv_municipios"]["sha256"],
        "icv_municipios_dataset_content_sha256": config["provenance"]["icv_municipios"]["dataset_content_sha256"],
    }
    if applies_to != expected_applies_to:
        raise CrosswalkError("la procedencia del fichero de aliases no coincide")
    entries = document.get("aliases")
    if not isinstance(entries, list):
        raise CrosswalkError("aliases debe ser un array")

    aliases: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CrosswalkError(f"alias {index} no es un objeto")
        name = entry.get("municipio_112cv")
        code = entry.get("cod_ine_mun")
        reason = entry.get("reason")
        review = entry.get("review")
        expected_icv = entry.get("expected_icv")
        if not isinstance(name, str) or name not in source_names:
            raise CrosswalkError(f"alias {index} referencia un municipio 112CV ausente")
        if name in aliases:
            raise CrosswalkError(f"alias duplicado para {name!r}")
        if name in exact_index:
            raise CrosswalkError(f"alias redundante: {name!r} ya tiene coincidencia exacta")
        if not isinstance(code, str) or code not in icv_by_code:
            raise CrosswalkError(f"alias {name!r} referencia código ICV ausente {code!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise CrosswalkError(f"alias {name!r} no documenta el motivo")
        if (
            not isinstance(review, dict)
            or review.get("status") != "approved"
            or not isinstance(review.get("reviewed_at"), str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", review["reviewed_at"]) is None
            or not isinstance(review.get("basis"), str)
            or not review["basis"].strip()
        ):
            raise CrosswalkError(f"alias {name!r} no tiene una revisión aprobada completa")
        if not isinstance(expected_icv, dict) or not expected_icv:
            raise CrosswalkError(f"alias {name!r} no fija valores ICV esperados")
        row = icv_by_code[code]
        for field, expected_value in expected_icv.items():
            if field not in row or row[field] != expected_value:
                raise CrosswalkError(
                    f"alias {name!r}: {field} cambió ({row.get(field)!r} != {expected_value!r})"
                )
        aliases[name] = entry
    return aliases


def _required_review_categories(
    name: str, aliases: dict[str, dict[str, Any]], samples: set[str]
) -> list[str]:
    categories: list[str] = []
    if name in samples:
        categories.append("required_sample")
    if "/" in name:
        categories.append("bilingual")
    if POSTPOSED_ARTICLE.search(name):
        categories.append("postposed_article")
    if name in aliases:
        categories.append("alias")
    return categories


def _load_reviews(path: Path) -> dict[str, dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != REVIEW_FIELDS:
                raise CrosswalkError(
                    f"cabecera de revisiones inesperada: {reader.fieldnames!r}"
                )
            reviews: dict[str, dict[str, str]] = {}
            for line_number, row in enumerate(reader, start=2):
                name = row["municipio_112cv"]
                if not name:
                    raise CrosswalkError(f"revisión sin municipio en línea {line_number}")
                if name in reviews:
                    raise CrosswalkError(f"revisión duplicada para {name!r}")
                if row["decision"] != "approved":
                    raise CrosswalkError(f"revisión no aprobada para {name!r}")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["reviewed_at"]) is None:
                    raise CrosswalkError(f"fecha de revisión inválida para {name!r}")
                if not row["review_note"].strip():
                    raise CrosswalkError(f"falta nota de revisión para {name!r}")
                reviews[name] = dict(row)
            return reviews
    except CrosswalkError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise CrosswalkError(f"no se puede leer el registro de revisiones {path}: {exc}") from exc


def _suggest_candidates(
    name: str, normalized_index: dict[str, set[str]]
) -> list[str]:
    candidates: set[str] = set()
    for key in _candidate_keys(name):
        candidates.update(normalized_index.get(key, set()))
    return sorted(candidates)


def _build_rows(
    source_rows: list[dict[str, Any]],
    icv_rows: list[dict[str, Any]],
    settings: dict[str, Any],
    aliases: dict[str, dict[str, Any]],
    reviews: dict[str, dict[str, str]],
    required_samples: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    code_field = settings["code_field"]
    geometry_field = settings["geometry_field"]
    name_fields = list(settings["name_fields"])
    icv_by_code = {row[code_field]: row for row in icv_rows}
    exact = _exact_index(icv_rows, code_field, name_fields)
    normalized = _normalized_candidate_index(icv_rows, code_field, name_fields)
    unresolved: list[tuple[str, list[str]]] = []
    ambiguous: list[tuple[str, list[str]]] = []
    resolved: list[dict[str, Any]] = []

    for source in source_rows:
        name = source["municipio"]
        hits = exact.get(name, {})
        if len(hits) > 1:
            ambiguous.append((name, sorted(hits)))
            continue
        if hits:
            code = next(iter(hits))
            fields = sorted(hits[code], key=name_fields.index)
            method = "exact_primary" if name_fields[0] in fields else "exact_variant"
            alias_reason = ""
        else:
            alias = aliases.get(name)
            if alias is None:
                unresolved.append((name, _suggest_candidates(name, normalized)))
                continue
            code = alias["cod_ine_mun"]
            fields = ["alias_file"]
            method = "alias"
            alias_reason = alias["reason"]
        resolved.append(
            {
                "source": source,
                "icv": icv_by_code[code],
                "code": code,
                "fields": fields,
                "method": method,
                "alias_reason": alias_reason,
            }
        )

    if unresolved or ambiguous:
        lines = ["el crosswalk no se puede resolver de forma determinista:"]
        for name, candidates in unresolved:
            suggestion = ", ".join(candidates) if candidates else "ninguno"
            lines.append(
                f"- no encontrado {name!r}; candidatos por normalización: {suggestion}"
            )
        for name, codes in ambiguous:
            lines.append(f"- coincidencia exacta ambigua {name!r}: {', '.join(codes)}")
        raise CrosswalkError("\n".join(lines))

    assigned_codes = [item["code"] for item in resolved]
    duplicate_codes = sorted(
        code
        for code, count in collections.Counter(assigned_codes).items()
        if count != 1
    )
    missing_codes = sorted(set(icv_by_code) - set(assigned_codes))
    if duplicate_codes or missing_codes:
        raise CrosswalkError(
            "la asignación no es biyectiva; "
            f"códigos duplicados={duplicate_codes[:10]}, sin asignar={missing_codes[:10]}"
        )

    required_by_name = {
        item["source"]["municipio"]: _required_review_categories(
            item["source"]["municipio"], aliases, required_samples
        )
        for item in resolved
    }
    required_names = {name for name, categories in required_by_name.items() if categories}
    missing_reviews = sorted(required_names - set(reviews))
    extra_reviews = sorted(set(reviews) - required_names)
    if missing_reviews or extra_reviews:
        raise CrosswalkError(
            "el registro manual no cubre exactamente los casos obligatorios; "
            f"faltan={missing_reviews[:10]}, sobran={extra_reviews[:10]}"
        )

    rows: list[dict[str, str]] = []
    for item in resolved:
        source = item["source"]
        icv = item["icv"]
        name = source["municipio"]
        categories = required_by_name[name]
        review = reviews.get(name)
        if review:
            observed_categories = review["review_categories"].split(";")
            if observed_categories != categories:
                raise CrosswalkError(
                    f"categorías de revisión incorrectas para {name!r}: "
                    f"{observed_categories!r} != {categories!r}"
                )
            if review["cod_ine_mun"] != item["code"]:
                raise CrosswalkError(f"la revisión de {name!r} aprueba otro código")
            if review["icv_noms_mun_observed"] != (icv.get("noms_mun") or ""):
                raise CrosswalkError(f"noms_mun cambió desde la revisión de {name!r}")
        rows.append(
            {
                "municipio_112cv": name,
                "id_zona_previfoc": str(source["idZonaPrevifoc"]),
                "icv_cod_ine_mun": item["code"],
                "icv_nom_mun": icv.get("nom_mun") or "",
                "icv_nom_mun_cas": icv.get("nom_mun_cas") or "",
                "icv_nom_mun_val": icv.get("nom_mun_val") or "",
                "icv_noms_mun": icv.get("noms_mun") or "",
                "match_method": item["method"],
                "match_fields": ";".join(item["fields"]),
                "alias_reason": item["alias_reason"],
                "review_status": "reviewed" if review else "automatic",
                "review_categories": ";".join(categories),
                "review_note": review["review_note"] if review else "",
            }
        )

    rows.sort(key=lambda row: (row["municipio_112cv"].casefold(), row["municipio_112cv"]))
    stats = {
        "ambiguous_matches": 0,
        "duplicate_icv_codes": 0,
        "exact_matches": sum(row["match_method"].startswith("exact_") for row in rows),
        "excluded_outside_cv_records": 1,
        "manual_reviews": sum(row["review_status"] == "reviewed" for row in rows),
        "match_methods": dict(
            sorted(collections.Counter(row["match_method"] for row in rows).items())
        ),
        "municipalities": len(rows),
        "unmatched": 0,
        "aliases": sum(row["match_method"] == "alias" for row in rows),
        "zone_counts": {
            zone: count
            for zone, count in sorted(
                collections.Counter(row["id_zona_previfoc"] for row in rows).items(),
                key=lambda item: int(item[0]),
            )
        },
        "review_categories": dict(
            sorted(
                collections.Counter(
                    category
                    for row in rows
                    for category in row["review_categories"].split(";")
                    if category
                ).items()
            )
        ),
    }
    return rows, stats


def _csv_bytes(fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report_bytes(
    rows: list[dict[str, str]],
    stats: dict[str, Any],
    manifest: dict[str, Any],
    config: dict[str, Any],
    aliases: dict[str, dict[str, Any]],
    reviews: dict[str, dict[str, str]],
    crosswalk_sha256: str,
) -> bytes:
    source_manifest = manifest["sources"]
    lines = [
        "# GEO-002 — Informe del crosswalk municipal",
        "",
        "Este informe corresponde al crosswalk reproducible de 542 municipios. No modifica ni procesa geometrías.",
        "",
        "## Procedencia fijada",
        "",
        "| Fuente | Snapshot de GEO-001 | SHA-256 crudo | Huella lógica | Licencia |",
        "|---|---|---|---|---|",
    ]
    for source_id in SOURCE_IDS:
        record = source_manifest[source_id]
        lines.append(
            f"| `{source_id}` | `{_markdown_cell(record['snapshot'])}` | "
            f"`{record['sha256']}` | "
            f"`{record['inspection']['dataset_content_sha256']}` | "
            f"{_markdown_cell(record['license']['status'])} |"
        )
    lines.extend(
        [
            "",
            "Las rutas anteriores se resolvieron desde `data/sources/manifest.json`; no se consultó ninguna URL viva. `Fuera C.V.` se comprobó contra el registro fijado y se excluyó explícitamente.",
            "",
            "La licencia ICV sigue declarada como `CC BY 4.0 Generalitat`. La licencia específica de 112CV continúa en estado `not_found`: esta ausencia no bloquea el trabajo local, pero sí debe resolverse antes de reutilización pública.",
            "",
            "## Resultado",
            "",
            f"- Filas: **{stats['municipalities']}**; SHA-256 de `crosswalk.csv`: `{crosswalk_sha256}`.",
            f"- Coincidencias exactas inequívocas: **{stats['exact_matches']}**.",
            f"- Aliases/excepciones explícitas: **{stats['aliases']}**.",
            f"- Revisiones manuales registradas: **{stats['manual_reviews']}**.",
            "- No encontrados tras aplicar aliases: **0**.",
            "- Coincidencias exactas ambiguas: **0**.",
            "- Códigos ICV duplicados, vacíos o sin asignar: **0**.",
            "- Códigos con ceros iniciales: conservados como texto de cinco dígitos.",
            "",
            "### Métodos",
            "",
            "| Método | Filas | Regla |",
            "|---|---:|---|",
        ]
    )
    rules = {
        "exact_primary": "Igualdad literal inequívoca con `nom_mun`.",
        "exact_variant": "Igualdad literal inequívoca con otra variante ICV publicada.",
        "alias": "Código fijado en el fichero de aliases aprobado.",
    }
    for method, count in stats["match_methods"].items():
        lines.append(f"| `{method}` | {count} | {rules[method]} |")
    lines.extend(
        [
            "",
            "La normalización Unicode NFKC, de espacios, caja, apóstrofos y separadores `/` solo se usa para proponer candidatos al diagnosticar un nombre sin resolver. No se usa similitud aproximada ni se aprueba ninguna asignación normalizada automáticamente.",
            "",
            "### Conteos por zona",
            "",
            "| `idZonaPrevifoc` | Municipios |",
            "|---:|---:|",
        ]
    )
    for zone, count in stats["zone_counts"].items():
        lines.append(f"| {zone} | {count} |")
    lines.extend(
        [
            "",
            "## Aliases y excepciones aprobados",
            "",
            "| Nombre 112CV | Código ICV | `nom_mun` | `noms_mun` | Motivo | Revisión |",
            "|---|---|---|---|---|---|",
        ]
    )
    by_name = {row["municipio_112cv"]: row for row in rows}
    for name in sorted(aliases, key=lambda value: (value.casefold(), value)):
        entry = aliases[name]
        row = by_name[name]
        lines.append(
            f"| {_markdown_cell(name)} | `{row['icv_cod_ine_mun']}` | "
            f"{_markdown_cell(row['icv_nom_mun'])} | {_markdown_cell(row['icv_noms_mun'])} | "
            f"{_markdown_cell(entry['reason'])} | "
            f"{entry['review']['status']} ({entry['review']['reviewed_at']}) |"
        )
    lines.extend(
        [
            "",
            "## Casos de revisión manual",
            "",
            "El registro versionado cubre todas las denominaciones bilingües, todos los artículos pospuestos detectados, todas las excepciones y las muestras mínimas Ademuz, València y Alacant/Alicante.",
            "",
            "| Nombre 112CV | Código ICV | Categorías | `noms_mun` contrastado | Decisión |",
            "|---|---|---|---|---|",
        ]
    )
    for name in sorted(reviews, key=lambda value: (value.casefold(), value)):
        review = reviews[name]
        lines.append(
            f"| {_markdown_cell(name)} | `{review['cod_ine_mun']}` | "
            f"`{_markdown_cell(review['review_categories'])}` | "
            f"{_markdown_cell(review['icv_noms_mun_observed'])} | "
            f"{review['decision']} ({review['reviewed_at']}) |"
        )
    lines.extend(
        [
            "",
            "## Diagnósticos finales",
            "",
            "- No encontrados: ninguno.",
            "- Duplicados de municipio 112CV: ninguno.",
            "- Coincidencias exactas ambiguas: ninguna.",
            "- Duplicados de `cod_ine_mun`: ninguno.",
            "- Filas pendientes de revisión: ninguna.",
            "",
            "## Condiciones para GEO-003",
            "",
            "GEO-003 puede unir por `icv_cod_ine_mun` usando este `crosswalk.csv` y debe verificar su SHA-256. Debe mantener los códigos como texto. La confirmación formal de que PREVIFOC se define exactamente por municipios completos y la licencia específica 112CV continúan sin verificarse; no afectan a la cobertura del crosswalk local, pero deben mantenerse visibles antes de publicación.",
            "",
            "No se han disuelto municipios, generado zonas, reproyectado, simplificado ni creado teselas en GEO-002.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def render_artifacts(config_path: Path = DEFAULT_CONFIG) -> tuple[dict[str, bytes], Path]:
    config_path = config_path.resolve()
    config = _load_config(config_path)
    source_manifest, snapshots, source_manifest_sha, source_manifest_path = (
        _load_fixed_sources(config_path, config)
    )
    expected = config["expected"]
    source_rows = _load_112cv(snapshots["municipios_112cv"], expected)
    icv_rows = _load_icv(
        snapshots["icv_municipios"],
        config["icv"],
        int(expected["municipality_count"]),
    )
    code_field = config["icv"]["code_field"]
    name_fields = list(config["icv"]["name_fields"])
    source_names = {row["municipio"] for row in source_rows}
    icv_by_code = {row[code_field]: row for row in icv_rows}
    exact_index = _exact_index(icv_rows, code_field, name_fields)

    aliases_path = _resolve_from(config_path.parent, config["aliases"], "aliases")
    reviews_path = _resolve_from(config_path.parent, config["reviews"], "reviews")
    aliases = _load_aliases(
        aliases_path, config, source_names, icv_by_code, exact_index
    )
    reviews = _load_reviews(reviews_path)
    required_samples = set(config["required_manual_samples"])
    if not required_samples.issubset(source_names):
        raise CrosswalkError("alguna muestra manual obligatoria no existe en 112CV")
    rows, stats = _build_rows(
        source_rows,
        icv_rows,
        config["icv"],
        aliases,
        reviews,
        required_samples,
    )

    expected_counts = {
        str(zone): int(count) for zone, count in expected["zone_counts"].items()
    }
    if stats["municipalities"] != int(expected["municipality_count"]):
        raise CrosswalkError("el crosswalk no tiene el número esperado de filas")
    if stats["zone_counts"] != expected_counts:
        raise CrosswalkError("los conteos finales por zona no coinciden")

    crosswalk_content = _csv_bytes(CROSSWALK_FIELDS, rows)
    crosswalk_sha = sha256_bytes(crosswalk_content)
    report_content = _report_bytes(
        rows,
        stats,
        source_manifest,
        config,
        aliases,
        reviews,
        crosswalk_sha,
    )
    output_directory = _resolve_from(
        config_path.parent, config["output_directory"], "output_directory"
    )
    artifact_manifest = {
        "crosswalk_schema_version": 1,
        "inputs": {
            "aliases": {
                "path": _relative(aliases_path, output_directory),
                "sha256": sha256_file(aliases_path),
            },
            "configuration": {
                "path": _relative(config_path, output_directory),
                "sha256": sha256_file(config_path),
            },
            "reviews": {
                "path": _relative(reviews_path, output_directory),
                "sha256": sha256_file(reviews_path),
            },
            "source_manifest": {
                "path": _relative(source_manifest_path, output_directory),
                "sha256": source_manifest_sha,
            },
            "sources": {
                source_id: {
                    "dataset_content_sha256": source_manifest["sources"][source_id][
                        "inspection"
                    ]["dataset_content_sha256"],
                    "sha256": source_manifest["sources"][source_id]["sha256"],
                    "snapshot": _relative(snapshots[source_id], output_directory),
                }
                for source_id in SOURCE_IDS
            },
        },
        "outputs": {
            CROSSWALK_NAME: {
                "rows": len(rows),
                "sha256": crosswalk_sha,
                "size_bytes": len(crosswalk_content),
            },
            REPORT_NAME: {
                "sha256": sha256_bytes(report_content),
                "size_bytes": len(report_content),
            },
        },
        "statistics": stats,
    }
    artifacts = {
        CROSSWALK_NAME: crosswalk_content,
        REPORT_NAME: report_content,
        MANIFEST_NAME: _json_bytes(artifact_manifest),
    }
    return artifacts, output_directory


def build_crosswalk(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    for name in (CROSSWALK_NAME, REPORT_NAME, MANIFEST_NAME):
        _atomic_write(output_directory / name, artifacts[name])
    return artifacts


def validate_crosswalk(config_path: Path = DEFAULT_CONFIG) -> dict[str, bytes]:
    artifacts, output_directory = render_artifacts(config_path)
    for name, expected in artifacts.items():
        path = output_directory / name
        try:
            observed = path.read_bytes()
        except OSError as exc:
            raise CrosswalkError(f"no se puede leer el entregable {path}: {exc}") from exc
        if observed != expected:
            raise CrosswalkError(
                f"{path} no coincide byte a byte con la regeneración determinista"
            )
    return artifacts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construye y valida el crosswalk municipal de GEO-002 sin red."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("build", "construir crosswalk, manifiesto e informe"),
        ("validate", "regenerar en memoria y comparar los entregables byte a byte"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "build":
            artifacts = build_crosswalk(args.config)
        else:
            artifacts = validate_crosswalk(args.config)
        config = _load_config(args.config.resolve())
        output = _resolve_from(
            args.config.resolve().parent,
            config["output_directory"],
            "output_directory",
        )
        manifest = json.loads(artifacts[MANIFEST_NAME])
        print(f"crosswalk: {output / CROSSWALK_NAME}")
        print(f"informe: {output / REPORT_NAME}")
        print(f"manifiesto: {output / MANIFEST_NAME}")
        print(
            "filas: {rows}; sha256: {sha}".format(
                rows=manifest["outputs"][CROSSWALK_NAME]["rows"],
                sha=manifest["outputs"][CROSSWALK_NAME]["sha256"],
            )
        )
        return 0
    except CrosswalkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
