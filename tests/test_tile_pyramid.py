from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile
import unittest

from shapely.geometry import box

from tools import tile_pyramid, tile_template


class TilePyramidUnitTests(unittest.TestCase):
    def _inside_tile(self, zoom: int, x: int, y: int, inset: float = 0.2):
        left, bottom, right, top = tile_pyramid.tile_bounds(zoom, x, y)
        width = right - left
        height = top - bottom
        return box(
            left + inset * width,
            bottom + inset * height,
            right - inset * width,
            top - inset * height,
        )

    def test_xyz_bounds_and_zoom_limits(self) -> None:
        for zoom in range(6, 15):
            limit = 1 << zoom
            west, south, east, north = tile_pyramid.tile_bounds(zoom, 0, 0)
            self.assertAlmostEqual(-tile_pyramid.WEB_MERCATOR_HALF_WORLD, west)
            self.assertAlmostEqual(tile_pyramid.WEB_MERCATOR_HALF_WORLD, north)
            self.assertGreater(east, west)
            self.assertGreater(north, south)
            tile_pyramid.tile_bounds(zoom, limit - 1, limit - 1)
        for zoom in (5, 15):
            with self.assertRaisesRegex(tile_pyramid.TilePyramidError, "zoom fuera"):
                tile_pyramid.tile_bounds(zoom, 0, 0)

    def test_y_is_xyz_not_tms(self) -> None:
        zoom = 10
        north = tile_pyramid.mercator_to_tile(zoom, 0.0, 5_000_000.0)
        south = tile_pyramid.mercator_to_tile(zoom, 0.0, 4_000_000.0)
        self.assertLess(north[1], south[1])
        _, north_bottom, _, north_top = tile_pyramid.tile_bounds(zoom, *north)
        _, south_bottom, _, south_top = tile_pyramid.tile_bounds(zoom, *south)
        self.assertGreater(north_bottom, south_bottom)
        self.assertGreater(north_top, south_top)

    def test_enumerates_only_exact_intersections(self) -> None:
        zoom, x, y = 8, 126, 97
        geometry = self._inside_tile(zoom, x, y)
        dataset = tile_pyramid.dataset_from_projected({53: geometry})
        self.assertEqual(((x, y),), tile_pyramid.enumerate_tiles(dataset, zoom))

        left, bottom, right, top = tile_pyramid.tile_bounds(zoom, x, y)
        span = right - left
        crossing = box(right - span * 0.1, bottom + span * 0.2, right + span * 0.1, top - span * 0.2)
        dataset = tile_pyramid.dataset_from_projected({53: crossing})
        self.assertEqual(((x, y), (x + 1, y)), tile_pyramid.enumerate_tiles(dataset, zoom))

    def test_png_contract_transparency_and_determinism(self) -> None:
        zoom, x, y = 8, 126, 97
        dataset = tile_pyramid.dataset_from_projected({53: self._inside_tile(zoom, x, y)})
        first = tile_pyramid.render_tile_indices(dataset, zoom, x, y)
        second = tile_pyramid.render_tile_indices(dataset, zoom, x, y)
        self.assertEqual(first, second)
        first_png = tile_template.encode_indexed_png(first)
        second_png = tile_template.encode_indexed_png(second)
        self.assertEqual(first_png, second_png)
        chunks = tile_template.validate_contract(first_png)
        self.assertEqual(tile_template.CHUNK_ORDER, tuple(chunk.chunk_type for chunk in chunks))
        self.assertTrue({0, 1, 8, 15}.issubset(set(first)))

        exterior = tile_pyramid.render_tile_indices(dataset, zoom, x + 5, y + 5)
        self.assertEqual({0}, set(exterior))
        transparent = tile_template.decode_indexed_png(tile_template.encode_indexed_png(exterior))
        self.assertEqual({0}, set(transparent.rgba_bytes()[3::4]))

    def test_adjacent_tiles_equal_shared_window_crops(self) -> None:
        zoom, x, y = 8, 126, 97
        left, bottom, right, top = tile_pyramid.tile_bounds(zoom, x, y)
        span = right - left
        geometry = box(left + span * 0.2, bottom + span * 0.2, right + span * 0.2, top - span * 0.2)
        dataset = tile_pyramid.dataset_from_projected({53: geometry})
        left_tile = tile_pyramid.render_tile_indices(dataset, zoom, x, y)
        right_tile = tile_pyramid.render_tile_indices(dataset, zoom, x + 1, y)
        width, height, shared = tile_pyramid.render_window_indices(
            dataset, zoom, x, y, width_tiles=2
        )
        self.assertEqual((512, 256), (width, height))
        self.assertEqual(left_tile, tile_pyramid._extract_tile(shared, 2, 0, 0))
        self.assertEqual(right_tile, tile_pyramid._extract_tile(shared, 2, 1, 0))
        self.assertIn(15, left_tile[tile_pyramid.TILE_SIZE - 1::tile_pyramid.TILE_SIZE])


class TilePyramidProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.output = tile_pyramid.DEFAULT_OUTPUT
        cls.manifest = json.loads((cls.output / tile_pyramid.MANIFEST_NAME).read_text(encoding="utf-8"))

    def test_frozen_versions_and_zoom_counts(self) -> None:
        self.assertEqual(tile_template.GEOMETRY_VERSION, self.manifest["geometry_version"])
        self.assertEqual(tile_template.FORMAT_VERSION, self.manifest["format_version"])
        self.assertEqual([6, 14], self.manifest["pyramid"]["zooms"])
        self.assertEqual(set(map(str, range(6, 15))), set(self.manifest["pyramid"]["by_zoom"]))
        self.assertEqual(
            self.manifest["pyramid"]["tile_assets"],
            sum(item["tiles"] for item in self.manifest["pyramid"]["by_zoom"].values()),
        )

    def test_inventory_paths_hashes_bytes_and_asset_limit(self) -> None:
        inventory_path = self.output / self.manifest["pyramid"]["inventory"]["path"]
        inventory = inventory_path.read_bytes()
        self.assertEqual(self.manifest["pyramid"]["inventory"]["sha256"], tile_pyramid.sha256_bytes(inventory))
        lines = inventory.decode("utf-8").splitlines()
        self.assertEqual(self.manifest["pyramid"]["tile_assets"], len(lines))
        byte_total = 0
        for line in lines:
            digest, relative = line.split("  ", 1)
            parts = relative.split("/")
            self.assertEqual(3, len(parts))
            zoom, x, filename = parts
            self.assertIn(int(zoom), range(6, 15))
            self.assertTrue(filename.endswith(".png"))
            path = self.output / relative
            self.assertEqual(digest, tile_pyramid.sha256_file(path))
            byte_total += path.stat().st_size
        self.assertEqual(byte_total, self.manifest["pyramid"]["tile_bytes"])
        self.assertLess(self.manifest["assets"]["total"], 19_000)
        self.assertTrue(self.manifest["assets"]["passes_limit"])

    def test_png_sample_each_zoom_and_shared_transparent_tile(self) -> None:
        lines = (self.output / tile_pyramid.INVENTORY_NAME).read_text(encoding="utf-8").splitlines()
        by_zoom: dict[int, list[Path]] = {zoom: [] for zoom in range(6, 15)}
        for line in lines:
            relative = line.split("  ", 1)[1]
            by_zoom[int(relative.split("/", 1)[0])].append(self.output / relative)
        for zoom, paths in by_zoom.items():
            sample = paths[len(paths) // 2]
            decoded = tile_template.decode_indexed_png(sample.read_bytes())
            self.assertEqual((256, 256), (decoded.width, decoded.height), zoom)
            self.assertEqual(tile_template.MARKER_PALETTE, decoded.palette, zoom)
            self.assertEqual(tile_template.ALPHA_TABLE, decoded.alpha, zoom)
            self.assertTrue(set(decoded.indices).issubset(set(range(16))), zoom)
        transparent = tile_template.decode_indexed_png(
            (self.output / tile_pyramid.TRANSPARENT_NAME).read_bytes()
        )
        self.assertEqual({0}, set(transparent.indices))

    def test_continuity_orientation_boundaries_and_controls(self) -> None:
        verification = self.manifest["verification"]
        self.assertEqual(17, verification["continuity"]["pairs_checked"])
        self.assertEqual(
            [{"direction": "south", "reason": "no adjacent covered pair", "zoom": 6}],
            verification["continuity"]["unavailable_directions"],
        )
        self.assertTrue(verification["geographic"]["orientation_xyz"]["passes"])
        self.assertLess(
            verification["geographic"]["orientation_xyz"]["north_y"],
            verification["geographic"]["orientation_xyz"]["south_y"],
        )
        self.assertGreater(verification["geographic"]["internal_boundaries_checked"], 0)
        self.assertEqual(0, verification["visual"]["visible_white_pixels"])
        self.assertEqual(list(range(16)), verification["visual"]["indices_observed"])
        for zoom in (6, 10, 14):
            self.assertIn(f"controls/z{zoom}-overview.png", self.manifest["controls"])
        for name, metadata in self.manifest["controls"].items():
            path = self.output / name
            self.assertEqual(metadata["sha256"], tile_pyramid.sha256_file(path))

    def test_manifest_total_bytes_and_file_count(self) -> None:
        files = [path for path in self.output.rglob("*") if path.is_file()]
        self.assertEqual(self.manifest["assets"]["total"], len(files))
        self.assertEqual(self.manifest["assets"]["bytes_total"], sum(path.stat().st_size for path in files))


if __name__ == "__main__":
    unittest.main()
