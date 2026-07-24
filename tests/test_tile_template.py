from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools import tile_template

try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None  # type: ignore[assignment]


class TileTemplateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = tile_template.build_artifacts()
        cls.original = cls.artifacts[tile_template.ORIGINAL_NAME]
        cls.recolored = cls.artifacts[tile_template.RECOLORED_NAME]
        cls.transparent = cls.artifacts[tile_template.TRANSPARENT_NAME]
        cls.manifest = json.loads(cls.artifacts[tile_template.MANIFEST_NAME])

    def test_frozen_geometry_version_and_hashes(self) -> None:
        self.assertEqual(tile_template.GEOMETRY_VERSION, self.manifest["geometry_version"])
        observed = tile_template.verify_frozen_geometry()
        self.assertEqual(tile_template.FROZEN_HASHES["master"], observed["master"])
        self.assertEqual(tile_template.FROZEN_HASHES["geojson"], observed["geojson"])
        self.assertEqual(tile_template.FROZEN_HASHES["crosswalk"], observed["crosswalk"])

    def test_signature_chunks_lengths_order_and_crc(self) -> None:
        for name in (
            tile_template.ORIGINAL_NAME,
            tile_template.RECOLORED_NAME,
            tile_template.TRANSPARENT_NAME,
        ):
            content = self.artifacts[name]
            self.assertTrue(content.startswith(tile_template.PNG_SIGNATURE))
            chunks = tile_template.parse_png(content)
            self.assertEqual(tile_template.CHUNK_ORDER, tuple(chunk.chunk_type for chunk in chunks))
            self.assertEqual([13, 48, 16, len(chunks[3].data), 0], [len(chunk.data) for chunk in chunks])
            for chunk in chunks:
                self.assertEqual(
                    chunk.crc,
                    zlib.crc32(chunk.chunk_type + chunk.data) & 0xFFFFFFFF,
                )
            width, height, depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunks[0].data
            )
            self.assertEqual((256, 256, 8, 3, 0, 0, 0), (
                width, height, depth, color_type, compression, filtering, interlace
            ))

    def test_palette_indices_and_exact_alpha_contract(self) -> None:
        self.assertEqual(
            {
                "0": "background_transparent",
                "1": "zone_53_1N",
                "2": "zone_54_1S",
                "3": "zone_55_2",
                "4": "zone_56_3",
                "5": "zone_57_4",
                "6": "zone_58_5",
                "7": "zone_59_6",
                "8": "zone_53_1N_hatch",
                "9": "zone_54_1S_hatch",
                "10": "zone_55_2_hatch",
                "11": "zone_56_3_hatch",
                "12": "zone_57_4_hatch",
                "13": "zone_58_5_hatch",
                "14": "zone_59_6_hatch",
                "15": "black_boundaries",
            },
            self.manifest["contract"]["index_meaning"],
        )
        chunks = tile_template.validate_contract(self.original)
        palette = tuple(
            tuple(chunks[1].data[pos : pos + 3])
            for pos in range(0, len(chunks[1].data), 3)
        )
        self.assertEqual(tile_template.MARKER_PALETTE, palette)
        self.assertEqual((0,) + (77,) * 14 + (179,), tuple(chunks[2].data))
        decoded = tile_template.decode_indexed_png(self.original)
        self.assertEqual({0, 1, 2, 8, 9, 15}, set(decoded.indices))
        self.assertEqual(0, decoded.indices[0])
        self.assertEqual(8, decoded.indices[100 * 256 + 80])
        self.assertEqual(15, decoded.indices[100 * 256 + 128])
        self.assertEqual(2, decoded.indices[100 * 256 + 180])

    def test_reference_recolor_changes_only_seven_plte_entries_and_crc(self) -> None:
        before = tile_template.validate_contract(self.original)
        after = tile_template.validate_contract(self.recolored)
        self.assertEqual(before[1].data[:3], after[1].data[:3])
        self.assertEqual(before[1].data[45:48], after[1].data[45:48])
        expected = bytes(component for rgb in tile_template.RECOLORED_TEST_VECTOR for component in rgb)
        self.assertEqual(expected, after[1].data[3:24])
        self.assertEqual(expected, after[1].data[24:45])
        self.assertNotEqual(before[1].crc, after[1].crc)
        for index in (0, 2, 3, 4):
            self.assertEqual(before[index], after[index])
        self.assertEqual(before[3].data, after[3].data)
        self.assertEqual(
            tile_template.sha256_bytes(before[3].data),
            tile_template.sha256_bytes(after[3].data),
        )

    def test_background_multicolor_boundary_and_no_white_halos(self) -> None:
        decoded = tile_template.decode_indexed_png(self.recolored)
        rgba = decoded.rgba_bytes()

        def pixel(x: int, y: int) -> tuple[int, int, int, int]:
            offset = (y * 256 + x) * 4
            return tuple(rgba[offset : offset + 4])  # type: ignore[return-value]

        self.assertEqual((0, 0, 0, 0), pixel(0, 0))
        self.assertEqual((*tile_template.RECOLORED_TEST_VECTOR[0], 77), pixel(80, 100))
        self.assertEqual((*tile_template.RECOLORED_TEST_VECTOR[1], 77), pixel(180, 100))
        self.assertEqual((0, 0, 0, 179), pixel(128, 100))
        self.assertEqual((0, 0, 0, 179), pixel(32, 100))
        colors = {tuple(rgba[pos : pos + 4]) for pos in range(0, len(rgba), 4)}
        self.assertNotIn((255, 255, 255, 255), colors)
        self.assertFalse(any(rgb[:3] == (255, 255, 255) for rgb in colors if rgb[3]))
        self.assertEqual({0, 77, 179}, {color[3] for color in colors})

    def test_transparent_fixture_is_really_fully_transparent(self) -> None:
        decoded = tile_template.decode_indexed_png(self.transparent)
        self.assertEqual({0}, set(decoded.indices))
        self.assertEqual({0}, set(decoded.rgba_bytes()[3::4]))

    @unittest.skipIf(Image is None, "requiere Pillow como segundo decodificador")
    def test_two_independent_decoders_agree(self) -> None:
        for name in (
            tile_template.ORIGINAL_NAME,
            tile_template.RECOLORED_NAME,
            tile_template.TRANSPARENT_NAME,
        ):
            content = self.artifacts[name]
            standard_library = tile_template.decode_indexed_png(content)
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                self.assertEqual("PNG", image.format)
                self.assertEqual("P", image.mode)
                self.assertEqual((256, 256), image.size)
                self.assertEqual(standard_library.indices, image.tobytes())
                self.assertEqual(standard_library.rgba_bytes(), image.convert("RGBA").tobytes())

    def test_repeatability_and_manifest_hashes(self) -> None:
        repeated = tile_template.build_artifacts()
        self.assertEqual(set(self.artifacts), set(repeated))
        for name in self.artifacts:
            self.assertEqual(self.artifacts[name], repeated[name], name)
        for name in (
            tile_template.ORIGINAL_NAME,
            tile_template.RECOLORED_NAME,
            tile_template.TRANSPARENT_NAME,
        ):
            metadata = self.manifest["outputs"][name]
            self.assertEqual(metadata["sha256"], tile_template.sha256_bytes(self.artifacts[name]))
            self.assertEqual(metadata["size_bytes"], len(self.artifacts[name]))

    def test_recolor_rejects_wrong_count_and_crc_corruption(self) -> None:
        with self.assertRaisesRegex(tile_template.TileTemplateError, "7 colores"):
            tile_template.recolor_png(self.original, [(1, 2, 3)] * 6)
        corrupted = bytearray(self.original)
        corrupted[-1] ^= 1
        with self.assertRaisesRegex(tile_template.TileTemplateError, "CRC inválido"):
            tile_template.validate_contract(bytes(corrupted))

    def test_validate_detects_any_output_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for name, content in self.artifacts.items():
                (output / name).write_bytes(content)
            tile_template.validate(output)
            path = output / tile_template.ORIGINAL_NAME
            path.write_bytes(self.original + b"x")
            with self.assertRaisesRegex(tile_template.TileTemplateError, "no reproducible"):
                tile_template.validate(output)


if __name__ == "__main__":
    unittest.main()
