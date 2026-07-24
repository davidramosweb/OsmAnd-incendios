#!/usr/bin/env python3
"""Sirve por HTTP la piramide XYZ congelada para la prueba OSMAND-001."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import time
from typing import TextIO
from urllib.parse import urlsplit
import uuid


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TILE_ROOT = PROJECT_ROOT / "data" / "tiles-002"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

MIN_ZOOM = 6
MAX_ZOOM = 14
CACHE_CONTROL = "private, max-age=300, must-revalidate"
CORS_ORIGIN = "*"

GEOMETRY_VERSION = (
    "sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0"
)
FORMAT_VERSION = "previfoc-indexed-template-v2"
EXPECTED_TILE_COUNT = 9_507
EXPECTED_MANIFEST_SHA256 = "bf441e744a7b82d63b455ca4ec66a92afb8e2611d4d4d918dc88b3c738c98cd2"
EXPECTED_INVENTORY_SHA256 = "464e34c9db51811977898fea42d5b17c2ba0e5b25d09feb292aac60790121480"
EXPECTED_TRANSPARENT_SHA256 = "679644f8ef3768bbe373bc2db7d50c3d9f133013cb927154fc920a4471616809"

_TILE_ROUTE_RE = re.compile(r"^/(?:osmand-001/)?tiles/([^/]+)/([^/]+)/([^/]+)\.png$")
_INVENTORY_RE = re.compile(r"^([0-9a-f]{64})  ([^\s]+)$")
_CANONICAL_INTEGER_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")


class OsmAndServerError(RuntimeError):
    """Fallo de integridad o configuracion del servidor temporal."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise OsmAndServerError(f"no se puede leer {path}: {exc}") from exc
    return digest.hexdigest()


@dataclass(frozen=True)
class FrozenTileSet:
    root: Path
    inventory: dict[str, str]
    transparent: bytes


def _validate_inventory_path(relative: str) -> tuple[int, int, int]:
    parts = relative.split("/")
    if len(parts) != 3 or not parts[2].endswith(".png"):
        raise OsmAndServerError(f"ruta no XYZ en inventario: {relative}")
    raw_zoom, raw_x, filename = parts
    raw_y = filename[:-4]
    if not all(_CANONICAL_INTEGER_RE.fullmatch(value) for value in (raw_zoom, raw_x, raw_y)):
        raise OsmAndServerError(f"coordenada no canonica en inventario: {relative}")
    zoom, x, y = int(raw_zoom), int(raw_x), int(raw_y)
    if not MIN_ZOOM <= zoom <= MAX_ZOOM:
        raise OsmAndServerError(f"zoom fuera de {MIN_ZOOM}-{MAX_ZOOM}: {relative}")
    limit = 1 << zoom
    if not (0 <= x < limit and 0 <= y < limit):
        raise OsmAndServerError(f"coordenada fuera del mundo XYZ: {relative}")
    return zoom, x, y


def load_frozen_tiles(tile_root: Path = DEFAULT_TILE_ROOT) -> FrozenTileSet:
    """Valida todo TILES-002 sin modificarlo y devuelve su inventario en memoria."""

    root = tile_root.resolve()
    manifest_path = root / "manifest.json"
    inventory_path = root / "tiles.sha256"
    transparent_path = root / "transparent.png"

    if sha256_file(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise OsmAndServerError("SHA-256 inesperado para manifest.json de TILES-002")
    if sha256_file(inventory_path) != EXPECTED_INVENTORY_SHA256:
        raise OsmAndServerError("SHA-256 inesperado para tiles.sha256 de TILES-002")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OsmAndServerError(f"manifest.json no se puede analizar: {exc}") from exc
    pyramid = manifest.get("pyramid", {})
    if manifest.get("geometry_version") != GEOMETRY_VERSION:
        raise OsmAndServerError("geometry_version inesperada en TILES-002")
    if manifest.get("format_version") != FORMAT_VERSION:
        raise OsmAndServerError("format_version inesperada en TILES-002")
    if pyramid.get("path_template") != "{z}/{x}/{y}.png":
        raise OsmAndServerError("plantilla de ruta inesperada en TILES-002")
    if pyramid.get("xyz_y_axis") != "north_to_south_not_inverted":
        raise OsmAndServerError("TILES-002 no declara XYZ norte-sur")
    if pyramid.get("zooms") != [MIN_ZOOM, MAX_ZOOM]:
        raise OsmAndServerError("rango de zoom inesperado en TILES-002")
    if pyramid.get("tile_assets") != EXPECTED_TILE_COUNT:
        raise OsmAndServerError("conteo de teselas inesperado en TILES-002")

    try:
        lines = inventory_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise OsmAndServerError(f"tiles.sha256 no se puede leer: {exc}") from exc
    if len(lines) != EXPECTED_TILE_COUNT:
        raise OsmAndServerError(
            f"inventario con {len(lines)} rutas; se esperaban {EXPECTED_TILE_COUNT}"
        )

    inventory: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        match = _INVENTORY_RE.fullmatch(line)
        if match is None:
            raise OsmAndServerError(f"linea {line_number} invalida en tiles.sha256")
        expected_digest, relative = match.groups()
        _validate_inventory_path(relative)
        if relative in inventory:
            raise OsmAndServerError(f"ruta duplicada en inventario: {relative}")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise OsmAndServerError(f"tesela ausente o enlace no permitido: {relative}")
        observed_digest = sha256_file(path)
        if observed_digest != expected_digest:
            raise OsmAndServerError(f"SHA-256 inesperado para tesela: {relative}")
        inventory[relative] = expected_digest

    actual_paths = {
        path.relative_to(root).as_posix()
        for zoom in range(MIN_ZOOM, MAX_ZOOM + 1)
        for path in (root / str(zoom)).rglob("*.png")
        if path.is_file()
    }
    expected_paths = set(inventory)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)[:3]
        extra = sorted(actual_paths - expected_paths)[:3]
        raise OsmAndServerError(f"rutas distintas al inventario; faltan={missing}; sobran={extra}")

    try:
        transparent = transparent_path.read_bytes()
    except OSError as exc:
        raise OsmAndServerError(f"no se puede leer transparent.png: {exc}") from exc
    if sha256_bytes(transparent) != EXPECTED_TRANSPARENT_SHA256:
        raise OsmAndServerError("SHA-256 inesperado para transparent.png de TILES-002")
    return FrozenTileSet(root=root, inventory=inventory, transparent=transparent)


@dataclass(frozen=True)
class ParsedTileRequest:
    zoom: int
    x: int
    y: int
    relative: str


def parse_tile_request(path: str) -> ParsedTileRequest:
    """Analiza una ruta HTTP y distingue formato, zoom y limites XYZ."""

    match = _TILE_ROUTE_RE.fullmatch(path)
    if match is None:
        raise OsmAndServerError("ruta_desconocida")
    raw_zoom, raw_x, raw_y = match.groups()
    if not all(_CANONICAL_INTEGER_RE.fullmatch(value) for value in (raw_zoom, raw_x, raw_y)):
        raise OsmAndServerError("coordenada_no_entera_o_negativa")
    zoom, x, y = int(raw_zoom), int(raw_x), int(raw_y)
    if not MIN_ZOOM <= zoom <= MAX_ZOOM:
        raise OsmAndServerError("zoom_fuera_de_rango")
    limit = 1 << zoom
    if not (0 <= x < limit and 0 <= y < limit):
        raise OsmAndServerError("coordenada_fuera_de_rango")
    return ParsedTileRequest(zoom, x, y, f"{zoom}/{x}/{y}.png")


class TileHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        tile_set: FrozenTileSet,
        log_stream: TextIO = sys.stdout,
    ) -> None:
        self.tile_set = tile_set
        self.log_stream = log_stream
        super().__init__(server_address, OsmAndTileHandler)

    def write_log(self, record: dict[str, object]) -> None:
        print(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            file=self.log_stream,
            flush=True,
        )

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        self.write_log(
            {
                "event": "server_error",
                "client_ip": client_address[0],
                "time": datetime.now(timezone.utc).isoformat(),
            }
        )
        super().handle_error(request, client_address)


class OsmAndTileHandler(BaseHTTPRequestHandler):
    server: TileHTTPServer
    server_version = "OSMAND-001/1.0"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        # Toda la telemetria necesaria se emite como JSONL en _handle.
        return

    def do_GET(self) -> None:  # noqa: N802 - nombre exigido por BaseHTTPRequestHandler
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle(send_body=False)

    def do_OPTIONS(self) -> None:  # noqa: N802
        request_id = uuid.uuid4().hex
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Max-Age", "300")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", request_id)
        self.send_header("Content-Length", "0")
        self.end_headers()
        self._log_request(request_id, 204, "options", 0, 0.0)

    def _handle(self, *, send_body: bool) -> None:
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        raw_path = urlsplit(self.path).path
        try:
            request = parse_tile_request(raw_path)
        except OsmAndServerError as exc:
            error = str(exc)
            status = 404 if error in {"ruta_desconocida", "zoom_fuera_de_rango"} else 400
            body = (error + "\n").encode("utf-8")
            self._send_bytes(
                status,
                body,
                "text/plain; charset=utf-8",
                "no-store",
                request_id,
                "error",
                send_body,
            )
            self._log_request(request_id, status, error, len(body), started)
            return

        expected_digest = self.server.tile_set.inventory.get(request.relative)
        if expected_digest is None:
            body = self.server.tile_set.transparent
            outcome = "transparent_fallback"
        else:
            try:
                body = (self.server.tile_set.root / request.relative).read_bytes()
            except OSError:
                self._integrity_error(request_id, started, send_body, "tile_read_error")
                return
            if sha256_bytes(body) != expected_digest:
                self._integrity_error(request_id, started, send_body, "tile_integrity_error")
                return
            outcome = "covered_tile"

        self._send_bytes(
            200,
            body,
            "image/png",
            CACHE_CONTROL,
            request_id,
            outcome,
            send_body,
        )
        self._log_request(request_id, 200, outcome, len(body), started, request)

    def _integrity_error(
        self, request_id: str, started: float, send_body: bool, outcome: str
    ) -> None:
        body = (outcome + "\n").encode("ascii")
        self._send_bytes(
            500,
            body,
            "text/plain; charset=utf-8",
            "no-store",
            request_id,
            "error",
            send_body,
        )
        self._log_request(request_id, 500, outcome, len(body), started)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        cache_control: str,
        request_id: str,
        result: str,
        send_body: bool,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Request-ID", request_id)
        self.send_header("X-OSMAND-001-Result", result)
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _log_request(
        self,
        request_id: str,
        status: int,
        outcome: str,
        response_bytes: int,
        started: float,
        tile: ParsedTileRequest | None = None,
    ) -> None:
        elapsed_ms = 0.0 if started == 0.0 else round((time.monotonic() - started) * 1000, 3)
        forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        record: dict[str, object] = {
            "cache_control": CACHE_CONTROL if status == 200 else "no-store",
            "client_ip": forwarded or self.client_address[0],
            "elapsed_ms": elapsed_ms,
            "event": "http_request",
            "method": self.command,
            "outcome": outcome,
            "path": urlsplit(self.path).path,
            "request_id": request_id,
            "response_bytes": response_bytes,
            "status": status,
            "time": datetime.now(timezone.utc).isoformat(),
            "user_agent": self.headers.get("User-Agent", ""),
        }
        if tile is not None:
            record["xyz"] = [tile.zoom, tile.x, tile.y]
        self.server.write_log(record)


def build_server(
    host: str,
    port: int,
    tile_set: FrozenTileSet,
    *,
    log_stream: TextIO = sys.stdout,
) -> TileHTTPServer:
    return TileHTTPServer((host, port), tile_set, log_stream)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("serve", "validate"),
        nargs="?",
        default="serve",
        help="serve inicia HTTP; validate solo comprueba TILES-002",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tile-root", type=Path, default=DEFAULT_TILE_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        tile_set = load_frozen_tiles(args.tile_root)
    except OsmAndServerError as exc:
        print(f"OSMAND-001: {exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(
            f"TILES-002 inmutable: {len(tile_set.inventory)} teselas; "
            f"transparent.png={EXPECTED_TRANSPARENT_SHA256}"
        )
        return 0

    server = build_server(args.host, args.port, tile_set)
    host, port = server.server_address[:2]
    server.write_log(
        {
            "cache_control": CACHE_CONTROL,
            "cors": CORS_ORIGIN,
            "event": "server_started",
            "listen": f"http://{host}:{port}",
            "tile_count": len(tile_set.inventory),
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
