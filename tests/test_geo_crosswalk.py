from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools import geo_crosswalk


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


class CrosswalkFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_dir = root / "config"
        self.sources_dir = root / "data" / "sources"
        self.snapshots_dir = self.sources_dir / "snapshots"
        self.output_dir = root / "data" / "crosswalk"
        self.config_dir.mkdir(parents=True)
        self.snapshots_dir.mkdir(parents=True)
        self.municipalities = [
            {
                "municipio": "Ademuz",
                "idZonaPrevifoc": 53,
                "idZonaAvisoMeteo": 1,
                "idZonaEmergencia": 1,
            },
            {
                "municipio": "Alacant/Alicante",
                "idZonaPrevifoc": 53,
                "idZonaAvisoMeteo": 2,
                "idZonaEmergencia": 2,
            },
            {
                "municipio": "Alfarp",
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
        self.icv_rows = [
            (
                "00001",
                b"geometry-1",
                "Ademuz",
                "Ademuz",
                "Ademuz",
                "Ademuz",
                "Ademuz",
                "Ademuz",
            ),
            (
                "00002",
                b"geometry-2",
                "Alacant",
                "Alicante",
                "Alicante",
                "Alacant",
                "Alacant",
                "Alacant/Alicante",
            ),
            (
                "00003",
                b"geometry-3",
                "Alfarb",
                "Alfarb",
                "Alfarb",
                "Alfarb",
                "Alfarb",
                "Alfarb",
            ),
        ]
        self.raw_112 = self.snapshots_dir / "municipios.json"
        self.raw_icv = self.snapshots_dir / "municipios.gpkg"
        self.manifest_path = self.sources_dir / "manifest.json"
        self.aliases_path = self.config_dir / "aliases.json"
        self.reviews_path = self.config_dir / "reviews.csv"
        self.config_path = self.config_dir / "crosswalk.json"
        self._write_sources()
        self._write_metadata()

    def _write_sources(self) -> None:
        self.raw_112.write_bytes(_json_bytes(self.municipalities))
        connection = sqlite3.connect(self.raw_icv)
        try:
            connection.execute(
                """
                CREATE TABLE "ICV.Municipios" (
                  cod_ine_mun TEXT,
                  geom BLOB,
                  nom_mun TEXT,
                  nom_mun_cas TEXT,
                  nom_mun_cas_a TEXT,
                  nom_mun_val TEXT,
                  nom_mun_val_a TEXT,
                  noms_mun TEXT
                )
                """
            )
            connection.executemany(
                'INSERT INTO "ICV.Municipios" VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                self.icv_rows,
            )
            connection.commit()
        finally:
            connection.close()

    def _write_metadata(self) -> None:
        sha_112 = geo_crosswalk.sha256_file(self.raw_112)
        sha_icv = geo_crosswalk.sha256_file(self.raw_icv)
        logical_112 = "1" * 64
        logical_icv = "2" * 64
        manifest = {
            "manifest_schema_version": 1,
            "sources": {
                "municipios_112cv": {
                    "inspection": {"dataset_content_sha256": logical_112},
                    "license": {"status": "fixture"},
                    "sha256": sha_112,
                    "size_bytes": self.raw_112.stat().st_size,
                    "snapshot": "snapshots/municipios.json",
                },
                "icv_municipios": {
                    "inspection": {"dataset_content_sha256": logical_icv},
                    "license": {"status": "fixture"},
                    "sha256": sha_icv,
                    "size_bytes": self.raw_icv.stat().st_size,
                    "snapshot": "snapshots/municipios.gpkg",
                },
            },
        }
        self.manifest_path.write_bytes(_json_bytes(manifest))
        aliases = {
            "aliases": [
                {
                    "cod_ine_mun": "00003",
                    "expected_icv": {"nom_mun": "Alfarb", "noms_mun": "Alfarb"},
                    "municipio_112cv": "Alfarp",
                    "reason": "fixture de diferencia ortográfica",
                    "review": {
                        "basis": "comparación completa del fixture",
                        "reviewed_at": "2026-07-18",
                        "status": "approved",
                    },
                }
            ],
            "applies_to": {
                "icv_municipios_dataset_content_sha256": logical_icv,
                "icv_municipios_sha256": sha_icv,
                "municipios_112cv_sha256": sha_112,
            },
            "schema_version": 1,
        }
        self.aliases_path.write_bytes(_json_bytes(aliases))
        reviews = [
            {
                "municipio_112cv": "Ademuz",
                "cod_ine_mun": "00001",
                "review_categories": "required_sample",
                "icv_noms_mun_observed": "Ademuz",
                "decision": "approved",
                "reviewed_at": "2026-07-18",
                "review_note": "muestra comprobada",
            },
            {
                "municipio_112cv": "Alacant/Alicante",
                "cod_ine_mun": "00002",
                "review_categories": "bilingual",
                "icv_noms_mun_observed": "Alacant/Alicante",
                "decision": "approved",
                "reviewed_at": "2026-07-18",
                "review_note": "formas bilingües comprobadas",
            },
            {
                "municipio_112cv": "Alfarp",
                "cod_ine_mun": "00003",
                "review_categories": "alias",
                "icv_noms_mun_observed": "Alfarb",
                "decision": "approved",
                "reviewed_at": "2026-07-18",
                "review_note": "alias comprobado",
            },
        ]
        _write_csv(self.reviews_path, geo_crosswalk.REVIEW_FIELDS, reviews)
        config = {
            "aliases": "aliases.json",
            "expected": {
                "allowed_zone_ids": [53, 54],
                "municipality_count": 3,
                "outside_record": self.municipalities[-1],
                "zone_counts": {"53": 2, "54": 1},
            },
            "icv": {
                "code_field": "cod_ine_mun",
                "geometry_field": "geom",
                "layer": "ICV.Municipios",
                "name_fields": [
                    "nom_mun",
                    "nom_mun_cas",
                    "nom_mun_cas_a",
                    "nom_mun_val",
                    "nom_mun_val_a",
                    "noms_mun",
                ],
            },
            "output_directory": "../data/crosswalk",
            "provenance": {
                "municipios_112cv": {
                    "dataset_content_sha256": logical_112,
                    "sha256": sha_112,
                    "snapshot": "snapshots/municipios.json",
                },
                "icv_municipios": {
                    "dataset_content_sha256": logical_icv,
                    "sha256": sha_icv,
                    "snapshot": "snapshots/municipios.gpkg",
                },
            },
            "required_manual_samples": ["Ademuz"],
            "reviews": "reviews.csv",
            "schema_version": 1,
            "source_manifest": "../data/sources/manifest.json",
        }
        self.config_path.write_bytes(_json_bytes(config))


class GeoCrosswalkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = CrosswalkFixture(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_is_repeatable_bijective_and_preserves_leading_zeroes(self) -> None:
        first = geo_crosswalk.build_crosswalk(self.fixture.config_path)
        second = geo_crosswalk.build_crosswalk(self.fixture.config_path)
        self.assertEqual(first, second)
        geo_crosswalk.validate_crosswalk(self.fixture.config_path)

        rows = list(
            csv.DictReader(first[geo_crosswalk.CROSSWALK_NAME].decode("utf-8").splitlines())
        )
        self.assertEqual(3, len(rows))
        self.assertNotIn("Fuera C.V.", {row["municipio_112cv"] for row in rows})
        self.assertEqual(3, len({row["municipio_112cv"] for row in rows}))
        self.assertEqual({"00001", "00002", "00003"}, {row["icv_cod_ine_mun"] for row in rows})
        self.assertEqual(
            "alias",
            next(row for row in rows if row["municipio_112cv"] == "Alfarp")[
                "match_method"
            ],
        )

    def test_normalized_candidate_is_reported_but_never_auto_assigned(self) -> None:
        source_rows = [
            {
                "municipio": "ADEMUZ",
                "idZonaPrevifoc": 53,
            }
        ]
        icv_rows = [
            {
                "cod_ine_mun": "00001",
                "geom": b"geometry",
                "nom_mun": "Ademuz",
                "nom_mun_cas": "Ademuz",
                "nom_mun_cas_a": "Ademuz",
                "nom_mun_val": "Ademuz",
                "nom_mun_val_a": "Ademuz",
                "noms_mun": "Ademuz",
            }
        ]
        settings = json.loads(self.fixture.config_path.read_text())["icv"]
        with self.assertRaisesRegex(
            geo_crosswalk.CrosswalkError,
            r"no encontrado 'ADEMUZ'; candidatos por normalización: 00001",
        ):
            geo_crosswalk._build_rows(
                source_rows,
                icv_rows,
                settings,
                aliases={},
                reviews={},
                required_samples=set(),
            )

    def test_ambiguous_literal_match_is_rejected(self) -> None:
        source_rows = [{"municipio": "Duplicado", "idZonaPrevifoc": 53}]
        template = {
            "geom": b"geometry",
            "nom_mun": "Duplicado",
            "nom_mun_cas": None,
            "nom_mun_cas_a": None,
            "nom_mun_val": None,
            "nom_mun_val_a": None,
            "noms_mun": None,
        }
        icv_rows = [
            {**template, "cod_ine_mun": "00001"},
            {**template, "cod_ine_mun": "00002"},
        ]
        settings = json.loads(self.fixture.config_path.read_text())["icv"]
        with self.assertRaisesRegex(
            geo_crosswalk.CrosswalkError, "coincidencia exacta ambigua"
        ):
            geo_crosswalk._build_rows(
                source_rows,
                icv_rows,
                settings,
                aliases={},
                reviews={},
                required_samples=set(),
            )

    def test_unapproved_alias_is_rejected(self) -> None:
        aliases = json.loads(self.fixture.aliases_path.read_text())
        aliases["aliases"][0]["review"]["status"] = "pending"
        self.fixture.aliases_path.write_bytes(_json_bytes(aliases))
        with self.assertRaisesRegex(geo_crosswalk.CrosswalkError, "no tiene una revisión"):
            geo_crosswalk.build_crosswalk(self.fixture.config_path)

    def test_missing_required_manual_review_is_rejected(self) -> None:
        rows = list(
            csv.DictReader(self.fixture.reviews_path.read_text(encoding="utf-8").splitlines())
        )
        _write_csv(
            self.fixture.reviews_path,
            geo_crosswalk.REVIEW_FIELDS,
            [row for row in rows if row["municipio_112cv"] != "Alacant/Alicante"],
        )
        with self.assertRaisesRegex(geo_crosswalk.CrosswalkError, "faltan="):
            geo_crosswalk.build_crosswalk(self.fixture.config_path)

    def test_tampered_output_is_rejected(self) -> None:
        geo_crosswalk.build_crosswalk(self.fixture.config_path)
        crosswalk = self.fixture.output_dir / geo_crosswalk.CROSSWALK_NAME
        crosswalk.write_bytes(crosswalk.read_bytes() + b"tampered\n")
        with self.assertRaisesRegex(geo_crosswalk.CrosswalkError, "no coincide byte a byte"):
            geo_crosswalk.validate_crosswalk(self.fixture.config_path)

    def test_changed_source_hash_is_rejected_before_matching(self) -> None:
        self.fixture.raw_112.write_bytes(self.fixture.raw_112.read_bytes() + b"\n")
        with self.assertRaisesRegex(geo_crosswalk.CrosswalkError, "SHA-256 crudo incorrecto"):
            geo_crosswalk.build_crosswalk(self.fixture.config_path)


class ProductionCrosswalkAcceptanceTests(unittest.TestCase):
    def test_geo_002_acceptance_invariants(self) -> None:
        artifacts = geo_crosswalk.validate_crosswalk()
        manifest = json.loads(artifacts[geo_crosswalk.MANIFEST_NAME])
        rows = list(
            csv.DictReader(
                artifacts[geo_crosswalk.CROSSWALK_NAME].decode("utf-8").splitlines()
            )
        )
        self.assertEqual(542, len(rows))
        self.assertEqual(542, len({row["municipio_112cv"] for row in rows}))
        self.assertEqual(542, len({row["icv_cod_ine_mun"] for row in rows}))
        self.assertNotIn("Fuera C.V.", {row["municipio_112cv"] for row in rows})
        self.assertTrue(all(row["icv_cod_ine_mun"] for row in rows))
        self.assertTrue(
            all(
                len(row["icv_cod_ine_mun"]) == 5
                and row["icv_cod_ine_mun"].isdigit()
                for row in rows
            )
        )
        self.assertEqual(
            {"53": 28, "54": 64, "55": 40, "56": 113, "57": 61, "58": 190, "59": 46},
            dict(manifest["statistics"]["zone_counts"]),
        )
        self.assertEqual(0, manifest["statistics"]["unmatched"])
        self.assertEqual(0, manifest["statistics"]["ambiguous_matches"])
        self.assertEqual(0, manifest["statistics"]["duplicate_icv_codes"])
        self.assertEqual(13, manifest["statistics"]["aliases"])
        self.assertTrue(
            all(
                row["alias_reason"]
                and row["review_status"] == "reviewed"
                and "alias" in row["review_categories"].split(";")
                for row in rows
                if row["match_method"] == "alias"
            )
        )
        self.assertEqual(
            "0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876",
            manifest["outputs"][geo_crosswalk.CROSSWALK_NAME]["sha256"],
        )


if __name__ == "__main__":
    unittest.main()
