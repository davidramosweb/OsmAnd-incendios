from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
import unittest

from tools import geo_sources


def _multipolygon_blob(srs_id: int = 25830) -> bytes:
    points = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0))
    ring = struct.pack("<I", len(points)) + b"".join(
        struct.pack("<dd", x, y) for x, y in points
    )
    polygon = b"\x01" + struct.pack("<II", 3, 1) + ring
    multipolygon = b"\x01" + struct.pack("<II", 6, 1) + polygon
    return b"GP\x00\x01" + struct.pack("<i", srs_id) + multipolygon


def _create_gpkg(path: Path, *, empty_geometry: bool = False) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            PRAGMA application_id = 1196444487;
            PRAGMA user_version = 10200;
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
              min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
              srs_id INTEGER
            );
            CREATE TABLE gpkg_geometry_columns (
              table_name TEXT NOT NULL,
              column_name TEXT NOT NULL,
              geometry_type_name TEXT NOT NULL,
              srs_id INTEGER NOT NULL,
              z TINYINT NOT NULL,
              m TINYINT NOT NULL,
              PRIMARY KEY (table_name, column_name)
            );
            CREATE TABLE "ICV.Municipios" (
              fid INTEGER PRIMARY KEY,
              geom MULTIPOLYGON,
              cod_ine_mun TEXT,
              nom_mun TEXT,
              nom_mun_cas TEXT,
              nom_mun_val TEXT,
              noms_mun TEXT
            );
            INSERT INTO gpkg_spatial_ref_sys VALUES
              ('ETRS89 / UTM zone 30N', 25830, 'EPSG', 25830,
               'PROJCS["ETRS89 / UTM zone 30N"]', 'fixture');
            INSERT INTO gpkg_contents VALUES
              ('ICV.Municipios', 'features', 'ICV.Municipios', '',
               '2026-01-01T00:00:00.000Z', 0, 0, 3, 3, 25830);
            INSERT INTO gpkg_geometry_columns VALUES
              ('ICV.Municipios', 'geom', 'MULTIPOLYGON', 25830, 0, 0);
            """
        )
        blob = _multipolygon_blob()
        if empty_geometry:
            blob = blob[:3] + bytes([blob[3] | 0x10]) + blob[4:]
        rows = (
            (1, blob, "00001", "Ademuz", "Ademuz", "Ademuz", "Ademuz"),
            (2, blob, "00002", "València", "València", "València", "València"),
            (
                3,
                blob,
                "00003",
                "Alacant",
                "Alicante",
                "Alacant",
                "Alacant/Alicante",
            ),
        )
        connection.executemany(
            'INSERT INTO "ICV.Municipios" VALUES (?, ?, ?, ?, ?, ?, ?)', rows
        )
        connection.commit()
    finally:
        connection.close()


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple[int, str, bytes]] = {}

    def do_GET(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        status, content_type, body = self.routes.get(
            self.path, (404, "text/plain", b"not found")
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


class GeoSourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gpkg = self.root / "fixture.gpkg"
        _create_gpkg(self.gpkg)
        self.municipios = [
            {
                "municipio": "Ademuz",
                "idZonaPrevifoc": 53,
                "idZonaAvisoMeteo": 1,
                "idZonaEmergencia": 1,
            },
            {
                "municipio": "València",
                "idZonaPrevifoc": 53,
                "idZonaAvisoMeteo": 2,
                "idZonaEmergencia": 2,
            },
            {
                "municipio": "Alacant/Alicante",
                "idZonaPrevifoc": 54,
                "idZonaAvisoMeteo": 3,
                "idZonaEmergencia": 3,
            },
            {
                "municipio": "Fuera C.V.",
                "idZonaPrevifoc": 0,
                "idZonaAvisoMeteo": 0,
                "idZonaEmergencia": 0,
            },
        ]
        _Handler.routes = {
            "/municipios": (
                200,
                "application/json",
                json.dumps(self.municipios, ensure_ascii=False).encode(),
            ),
            "/icv": (
                200,
                "application/geopackage+sqlite3",
                self.gpkg.read_bytes(),
            ),
        }
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.config = self.root / "config.json"
        self.output = self.root / "sources"
        self._write_config(base_url)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def _write_config(self, base_url: str) -> None:
        config = {
            "schema_version": 1,
            "client": {"timeout_seconds": 5, "user_agent": "geo-test/1"},
            "sources": {
                "municipios_112cv": {
                    "accept": "application/json",
                    "expected": {
                        "allowed_zone_ids": [53, 54],
                        "assigned_municipalities": 3,
                        "outside_record": self.municipios[-1],
                        "required_fields": list(self.municipios[0]),
                        "zone_counts": {"53": 2, "54": 1},
                    },
                    "file_extension": "json",
                    "kind": "municipios_json",
                    "license": {"status": "fixture"},
                    "manual_sample_values": [
                        "Ademuz",
                        "València",
                        "Alacant/Alicante",
                    ],
                    "max_bytes": 10000,
                    "publisher": "fixture",
                    "url": f"{base_url}/municipios",
                },
                "icv_municipios": {
                    "accept": "application/geopackage+sqlite3",
                    "expected": {
                        "code_field": "cod_ine_mun",
                        "crs": {
                            "organization": "EPSG",
                            "organization_coordsys_id": 25830,
                        },
                        "feature_count": 3,
                        "geometry_type": "MULTIPOLYGON",
                        "layer": "ICV.Municipios",
                        "name_field": "nom_mun",
                        "required_fields": [
                            "fid",
                            "geom",
                            "cod_ine_mun",
                            "nom_mun",
                        ],
                    },
                    "file_extension": "gpkg",
                    "kind": "geopackage",
                    "license": {"status": "fixture"},
                    "manual_sample_field": "noms_mun",
                    "manual_sample_values": [
                        "Ademuz",
                        "València",
                        "Alacant/Alicante",
                    ],
                    "max_bytes": 1000000,
                    "publisher": "fixture",
                    "url": f"{base_url}/icv",
                },
            },
        }
        self.config.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_download_is_content_addressed_and_repeatable(self) -> None:
        first = geo_sources.download_sources(self.config, self.output)
        second = geo_sources.download_sources(self.config, self.output)
        for source_id in first["sources"]:
            first_record = first["sources"][source_id]
            second_record = second["sources"][source_id]
            self.assertEqual(first_record["sha256"], second_record["sha256"])
            self.assertEqual(
                first_record["inspection"]["dataset_content_sha256"],
                second_record["inspection"]["dataset_content_sha256"],
            )
            self.assertEqual(first_record["snapshot"], second_record["snapshot"])
            snapshot = self.output / first_record["snapshot"]
            self.assertEqual(
                hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                first_record["sha256"],
            )
        self.assertTrue((self.output / "manifest.json").is_file())
        self.assertTrue((self.output / "REPORT.md").is_file())
        geo_sources.validate_manifest(self.config, self.output / "manifest.json")

    def test_http_error_preserves_last_valid_manifest_and_snapshots(self) -> None:
        geo_sources.download_sources(self.config, self.output)
        manifest_before = (self.output / "manifest.json").read_bytes()
        snapshots_before = sorted(
            path.relative_to(self.output)
            for path in (self.output / "snapshots").rglob("*")
            if path.is_file()
        )
        _Handler.routes["/municipios"] = (503, "text/plain", b"unavailable")
        with self.assertRaises(geo_sources.DownloadError):
            geo_sources.download_sources(self.config, self.output)
        self.assertEqual(
            2,
            geo_sources.main(
                [
                    "download",
                    "--config",
                    str(self.config),
                    "--output",
                    str(self.output),
                ]
            ),
        )
        self.assertEqual(manifest_before, (self.output / "manifest.json").read_bytes())
        self.assertEqual(
            snapshots_before,
            sorted(
                path.relative_to(self.output)
                for path in (self.output / "snapshots").rglob("*")
                if path.is_file()
            ),
        )

    def test_unexpected_file_preserves_last_valid_manifest(self) -> None:
        geo_sources.download_sources(self.config, self.output)
        manifest_before = (self.output / "manifest.json").read_bytes()
        _Handler.routes["/icv"] = (200, "text/html", b"<html>error</html>")
        with self.assertRaises(geo_sources.ValidationError):
            geo_sources.download_sources(self.config, self.output)
        self.assertEqual(
            2,
            geo_sources.main(
                [
                    "download",
                    "--config",
                    str(self.config),
                    "--output",
                    str(self.output),
                ]
            ),
        )
        self.assertEqual(manifest_before, (self.output / "manifest.json").read_bytes())

    def test_empty_geometry_is_rejected(self) -> None:
        invalid = self.root / "empty.gpkg"
        _create_gpkg(invalid, empty_geometry=True)
        source = json.loads(self.config.read_text())["sources"]["icv_municipios"]
        with self.assertRaisesRegex(geo_sources.ValidationError, "vacia"):
            geo_sources._validate_gpkg(invalid, source)

    def test_invalid_municipality_count_is_rejected(self) -> None:
        invalid = self.root / "bad.json"
        invalid.write_text(json.dumps(self.municipios[:-1]), encoding="utf-8")
        source = json.loads(self.config.read_text())["sources"]["municipios_112cv"]
        with self.assertRaises(geo_sources.ValidationError):
            geo_sources._validate_municipios(invalid, source)

    def test_hash_is_stable_for_identical_bytes(self) -> None:
        path = self.root / "same.bin"
        path.write_bytes(b"identical content\n")
        first = geo_sources.sha256_file(path)
        second = geo_sources.sha256_file(path)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
