from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.osmand_package import DEFAULT_CONFIG, DEFAULT_OUTPUT, PackageError, build, validate


class OsmandPackageTests(unittest.TestCase):
    def test_versioned_package_is_valid(self) -> None:
        result = validate()
        self.assertEqual([6, 14], result["zoom"])
        self.assertEqual(60, result["expire_minutes"])
        self.assertEqual(
            [
                "https://previfoc.davidramosweb.com/tiles/current/{0}/{1}/{2}.png",
                "https://previfoc.davidramosweb.com/tiles/forecast-next-day/{0}/{1}/{2}.png",
            ],
            result["tile_urls"],
        )
        self.assertEqual(
            ["PREVIFOC — Hoy (no oficial)", "PREVIFOC — Mañana (previsión)"],
            result["source_names"],
        )

    def test_build_is_byte_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.osf"
            second = Path(temporary) / "second.osf"
            build(DEFAULT_CONFIG, first)
            build(DEFAULT_CONFIG, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(DEFAULT_OUTPUT.read_bytes(), first.read_bytes())

    def test_archive_contains_only_configuration_and_icon(self) -> None:
        with ZipFile(DEFAULT_OUTPUT) as archive:
            self.assertEqual(["items.json", "res/previfoc.png"], archive.namelist())
            document = json.loads(archive.read("items.json"))
        self.assertEqual(["PLUGIN", "RESOURCES", "MAP_SOURCES"], [item["type"] for item in document["items"]])
        self.assertEqual(2, len(document["items"][2]["items"]))
        serialized = json.dumps(document)
        self.assertNotIn("sqlitedb", serialized)
        self.assertNotIn("tiles/6/", serialized)

    def test_changed_public_origin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "config.json"
            config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
            config["public_origin"] = "http://example.test"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(PackageError, "public_origin debe ser HTTPS"):
                build(config_path, Path(temporary) / "bad.osf")

    def test_tampered_items_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "tampered.osf"
            with ZipFile(DEFAULT_OUTPUT) as source, ZipFile(target, "w") as output:
                document = json.loads(source.read("items.json"))
                document["items"][2]["items"][0]["expire"] = 5
                output.writestr("items.json", json.dumps(document))
                output.writestr("res/previfoc.png", source.read("res/previfoc.png"))
            with self.assertRaisesRegex(PackageError, "items.json no coincide"):
                validate(target)

    def test_extra_or_traversal_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "unsafe.osf"
            with ZipFile(DEFAULT_OUTPUT) as source, ZipFile(target, "w") as output:
                output.writestr("items.json", source.read("items.json"))
                output.writestr("res/previfoc.png", source.read("res/previfoc.png"))
                output.writestr("../tile.png", b"not allowed")
            with self.assertRaisesRegex(PackageError, "contenido ZIP inesperado"):
                validate(target)


if __name__ == "__main__":
    unittest.main()
