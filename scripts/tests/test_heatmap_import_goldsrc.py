"""Focused preparation/publishing boundaries; no installed game or database needed."""
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import heatmap_import_goldsrc as importer
from heatmap_bsp_surfaces import publish_surface_asset, validate_asset


def asset(name, image_hash='a' * 64):
    return dict(schemaVersion=1, map=name, bspSha256='b' * 64,
                image=dict(width=128, height=128, sha256=image_hash),
                projection=dict(xoffset=0, yoffset=0, scale=1, flipx=0, flipy=0,
                                rotate=0, cropx1=0, cropx2=0, cropy1=0, cropy2=0),
                grid=dict(width=4, height=3), nodeCount=1, edgeCount=0,
                pixelData=base64.b64encode(struct.pack('<I', 0)).decode(),
                heightData=base64.b64encode(struct.pack('<f', 0)).decode(), edgeData='')


class ImportSurfaceBoundaryTests(unittest.TestCase):
    def test_prepare_uses_final_jpeg_and_preserves_empty_output_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            game, output = root / 'game', root / 'prepared'
            (game / 'maps').mkdir(parents=True)
            (game / 'overviews').mkdir()
            name = 'custom-map'
            (game / 'maps' / (name + '.bsp')).write_bytes(b'fixture BSP')
            (game / 'overviews' / (name + '.txt')).write_text('fixture overview')
            Image.new('RGB', (128, 128), '#909090').save(game / 'overviews' / (name + '.bmp'))
            originals = {str(p.relative_to(game)): p.read_bytes() for p in game.rglob('*') if p.is_file()}

            def prepared(selected, bsp, overview, bitmap, jpeg):
                self.assertEqual(selected, name)
                self.assertEqual(bsp, game / 'maps' / (name + '.bsp'))
                self.assertEqual(overview.suffix, '.txt')
                self.assertEqual(bitmap.suffix, '.bmp')
                self.assertEqual(jpeg, output / name / (name + '.jpg'))
                self.assertTrue(jpeg.is_file())
                return asset(name, hashlib.sha256(jpeg.read_bytes()).hexdigest()), {'fixture': True}

            with patch.object(importer, 'read_bsp', return_value={'sha256': 'b' * 64, 'polygons': [], 'world_bounds': []}), \
                 patch.object(importer, 'overview_transform', return_value=[]), \
                 patch.object(importer, 'candidate_config', return_value=asset(name)['projection']), \
                 patch.object(importer, 'product_roundtrip', return_value={'max_euclidean_error_px': 0}), \
                 patch.object(importer, 'draw_overlay', side_effect=lambda image, bsp, matrix, path: image.save(path)), \
                 patch.object(importer, 'write_geometry_svg', side_effect=lambda bsp, matrix, size, path: path.write_text('<svg/>')), \
                 patch.object(importer, 'prepare_surface_asset', side_effect=prepared) as hook:
                result = importer.prepare(game, output, name)
                hook.assert_called_once()
                with self.assertRaisesRegex(ValueError, 'Output must be empty'):
                    importer.prepare(game, output, name)
                with self.assertRaisesRegex(ValueError, 'Surface output must differ'):
                    importer.prepare(game, root / 'other', name, root / 'other')
                hook.assert_called_once()

            directory = output / 'heatmap-surfaces' / 'cstrike'
            entry = json.loads((directory / 'manifest.json').read_text())[name]
            raw = (directory / entry['file']).read_bytes()
            validate_asset(json.loads(raw))
            self.assertEqual(entry['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['maps'][0]['asset_sha256']['surface'], entry['sha256'])
            self.assertTrue(Path(result['maps'][0]['prepared_assets']['surface']).is_file())
            self.assertEqual(originals, {str(p.relative_to(game)): p.read_bytes() for p in game.rglob('*') if p.is_file()})

    def test_publish_preserves_other_maps_and_rejects_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            old = publish_surface_asset(asset('old-map'), output)
            old_bytes = (output / 'old-map.json').read_bytes()
            publish_surface_asset(asset('new-map'), output)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(set(manifest), {'old-map', 'new-map'})
            self.assertEqual(manifest['old-map'], old)
            self.assertEqual((output / 'old-map.json').read_bytes(), old_bytes)
            self.assertFalse((output / '.manifest.lock').exists())
            manifest['old-map']['sha256'] = '0' * 64
            (output / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                publish_surface_asset(asset('third-map'), output)
            self.assertFalse((output / 'third-map.json').exists())
            self.assertFalse((output / '.manifest.lock').exists())


if __name__ == '__main__':
    unittest.main()
