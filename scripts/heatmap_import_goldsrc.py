"""Prepare native GoldSrc overview images and BSP geometry for a local installation.

Reads the installed game without modifying it. No database changes. No feature
matching is necessary: JPEGs retain the exact native BMP coordinate frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw
from heatmap_bsp_registration import (read_bsp, overview_transform, candidate_config,
                                      product_roundtrip, draw_overlay, write_geometry_svg)


def prepare(game: Path, output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty; existing reports are not overwritten')
    output.mkdir(parents=True, exist_ok=True)
    maps = {p.stem.lower(): p for p in (game / 'maps').glob('*.bsp')}
    bitmaps = {p.stem.lower(): p for p in (game / 'overviews').glob('*.bmp')}
    texts = {p.stem.lower(): p for p in (game / 'overviews').glob('*.txt')}
    names = sorted(maps.keys() & bitmaps.keys() & texts.keys())
    if not names:
        raise ValueError('No matching BSP/BMP/TXT files found')
    manifest = {'frame': 'native overview, no resize or crop', 'maps': [],
                'skipped_without_overview': sorted(maps.keys() - set(names))}
    for name in names:
        if not re.fullmatch(r'[a-z0-9_-]{1,64}', name):
            raise ValueError(f'Unsupported map name: {name}')
        directory = output / name
        directory.mkdir()
        bsp = read_bsp(maps[name])
        native = Image.open(bitmaps[name]).convert('RGB')
        matrix = overview_transform(texts[name].read_text(encoding='utf-8-sig'), *native.size)
        config = candidate_config(matrix)
        roundtrip = product_roundtrip(bsp, matrix, config)
        if roundtrip['max_euclidean_error_px'] > 2:
            raise ValueError(f'{name}: product projection error exceeds 2 px')
        # GoldSrc overview transparency key; this changes colour only, never XY.
        background = (44, 51, 56)
        native.putdata([background if g > 200 and r < 25 and b < 25 else (r, g, b)
                        for r, g, b in native.getdata()])
        image_path = directory / (name + '.jpg')
        native.save(image_path, quality=95, subsampling=0)
        served = Image.open(image_path)
        draw_overlay(served, bsp, matrix, directory / 'bsp-served-overlay.png')
        write_geometry_svg(bsp, matrix, served.size, directory / 'bsp-served-geometry.svg')
        report = {'map': name, 'status': 'native_frame_import', 'candidate_config': config,
                  'served_size': list(served.size), 'native_size': list(served.size),
                  'world_to_served': matrix, 'world_to_native': matrix,
                  'bsp_sha256': bsp['sha256'], 'world_faces': len(bsp['polygons']),
                  'world_bounds': bsp['world_bounds'], 'python_roundtrip': roundtrip,
                  'asset_sha256': {key: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for key, path in [('overview', texts[name]), ('native_image', bitmaps[name]), ('served_image', image_path)]},
                  'acceptance_boundary': 'Native overview projection and product rounding checked. This is not a wall mask or historical server-version verification.'}
        (directory / 'registration-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        manifest['maps'].append(report)
        print(f'{name}: {len(bsp["polygons"])} faces, max error {roundtrip["max_euclidean_error_px"]:.3f} px', flush=True)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    # Contact sheets support checking every map without opening 25 separate files.
    for overlay in (False, True):
        sheet = Image.new('RGB', (5 * 256, ((len(names) + 4) // 5) * 216), '#202830')
        draw = ImageDraw.Draw(sheet)
        for i, name in enumerate(names):
            image = Image.open(output / name / ('bsp-served-overlay.png' if overlay else name + '.jpg'))
            image.thumbnail((256, 192))
            x, y = i % 5 * 256, i // 5 * 216
            sheet.paste(image, (x, y + 24))
            draw.text((x + 8, y + 5), name, fill='white')
        sheet.save(output / ('geometry-contact-sheet.jpg' if overlay else 'maps-contact-sheet.jpg'), quality=92)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True, help='Counter-Strike directory containing maps/ and overviews/')
    parser.add_argument('--output', type=Path, required=True, help='New local output directory')
    args = parser.parse_args()
    result = prepare(args.game_dir, args.output)
    print(f'Prepared {len(result["maps"])} maps. Game files and database unchanged.')
