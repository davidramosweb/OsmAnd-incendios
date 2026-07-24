#!/usr/bin/env python3
"""Comprueba por HTTP la fuente XYZ temporal de OSMAND-001."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TILE_ROOT = PROJECT_ROOT / "data" / "tiles-002"
EXPECTED_CACHE_CONTROL = "private, max-age=300, must-revalidate"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class HTTPCheckError(RuntimeError):
    """Una respuesta HTTP incumple OSMAND-001."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    final_url: str


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def fetch(url: str, timeout: float) -> Response:
    request = Request(
        url,
        headers={
            "Accept": "image/png",
            "Origin": "https://osmand-check.invalid",
            "User-Agent": "OSMAND-001-http-check/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
                final_url=response.geturl(),
            )
    except HTTPError as exc:
        return Response(
            status=exc.code,
            headers={key.lower(): value for key, value in exc.headers.items()},
            body=exc.read(),
            final_url=exc.geturl(),
        )
    except (OSError, URLError) as exc:
        raise HTTPCheckError(f"no se puede solicitar {url}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HTTPCheckError(message)


def _check_png_headers(name: str, response: Response) -> None:
    _require(response.status == 200, f"{name}: HTTP {response.status}, se esperaba 200")
    _require(response.headers.get("content-type") == "image/png", f"{name}: Content-Type invalido")
    _require(response.headers.get("access-control-allow-origin") == "*", f"{name}: CORS invalido")
    _require(
        response.headers.get("cache-control") == EXPECTED_CACHE_CONTROL,
        f"{name}: Cache-Control invalido",
    )
    _require(response.body.startswith(PNG_SIGNATURE), f"{name}: cuerpo sin firma PNG")
    _require(
        response.headers.get("content-length") == str(len(response.body)),
        f"{name}: Content-Length invalido",
    )


def _check_error(name: str, response: Response, expected_status: int) -> None:
    _require(
        response.status == expected_status,
        f"{name}: HTTP {response.status}, se esperaba {expected_status}",
    )
    _require(
        response.headers.get("content-type") == "text/plain; charset=utf-8",
        f"{name}: error no es text/plain",
    )
    _require(response.headers.get("cache-control") == "no-store", f"{name}: error cacheable")
    _require(response.headers.get("access-control-allow-origin") == "*", f"{name}: CORS invalido")
    _require(b"<html" not in response.body.lower(), f"{name}: respuesta HTML ambigua")


def run_checks(
    base_url: str,
    *,
    tile_root: Path = DEFAULT_TILE_ROOT,
    timeout: float = 10.0,
    require_https: bool = False,
) -> list[dict[str, object]]:
    parsed_base = urlsplit(base_url)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        raise HTTPCheckError("base_url debe ser una URL HTTP(S) absoluta")
    if require_https and parsed_base.scheme != "https":
        raise HTTPCheckError("la comprobacion final exige HTTPS")
    normalized_base = base_url.rstrip("/") + "/"
    root = tile_root.resolve()
    transparent = (root / "transparent.png").read_bytes()

    cases = (
        ("covered_z6", "tiles/6/31/24.png"),
        ("outside_z6", "tiles/6/30/24.png"),
        ("invalid_zoom", "tiles/5/31/24.png"),
        ("invalid_x_noninteger", "tiles/6/31.5/24.png"),
        ("invalid_y_negative", "tiles/6/31/-1.png"),
        ("invalid_x_bounds", "tiles/6/64/24.png"),
        ("invalid_y_bounds", "tiles/6/31/64.png"),
        ("covered_z14", "tiles/14/8213/6173.png"),
        ("tms_mirror_z14", "tiles/14/8213/10210.png"),
    )
    responses = {
        name: fetch(urljoin(normalized_base, path), timeout)
        for name, path in cases
    }
    if require_https:
        for name, response in responses.items():
            _require(
                urlsplit(response.final_url).scheme == "https",
                f"{name}: la respuesta final dejo de usar HTTPS",
            )

    low = responses["covered_z6"]
    _check_png_headers("covered_z6", low)
    _require(low.body == (root / "6/31/24.png").read_bytes(), "covered_z6: bytes modificados")
    _require(low.body != transparent, "covered_z6: se recibio fallback transparente")

    outside = responses["outside_z6"]
    _check_png_headers("outside_z6", outside)
    _require(outside.body == transparent, "outside_z6: no es transparent.png exacto")

    _check_error("invalid_zoom", responses["invalid_zoom"], 404)
    _check_error("invalid_x_noninteger", responses["invalid_x_noninteger"], 400)
    _check_error("invalid_y_negative", responses["invalid_y_negative"], 400)
    _check_error("invalid_x_bounds", responses["invalid_x_bounds"], 400)
    _check_error("invalid_y_bounds", responses["invalid_y_bounds"], 400)

    high = responses["covered_z14"]
    _check_png_headers("covered_z14", high)
    _require(high.body == (root / "14/8213/6173.png").read_bytes(), "covered_z14: bytes modificados")
    _require(high.body != transparent, "covered_z14: se recibio fallback transparente")

    tms_mirror = responses["tms_mirror_z14"]
    _check_png_headers("tms_mirror_z14", tms_mirror)
    _require(tms_mirror.body == transparent, "tms_mirror_z14: parece haberse invertido Y")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    orientation = manifest["verification"]["geographic"]["orientation_xyz"]
    _require(orientation["passes"] is True, "manifiesto: orientacion XYZ no aprobada")
    _require(orientation["north_y"] < orientation["south_y"], "manifiesto: Y no crece al sur")

    return [
        {
            "name": name,
            "path": path,
            "status": responses[name].status,
            "content_type": responses[name].headers.get("content-type"),
            "cache_control": responses[name].headers.get("cache-control"),
            "cors": responses[name].headers.get("access-control-allow-origin"),
            "response_bytes": len(responses[name].body),
            "sha256": sha256_bytes(responses[name].body),
        }
        for name, path in cases
    ]


def magic_url(base_url: str, name: str = "PREVIFOC prueba temporal") -> str:
    tile_template = base_url.rstrip("/") + "/tiles/{0}/{1}/{2}.png"
    return (
        "https://osmand.net/add-tile-source?"
        f"name={quote(name, safe='')}&min_zoom=6&max_zoom=14&"
        f"url_template={quote(tile_template, safe='')}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="origen, sin /tiles; por ejemplo https://tiles.example")
    parser.add_argument("--tile-root", type=Path, default=DEFAULT_TILE_ROOT)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--require-https", action="store_true")
    parser.add_argument("--print-magic-url", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        results = run_checks(
            args.base_url,
            tile_root=args.tile_root,
            timeout=args.timeout,
            require_https=args.require_https,
        )
    except (HTTPCheckError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"OSMAND-001 HTTP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"base_url": args.base_url, "checks": results}, ensure_ascii=False, indent=2))
    if args.print_magic_url:
        print(magic_url(args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
