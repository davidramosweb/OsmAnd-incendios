#!/usr/bin/env python3
"""Construye y valida el instalador reproducible de OSMAND-003."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "osmand_package.json"
DEFAULT_OUTPUT = ROOT / "static" / "previfoc.osf"
ARCHIVE_FILES = ("items.json", "res/previfoc.png")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_BYTES = 256 * 1024
MAX_MEMBER_BYTES = 512 * 1024
EXPECTED_CONFIG_KEYS = {
    "schema_version",
    "artifact_version",
    "plugin_version",
    "plugin_id",
    "source_name",
    "source_name_en",
    "current_source_name",
    "forecast_source_name",
    "public_origin",
    "current_tile_url",
    "forecast_tile_url",
    "help_url",
    "attribution_url",
    "limitations_url",
    "official_source_url",
    "min_zoom",
    "max_zoom",
    "expire_minutes",
    "tile_size",
    "bit_density",
    "average_tile_size",
}


class PackageError(ValueError):
    """El paquete o su configuración no cumplen el contrato."""


def _invariant(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_config(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"no se pudo leer la configuración: {exc}") from exc
    _invariant(isinstance(config, dict), "la configuración debe ser un objeto JSON")
    keys = set(config)
    _invariant(keys == EXPECTED_CONFIG_KEYS, f"campos de configuración inesperados: {sorted(keys ^ EXPECTED_CONFIG_KEYS)}")
    _invariant(type(config["schema_version"]) is int and config["schema_version"] == 1, "schema_version no soportada")
    _invariant(isinstance(config["artifact_version"], str) and bool(re.fullmatch(r"[1-9]\d*\.\d+\.\d+", config["artifact_version"])), "artifact_version debe ser semver estable")
    _invariant(type(config["plugin_version"]) is int and config["plugin_version"] > 0, "plugin_version debe ser entero positivo")
    _invariant(isinstance(config["plugin_id"], str) and bool(re.fullmatch(r"[a-z][a-z0-9]*(?:\.[a-z0-9]+)+", config["plugin_id"])), "plugin_id no es estable")
    for key in ("source_name", "source_name_en", "current_source_name", "forecast_source_name"):
        _invariant(isinstance(config[key], str) and config[key].strip() == config[key] and config[key], f"{key} no es válido")
    for key in ("public_origin", "current_tile_url", "forecast_tile_url", "help_url", "attribution_url", "limitations_url", "official_source_url"):
        value = config[key]
        _invariant(isinstance(value, str), f"{key} debe ser una cadena")
        parsed = urlparse(value)
        _invariant(parsed.scheme == "https" and parsed.netloc, f"{key} debe ser HTTPS absoluto")
        _invariant(parsed.username is None and parsed.password is None, f"{key} no puede incluir credenciales")
    origin = config["public_origin"].rstrip("/")
    _invariant(config["public_origin"] == origin, "public_origin no debe terminar en barra")
    _invariant(config["current_tile_url"] == f"{origin}/tiles/current/{{0}}/{{1}}/{{2}}.png", "current_tile_url no coincide con la ruta XYZ actual")
    _invariant(config["forecast_tile_url"] == f"{origin}/tiles/forecast-next-day/{{0}}/{{1}}/{{2}}.png", "forecast_tile_url no coincide con la ruta XYZ de previsión")
    _invariant(config["help_url"] == f"{origin}/#instalar", "help_url no coincide con la página pública")
    _invariant(config["attribution_url"] == f"{origin}/#atribucion", "attribution_url no coincide con la página pública")
    _invariant(config["limitations_url"] == f"{origin}/#limitaciones", "limitations_url no coincide con la página pública")
    _invariant(type(config["min_zoom"]) is int and type(config["max_zoom"]) is int and config["min_zoom"] == 6 and config["max_zoom"] == 14, "el contrato exige zoom 6–14")
    _invariant(type(config["expire_minutes"]) is int and config["expire_minutes"] == 60, "el contrato exige una caducidad de 60 minutos")
    _invariant(type(config["tile_size"]) is int and config["tile_size"] == 256, "el contrato exige teselas de 256 px")
    _invariant(type(config["bit_density"]) is int and config["bit_density"] == 8, "el PNG indexado exige bitDensity 8")
    _invariant(type(config["average_tile_size"]) is int and config["average_tile_size"] > 0, "average_tile_size debe ser positivo")
    return config


def _description(config: dict[str, Any], *, english: bool) -> str:
    if english:
        warning = (
            "Independent, unofficial service. PREVIFOC level 3 is treated as a preventive closure of forest tracks "
            "and paths only in today's layer; tomorrow's layer is a risk forecast and does not confirm a future closure. "
            "Levels 1 and 2 do not confirm that a route is open. Check official authorities "
            "and applicable resolutions."
        )
        labels = ("Installation and notices", "Attribution", "Limitations", "Official 112CV source")
    else:
        warning = (
            "Servicio independiente y no oficial. Esta capa trata el nivel 3 PREVIFOC como cierre preventivo propio "
            "de pistas y sendas forestales solo en la capa de hoy; la capa de mañana es una previsión de riesgo y no "
            "confirma un cierre futuro. Los niveles 1 y 2 no confirman que una vía esté abierta. Consulte las "
            "autoridades y resoluciones aplicables."
        )
        labels = ("Instalación y avisos", "Atribución", "Limitaciones", "Fuente oficial 112CV")
    links = (
        (labels[0], config["help_url"]),
        (labels[1], config["attribution_url"]),
        (labels[2], config["limitations_url"]),
        (labels[3], config["official_source_url"]),
    )
    return warning + " " + " · ".join(f'<a href="{url}">{label}</a>' for label, url in links) + "."


def _items_document(config: dict[str, Any]) -> dict[str, Any]:
    plugin_id = config["plugin_id"]
    def map_source(name: str, url: str) -> dict[str, Any]:
        return {
            "sql": False,
            "name": name,
            "minZoom": config["min_zoom"],
            "maxZoom": config["max_zoom"],
            "url": url,
            "ellipsoid": False,
            "inverted_y": False,
            "timesupported": True,
            "expire": config["expire_minutes"],
            "inversiveZoom": False,
            "ext": ".png",
            "tileSize": config["tile_size"],
            "bitDensity": config["bit_density"],
            "avgSize": config["average_tile_size"],
        }
    return {
        "version": 1,
        "items": [
            {
                "type": "PLUGIN",
                "pluginId": plugin_id,
                "version": config["plugin_version"],
                "icon": {"": "@previfoc.png"},
                "name": {"": config["source_name"], "en": config["source_name_en"]},
                "description": {"": _description(config, english=False), "en": _description(config, english=True)},
            },
            {"type": "RESOURCES", "pluginId": plugin_id, "file": "res"},
            {
                "type": "MAP_SOURCES",
                "pluginId": plugin_id,
                "items": [
                    map_source(config["current_source_name"], config["current_tile_url"]),
                    map_source(config["forecast_source_name"], config["forecast_tile_url"]),
                ],
            },
        ],
    }


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _icon_png(size: int = 256) -> bytes:
    """Genera un icono RGBA simple y determinista, sin dependencias gráficas."""
    background = (23, 59, 53, 255)
    foreground = (248, 245, 236, 255)
    accent = (224, 126, 60, 255)
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            color = background
            dx, dy = x - 128, y - 128
            if dx * dx + dy * dy <= 104 * 104:
                color = accent
            # Una P geométrica legible incluso a tamaño pequeño.
            if 74 <= x <= 99 and 61 <= y <= 196:
                color = foreground
            if 92 <= x <= 159 and 61 <= y <= 86:
                color = foreground
            if 92 <= x <= 159 and 118 <= y <= 143:
                color = foreground
            if 148 <= x <= 173 and 72 <= y <= 132:
                color = foreground
            rows.extend(color)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _png_chunk(b"IEND", b"")


def _json_bytes(config: dict[str, Any]) -> bytes:
    return (json.dumps(_items_document(config), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build(config_path: Path = DEFAULT_CONFIG, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    config = _read_config(config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(_zip_info("items.json"), _json_bytes(config), compresslevel=9)
        archive.writestr(_zip_info("res/previfoc.png"), _icon_png(), compresslevel=9)
    return validate(output_path, config_path)


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    _invariant(not path.is_absolute(), f"ruta absoluta prohibida: {name}")
    _invariant(".." not in path.parts and "." not in path.parts, f"ruta no normalizada: {name}")
    _invariant("\\" not in name and not name.endswith("/"), f"ruta ZIP no portable: {name}")


def _validate_icon(data: bytes) -> None:
    _invariant(data.startswith(b"\x89PNG\r\n\x1a\n"), "el icono no es PNG")
    _invariant(len(data) >= 33 and data[12:16] == b"IHDR", "IHDR de icono ausente")
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    _invariant((width, height, depth, color_type) == (256, 256, 8, 6), "el icono debe ser PNG RGBA 256×256 de 8 bits")
    _invariant(data == _icon_png(), "el icono no coincide con el recurso reproducible")


def validate(package_path: Path = DEFAULT_OUTPUT, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = _read_config(config_path)
    _invariant(package_path.suffix == ".osf", "el artefacto debe usar extensión .osf")
    try:
        package_bytes = package_path.read_bytes()
    except OSError as exc:
        raise PackageError(f"no se pudo leer {package_path}: {exc}") from exc
    _invariant(len(package_bytes) <= MAX_ARCHIVE_BYTES, "el paquete excede el límite de tamaño")
    try:
        with ZipFile(package_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            _invariant(len(names) == len(set(names)), "el ZIP contiene rutas duplicadas")
            _invariant(tuple(names) == ARCHIVE_FILES, f"contenido ZIP inesperado: {names}")
            for info in infos:
                _validate_member_name(info.filename)
                _invariant(not (info.flag_bits & 0x1), f"miembro cifrado prohibido: {info.filename}")
                _invariant(info.file_size <= MAX_MEMBER_BYTES, f"miembro demasiado grande: {info.filename}")
                mode = info.external_attr >> 16
                _invariant((mode & 0o170000) != 0o120000, f"enlace simbólico prohibido: {info.filename}")
            items_bytes = archive.read("items.json")
            icon_bytes = archive.read("res/previfoc.png")
            _invariant(archive.testzip() is None, "CRC ZIP inválido")
    except (BadZipFile, KeyError, OSError) as exc:
        raise PackageError(f"ZIP inválido: {exc}") from exc
    _invariant(items_bytes == _json_bytes(config), "items.json no coincide exactamente con la configuración aprobada")
    try:
        document = json.loads(items_bytes)
    except json.JSONDecodeError as exc:
        raise PackageError(f"items.json inválido: {exc}") from exc
    _invariant(document == _items_document(config), "contrato items.json alterado")
    _validate_icon(icon_bytes)
    sources = document["items"][2]["items"]
    _invariant(len(sources) == 2, "el paquete debe contener hoy y mañana")
    for source in sources:
        _invariant(source["sql"] is False and source["inverted_y"] is False, "cada fuente debe ser XYZ remota, no SQLite ni TMS")
        _invariant(source["timesupported"] is True and source["expire"] == 60, "caducidad de 60 minutos ausente")
        _invariant(source["minZoom"] == 6 and source["maxZoom"] == 14, "rango de zoom alterado")
    result = {
        "artifact": str(package_path),
        "artifact_version": config["artifact_version"],
        "sha256": _sha256(package_bytes),
        "bytes": len(package_bytes),
        "members": names,
        "items_sha256": _sha256(items_bytes),
        "icon_sha256": _sha256(icon_bytes),
        "tile_urls": [source["url"] for source in sources],
        "source_names": [source["name"] for source in sources],
        "zoom": [sources[0]["minZoom"], sources[0]["maxZoom"]],
        "expire_minutes": sources[0]["expire"],
    }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "validate"):
        child = subparsers.add_parser(command)
        child.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        child.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build(args.config, args.output) if args.command == "build" else validate(args.output, args.config)
    except PackageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
