from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tools import geo_zones


if geo_zones._DEPENDENCY_IMPORT_ERROR is None:
    import pyproj
    from shapely.geometry import MultiPolygon, Polygon, box


HAS_GEO_DEPENDENCIES = geo_zones._DEPENDENCY_IMPORT_ERROR is None


def _tolerances() -> dict[str, float]:
    return {
        "coverage_absolute_m2": 1e-9,
        "coverage_relative": 0.0,
        "geojson_roundtrip_absolute_m2": 10.0,
        "geojson_roundtrip_relative": 1e-9,
        "overlap_absolute_m2": 1e-9,
        "overlap_relative": 0.0,
        "repair_absolute_m2": 1e-9,
        "repair_relative": 0.0,
    }


@unittest.skipUnless(HAS_GEO_DEPENDENCIES, "requiere requirements-geo.txt")
class GeoZoneGeometryFixtureTests(unittest.TestCase):
    def test_make_valid_is_limited_and_records_collapsed_linework(self) -> None:
        # Dos miembros MultiPolygon comparten un segmento: superficie correcta,
        # representación OGC inválida. Es el mismo tipo de invalidez que Xàtiva.
        invalid = MultiPolygon([box(0, 0, 2, 2), box(2, 1, 3, 2)])
        self.assertFalse(invalid.is_valid)
        config = {
            "expected_invalid_geometries": {
                "00001": {"name": "Fixture", "reason_prefix": "Self-intersection"}
            },
            "repair": {
                "keep_collapsed": True,
                "method": "linework",
                "operation": "shapely.make_valid",
            },
            "tolerances": _tolerances(),
        }
        repaired, repairs, counts = geo_zones._repair_geometries(
            {"00001": {"name": "Fixture", "geometry": invalid}}, config
        )
        geometry = repaired["00001"]
        self.assertTrue(geometry.is_valid)
        self.assertEqual("MultiPolygon", geometry.geom_type)
        self.assertAlmostEqual(5.0, geometry.area)
        self.assertEqual(1, counts["repairs_applied"])
        self.assertEqual(0.0, repairs[0]["symmetric_difference_m2"])
        self.assertEqual(2, repairs[0]["before"]["parts"])
        self.assertEqual(1, repairs[0]["after"]["parts"])
        self.assertEqual(0, repairs[0]["after"]["holes"])
        self.assertEqual("LineString", repairs[0]["discarded_non_polygonal_components"][0]["geometry_type"])
        self.assertAlmostEqual(1.0, repairs[0]["discarded_non_polygonal_components"][0]["length_m"])

    def test_holes_and_small_multipolygon_parts_are_preserved(self) -> None:
        main = Polygon(
            [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
            [[(2, 2), (2, 4), (4, 4), (4, 2), (2, 2)]],
        )
        tiny_island = box(20, 20, 20.001, 20.001)
        source = MultiPolygon([main, tiny_island])
        canonical = geo_zones.canonicalize_multipolygon(source)
        parts, holes = geo_zones._part_hole_counts(canonical)
        self.assertEqual(2, parts)
        self.assertEqual(1, holes)
        self.assertEqual(0.0, source.symmetric_difference(canonical).area)
        self.assertAlmostEqual(source.area, canonical.area)

    def test_coverage_overlap_and_gap_controls(self) -> None:
        reference = [MultiPolygon([box(0, 0, 2, 1)])]
        exact = {
            53: MultiPolygon([box(0, 0, 1, 1)]),
            54: MultiPolygon([box(1, 0, 2, 1)]),
        }
        result = geo_zones.evaluate_topology(reference, exact, _tolerances())
        self.assertTrue(result["coverage"]["passes"])
        self.assertTrue(result["overlaps"]["passes"])
        self.assertEqual(1, result["overlaps"]["pairs_checked"])

        overlap = {
            53: MultiPolygon([box(0, 0, 1.5, 1)]),
            54: MultiPolygon([box(1, 0, 2, 1)]),
        }
        with self.assertRaisesRegex(geo_zones.ZoneError, "falló la topología"):
            geo_zones.evaluate_topology(reference, overlap, _tolerances())

        gap = {
            53: MultiPolygon([box(0, 0, 0.9, 1)]),
            54: MultiPolygon([box(1.1, 0, 2, 1)]),
        }
        with self.assertRaisesRegex(geo_zones.ZoneError, "falló la topología"):
            geo_zones.evaluate_topology(reference, gap, _tolerances())

    def _seven_records(self) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        codes = ["1N", "1S", "2", "3", "4", "5", "6"]
        for offset, (zone_id, zone_code) in enumerate(zip(range(53, 60), codes)):
            geometry = geo_zones.canonicalize_multipolygon(
                MultiPolygon(
                    [box(700000 + offset * 1000, 4300000, 700100 + offset * 1000, 4300100)]
                )
            )
            records.append(
                {
                    "area_m2": float(geometry.area),
                    "bbox_epsg25830": list(geometry.bounds),
                    "geometry": geometry,
                    "geometry_sha256": geo_zones.geometry_sha256(geometry),
                    "holes": 0,
                    "municipality_count": 1,
                    "part_count": 1,
                    "valid": True,
                    "zone_code": zone_code,
                    "zone_id": zone_id,
                }
            )
        return records

    def test_rfc7946_crs_axis_order_winding_and_repeatability(self) -> None:
        records = self._seven_records()
        first, geometries = geo_zones._render_geojson(records, 9)
        second, _ = geo_zones._render_geojson(records, 9)
        self.assertEqual(first, second)
        document = json.loads(first)
        self.assertNotIn("crs", document)
        self.assertEqual(7, len(document["features"]))
        self.assertEqual(list(range(53, 60)), [feature["id"] for feature in document["features"]])
        for feature in document["features"]:
            self.assertEqual("MultiPolygon", feature["geometry"]["type"])
            longitude, latitude = feature["geometry"]["coordinates"][0][0][0]
            self.assertGreater(longitude, -2.0)
            self.assertLess(longitude, 1.0)
            self.assertGreater(latitude, 38.0)
            self.assertLess(latitude, 40.0)
        self.assertEqual(set(range(53, 60)), set(geometries))

    def test_master_gpkg_is_repeatable_and_declares_crs(self) -> None:
        records = self._seven_records()
        srs = {
            "srs_name": "ETRS89 / UTM zone 30N",
            "srs_id": 25830,
            "organization": "EPSG",
            "organization_coordsys_id": 25830,
            "definition": pyproj.CRS.from_epsg(25830).to_wkt(version="WKT1_GDAL"),
            "description": None,
        }
        first = geo_zones._render_master_gpkg(
            records, srs, "2026-07-18T00:00:00.000Z"
        )
        second = geo_zones._render_master_gpkg(
            records, srs, "2026-07-18T00:00:00.000Z"
        )
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "zones.gpkg"
            path.write_bytes(first)
            with contextlib.closing(sqlite3.connect(path)) as connection:
                self.assertEqual("ok", connection.execute("PRAGMA integrity_check").fetchone()[0])
                self.assertEqual(0x47504B47, connection.execute("PRAGMA application_id").fetchone()[0])
                self.assertEqual(7, connection.execute("SELECT COUNT(*) FROM zones").fetchone()[0])
                self.assertEqual(
                    ("MULTIPOLYGON", 25830),
                    connection.execute(
                        "SELECT geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name='zones'"
                    ).fetchone(),
                )


@unittest.skipUnless(HAS_GEO_DEPENDENCIES, "requiere requirements-geo.txt")
class ProductionZoneAcceptanceTests(unittest.TestCase):
    def test_geo_003_real_data_acceptance(self) -> None:
        artifacts = geo_zones.validate_zones()
        manifest = json.loads(artifacts[geo_zones.MANIFEST_NAME])
        statistics = manifest["statistics"]
        self.assertEqual(542, statistics["join"]["matched"])
        self.assertEqual(0, statistics["join"]["icv_without_crosswalk"])
        self.assertEqual(0, statistics["join"]["crosswalk_without_icv"])
        self.assertTrue(statistics["join"]["preserved_as_text_five_digits"])
        self.assertEqual(541, statistics["municipal_geometries"]["valid_before_repair"])
        self.assertEqual(1, statistics["municipal_geometries"]["invalid_before_repair"])
        self.assertEqual(542, statistics["municipal_geometries"]["valid_after_repair"])
        self.assertEqual("46145", statistics["repairs"][0]["cod_ine_mun"])
        self.assertEqual("Xàtiva", statistics["repairs"][0]["municipality"])
        self.assertEqual(18, statistics["repairs"][0]["before"]["holes"])
        self.assertEqual(18, statistics["repairs"][0]["after"]["holes"])
        self.assertEqual(0.0, statistics["repairs"][0]["symmetric_difference_m2"])
        self.assertTrue(statistics["topology"]["coverage"]["passes"])
        self.assertEqual(0.0, statistics["topology"]["coverage"]["symmetric_difference_m2"])
        self.assertTrue(statistics["topology"]["overlaps"]["passes"])
        self.assertEqual(21, statistics["topology"]["overlaps"]["pairs_checked"])
        self.assertEqual(0.0, statistics["topology"]["overlaps"]["max_area_m2"])
        self.assertEqual(
            [28, 64, 40, 113, 61, 190, 46],
            [zone["municipalities"] for zone in statistics["zones"]],
        )
        self.assertTrue(all(zone["valid"] for zone in statistics["zones"]))
        self.assertTrue(statistics["geojson_roundtrip"]["passes"])
        self.assertEqual(
            "e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
            manifest["outputs"][geo_zones.MASTER_NAME]["sha256"],
        )
        self.assertEqual(
            "b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2",
            manifest["outputs"][geo_zones.GEOJSON_NAME]["sha256"],
        )
        self.assertEqual(
            manifest["outputs"][geo_zones.MASTER_NAME]["sha256"],
            hashlib.sha256(artifacts[geo_zones.MASTER_NAME]).hexdigest(),
        )
        geojson = json.loads(artifacts[geo_zones.GEOJSON_NAME])
        self.assertNotIn("crs", geojson)
        self.assertEqual(list(range(53, 60)), [feature["id"] for feature in geojson["features"]])
        self.assertTrue(
            all(feature["geometry"]["type"] == "MultiPolygon" for feature in geojson["features"])
        )


if __name__ == "__main__":
    unittest.main()
