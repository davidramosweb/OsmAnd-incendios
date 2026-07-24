from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import unittest

from tools import geo_compare


if geo_compare._PIL_IMPORT_ERROR is None and geo_compare.geo_zones._DEPENDENCY_IMPORT_ERROR is None:
    from PIL import Image


HAS_DEPENDENCIES = (
    geo_compare._PIL_IMPORT_ERROR is None
    and geo_compare.geo_zones._DEPENDENCY_IMPORT_ERROR is None
)


@unittest.skipUnless(HAS_DEPENDENCIES, "requiere requirements-geo-004.txt")
class GeoCompareAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = geo_compare.DEFAULT_CONFIG.resolve()
        cls.config = geo_compare._load_config(cls.config_path)
        cls.artifacts, cls.output_directory = geo_compare.render_artifacts(
            cls.config_path, run_prerequisites=False
        )
        cls.manifest = json.loads(cls.artifacts[geo_compare.MANIFEST_NAME])

    def test_reference_and_frozen_geo003_hashes(self) -> None:
        expected = {
            "reference": "df1c7c08765bcdae51a36d4efbd414911b975d75de878a04faf364cc8b905f7f",
            "master": "e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
            "geojson": "b76ffaeec4eb9c75ee23991ed9386136d74d94a5bc2603700d65b37e6fb528c2",
            "crosswalk": "0ca0ed22ccaaa6994d4701bd75da1d1355fcb945f4e7dfaf1b22472743294876",
        }
        self.assertEqual(expected["reference"], self.manifest["inputs"]["reference"]["sha256"])
        self.assertEqual(expected["master"], self.manifest["inputs"]["master"]["sha256"])
        self.assertEqual(expected["geojson"], self.manifest["inputs"]["geojson"]["sha256"])
        self.assertEqual(expected["crosswalk"], self.manifest["inputs"]["crosswalk"]["sha256"])
        snapshot = self.output_directory / self.manifest["inputs"]["reference"]["snapshot"]
        self.assertEqual(expected["reference"], hashlib.sha256(snapshot.read_bytes()).hexdigest())

    def test_reads_exactly_seven_zones_and_codes(self) -> None:
        paths = geo_compare._verify_frozen_inputs(self.config_path, self.config)
        zones = geo_compare._load_zones(paths["master"], self.config)
        self.assertEqual(list(range(53, 60)), list(zones))
        self.assertEqual(
            ["1N", "1S", "2", "3", "4", "5", "6"],
            [zones[zone_id]["zone_code"] for zone_id in zones],
        )
        self.assertEqual([1, 1, 29, 2, 5, 67, 154], [zones[zone_id]["parts"] for zone_id in zones])
        self.assertEqual([0, 0, 0, 1, 0, 0, 0], [zones[zone_id]["holes"] for zone_id in zones])

    def test_seven_labels_dimensions_and_approved_geometry_version(self) -> None:
        self.assertEqual(set(geo_compare.EXPECTED_CODES), set(self.config["render"]["labels"]))
        expected_dimensions = {
            geo_compare.REGISTERED_NAME: [500, 835],
            geo_compare.DIAGNOSTIC_NAME: [1000, 1670],
            geo_compare.SIDE_BY_SIDE_NAME: [1020, 835],
            geo_compare.OVERLAY_NAME: [500, 835],
        }
        for name, dimensions in expected_dimensions.items():
            with Image.open(io.BytesIO(self.artifacts[name])) as image:
                self.assertEqual(tuple(dimensions), image.size)
            self.assertEqual(dimensions, self.manifest["outputs"][name]["dimensions_pixels"])
        self.assertEqual("approved", self.manifest["status"])
        self.assertTrue(self.manifest["approval"]["approved"])
        self.assertEqual("2026-07-18", self.manifest["approval"]["date"])
        self.assertEqual(
            "sha256:e2fe8dfca6e62bf40a7a1ff2e6b07677a7dcb890925a68d87c2a756e7884beb0",
            self.manifest["geometry_version"],
        )

    def test_registration_is_uniform_explainable_and_within_control_tolerance(self) -> None:
        registration = self.manifest["registration"]
        self.assertEqual("uniform_scale_translation_with_y_inversion", registration["method"])
        self.assertFalse(registration["nonlinear_deformation"])
        self.assertEqual("north_south_extent", registration["scale_basis"])
        self.assertEqual("bbox_centres", registration["horizontal_alignment"])
        self.assertAlmostEqual(0.002491290213226136, registration["scale_pixels_per_metre"], places=15)
        self.assertLess(
            max(point["residual_distance_pixels"] for point in registration["control_points"]),
            1.5,
        )
        predicted = {point["id"]: point["predicted_pixel"] for point in registration["control_points"]}
        self.assertAlmostEqual(8.0, predicted["north_extreme"][1], places=9)
        self.assertAlmostEqual(826.0, predicted["south_extreme"][1], places=9)

    def test_render_artifacts_repeat_byte_for_byte(self) -> None:
        repeated, _ = geo_compare.render_artifacts(
            self.config_path, run_prerequisites=False
        )
        self.assertEqual(set(self.artifacts), set(repeated))
        for name in self.artifacts:
            self.assertEqual(self.artifacts[name], repeated[name], name)

    def test_hash_guard_rejects_any_geo003_change(self) -> None:
        for name in ("master", "geojson", "crosswalk"):
            altered = copy.deepcopy(self.config)
            altered["inputs"][name]["sha256"] = "0" * 64
            with self.subTest(name=name):
                with self.assertRaisesRegex(geo_compare.CompareError, "hash congelado"):
                    geo_compare._verify_frozen_inputs(self.config_path, altered)

    def test_controls_and_discrepancy_classification(self) -> None:
        statistics = self.manifest["statistics"]
        self.assertEqual(15, statistics["controls"]["versioned_controls"])
        self.assertEqual(9, statistics["controls"]["adjacent_boundary_pairs_checked"])
        self.assertEqual(
            {"bloqueante": 0, "corregible": 0, "explicable": 3},
            statistics["discrepancies"],
        )


if __name__ == "__main__":
    unittest.main()
