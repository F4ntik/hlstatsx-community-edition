"""Independent SDK corner fixtures and malformed binary rejection."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location("bsp_registration", Path(__file__).parents[1] / "heatmap_bsp_registration.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RegistrationTests(unittest.TestCase):
    def test_candidate_all_orthogonal_orientations_roundtrip_product(self):
        rotations = ((1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0))
        bsp = {"polygons": [{"vertices": [(0, 0, 0), (100, 40, 0), (-32, -60, 0)]}], "entities": []}
        for a, b, c, d in rotations:
            for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                matrix = (a * sx / 2, b * sy / 2, 123, c * sx / 2, d * sy / 2, 456)
                config = module.candidate_config(matrix)
                self.assertEqual(config["scale"], 2)
                result = module.product_roundtrip(bsp, matrix, config)
                self.assertEqual(result["max_euclidean_error_px"], 0)

    def test_candidate_rejects_unsupported_matrix(self):
        for matrix in ((0, 0, 0, 0, 0, 0), (1, 0, 0, 0, 2, 0), (1, .2, 0, 0, 1, 0), (float("nan"), 0, 0, 0, 1, 0)):
            with self.assertRaises(ValueError):
                module.candidate_config(matrix)

    def test_spatial_holdouts_keep_both_image_duplicates_together(self):
        source = [(i * 10., 0.) for i in range(20)]
        target = [(i * 12., 0.) for i in range(20)]
        # Source duplicate (alternate SIFT orientation), then a target duplicate,
        # then transitive connection to a distinct source point.
        source += [source[0], (555., 0.), (666., 0.)]
        target += [(888., 0.), target[1], (888., 0.)]
        split = module.spatial_holdouts(source, target)
        self.assertEqual(split[0], split[20])
        self.assertEqual(split[0], split[22])
        self.assertEqual(split[1], split[21])
        self.assertIn(True, split)
        self.assertIn(False, split)
        order = list(reversed(range(len(source))))
        reordered = module.spatial_holdouts([source[i] for i in order], [target[i] for i in order])
        self.assertEqual(reordered, [split[i] for i in order])

    def test_reads_triangle_and_rejects_invalid_topology(self):
        lumps = [b""] * 15
        lumps[0] = b'{"classname" "info_player_start" "origin" "1 2 3"}\x00'
        lumps[1] = struct.pack("<4fi", 0, 0, 1, 0, 2)
        lumps[3] = b"".join(struct.pack("<3f", *p) for p in ((0, 0, 0), (10, 0, 0), (0, 10, 0)))
        lumps[7] = struct.pack("<Hhihh4Bi", 0, 0, 0, 3, 0, 0, 0, 0, 0, -1)
        lumps[12] = b"".join(struct.pack("<2H", *p) for p in ((0, 0), (0, 1), (1, 2), (2, 0)))
        lumps[13] = struct.pack("<3i", 1, 2, 3)
        lumps[14] = struct.pack("<9f7i", *(0,) * 9, *(0,) * 6, 1)

        def binary():
            header = bytearray(struct.pack("<i", 30) + bytes(120))
            body = bytearray()
            for index, lump in enumerate(lumps):
                struct.pack_into("<ii", header, 4 + index * 8, 124 + len(body), len(lump))
                body.extend(lump)
            return header + body

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "triangle.bsp"
            path.write_bytes(binary())
            result = module.read_bsp(path)
            self.assertEqual(result["polygons"][0]["vertices"][2], (0, 10, 0))
            self.assertEqual(result["entities"][0]["origin"], (1, 2, 3))
            lumps[13] = struct.pack("<3i", 1, 2, 99)
            path.write_bytes(binary())
            with self.assertRaises(ValueError):
                module.read_bsp(path)

    def test_rotated_native_corners(self):
        transform = module.overview_transform("ZOOM 2\nORIGIN 100 200 0\nROTATED 1", 1024, 768)
        self.assertEqual(module.project(transform, (100, 200)), (512, 384))
        self.assertEqual(module.project(transform, (-1948, 1736)), (0, 0))
        self.assertEqual(module.project(transform, (2148, -1336)), (1024, 768))

    def test_nonrotated_native_corners(self):
        transform = module.overview_transform("ZOOM 2\nORIGIN 100 200 0\nROTATED 0", 1024, 768)
        self.assertEqual(module.project(transform, (100, 200)), (512, 384))
        self.assertEqual(module.project(transform, (1636, 2248)), (0, 0))
        self.assertEqual(module.project(transform, (-1436, -1848)), (1024, 768))

    def test_invalid_overviews(self):
        for text in ("ZOOM 0\nORIGIN 0 0\nROTATED 0", "ZOOM 1\nORIGIN 0 0\nROTATED 2", "ZOOM 1e999\nORIGIN 0 0\nROTATED 0"):
            with self.assertRaises(ValueError):
                module.overview_transform(text, 1024, 768)
        with self.assertRaises(ValueError):
            module.overview_transform("ZOOM 1\nORIGIN 0 0\nROTATED 0", 1280, 1024)

    def test_compose(self):
        world = (0, -2, 300, -2, 0, 400)
        image = (1.5, 0, 20, 0, 1.5, 30)
        point = (13, 71)
        self.assertEqual(module.project(module.compose(image, world), point), module.project(image, module.project(world, point)))

    def test_reject_bad_binary_bounds_and_version(self):
        fixtures = [b"", struct.pack("<i", 29) + bytes(120)]
        header = bytearray(struct.pack("<i", 30) + bytes(120))
        struct.pack_into("<ii", header, 4, 124, 100)
        fixtures.append(bytes(header))
        header = bytearray(struct.pack("<i", 30) + bytes(140))
        struct.pack_into("<ii", header, 4, 124, 10)
        struct.pack_into("<ii", header, 12, 128, 10)
        fixtures.append(bytes(header))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.bsp"
            for fixture in fixtures:
                path.write_bytes(fixture)
                with self.assertRaises(ValueError):
                    module.read_bsp(path)


if __name__ == "__main__":
    unittest.main()
