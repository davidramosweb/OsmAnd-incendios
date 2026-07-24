from __future__ import annotations

import io
import json
from pathlib import Path
import threading
import unittest

from tools import osmand_http_check, osmand_xyz_server


class OsmAndXYZPureTests(unittest.TestCase):
    def test_route_contract(self) -> None:
        parsed = osmand_xyz_server.parse_tile_request("/tiles/14/8213/6173.png")
        self.assertEqual((14, 8213, 6173), (parsed.zoom, parsed.x, parsed.y))
        self.assertEqual("14/8213/6173.png", parsed.relative)
        public = osmand_xyz_server.parse_tile_request(
            "/osmand-001/tiles/14/8213/6173.png"
        )
        self.assertEqual(parsed, public)
        for path, message in (
            ("/tiles/5/31/24.png", "zoom_fuera_de_rango"),
            ("/tiles/6/31.0/24.png", "coordenada_no_entera_o_negativa"),
            ("/tiles/6/-1/24.png", "coordenada_no_entera_o_negativa"),
            ("/tiles/6/64/24.png", "coordenada_fuera_de_rango"),
            ("/tiles/6/31/64.png", "coordenada_fuera_de_rango"),
            ("/otra/ruta", "ruta_desconocida"),
        ):
            with self.subTest(path=path), self.assertRaisesRegex(
                osmand_xyz_server.OsmAndServerError, message
            ):
                osmand_xyz_server.parse_tile_request(path)

    def test_magic_url_uses_xyz_placeholders(self) -> None:
        value = osmand_http_check.magic_url("https://tiles.example.test")
        self.assertTrue(value.startswith("https://osmand.net/add-tile-source?"))
        self.assertIn("min_zoom=6", value)
        self.assertIn("max_zoom=14", value)
        self.assertIn("%7B0%7D%2F%7B1%7D%2F%7B2%7D.png", value)


class OsmAndXYZHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.logs = io.StringIO()
        cls.tile_set = osmand_xyz_server.load_frozen_tiles()
        cls.server = osmand_xyz_server.build_server(
            "127.0.0.1", 0, cls.tile_set, log_stream=cls.logs
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_full_http_acceptance_matrix(self) -> None:
        results = osmand_http_check.run_checks(self.base_url, timeout=5)
        statuses = {item["name"]: item["status"] for item in results}
        self.assertEqual(200, statuses["covered_z6"])
        self.assertEqual(200, statuses["outside_z6"])
        self.assertEqual(404, statuses["invalid_zoom"])
        self.assertEqual(400, statuses["invalid_x_noninteger"])
        self.assertEqual(400, statuses["invalid_y_negative"])
        self.assertEqual(400, statuses["invalid_x_bounds"])
        self.assertEqual(400, statuses["invalid_y_bounds"])
        self.assertEqual(200, statuses["covered_z14"])
        self.assertEqual(200, statuses["tms_mirror_z14"])

    def test_jsonl_logs_cover_success_fallback_and_error(self) -> None:
        osmand_http_check.run_checks(self.base_url, timeout=5)
        records = [json.loads(line) for line in self.logs.getvalue().splitlines()]
        outcomes = {record["outcome"] for record in records}
        self.assertIn("covered_tile", outcomes)
        self.assertIn("transparent_fallback", outcomes)
        self.assertIn("zoom_fuera_de_rango", outcomes)
        self.assertTrue(all(record["event"] == "http_request" for record in records))

    def test_frozen_tiles_are_only_read(self) -> None:
        before = {
            relative: (osmand_xyz_server.DEFAULT_TILE_ROOT / relative).stat().st_mtime_ns
            for relative in ("manifest.json", "tiles.sha256", "transparent.png", "6/31/24.png")
        }
        osmand_xyz_server.load_frozen_tiles()
        after = {
            relative: (osmand_xyz_server.DEFAULT_TILE_ROOT / relative).stat().st_mtime_ns
            for relative in before
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
