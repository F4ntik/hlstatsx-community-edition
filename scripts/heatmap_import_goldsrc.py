"""Prepare native GoldSrc overview images and BSP geometry for a local installation.

Reads the installed game without modifying it. No database changes. No feature
matching is necessary: JPEGs retain the exact native BMP coordinate frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw
from heatmap_bsp_registration import (read_bsp, overview_transform, candidate_config,
                                      product_roundtrip, draw_overlay, write_geometry_svg)
from heatmap_bsp_surfaces import MAP_NAME, prepare_surface_asset, publish_surface_asset


def prepare(game: Path, output: Path, map_name: str | None = None,
            surface_output: Path | None = None) -> dict:
    surface_output = surface_output if surface_output is not None else output / 'heatmap-surfaces' / 'cstrike'
    if surface_output.resolve() == output.resolve():
        raise ValueError('Surface output must differ from the report output directory')
    for destination in (output, surface_output):
        if destination.resolve().is_relative_to(game.resolve()):
            raise ValueError('Outputs must be outside the game directory')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty; existing reports are not overwritten')
    maps = {p.stem.lower(): p for p in (game / 'maps').glob('*.bsp')}
    bitmaps = {p.stem.lower(): p for p in (game / 'overviews').glob('*.bmp')}
    texts = {p.stem.lower(): p for p in (game / 'overviews').glob('*.txt')}
    names = sorted(maps.keys() & bitmaps.keys() & texts.keys())
    if not names:
        raise ValueError('No matching BSP/BMP/TXT files found')
    if map_name is not None:
        if map_name not in names:
            raise ValueError(f'{map_name}: no matching BSP/BMP/TXT files found')
        names = [map_name]
    for name in names:
        if not MAP_NAME.fullmatch(name):
            raise ValueError(f'Unsupported map name: {name}; the public viewer needs a letter followed by up to 31 letters, digits, underscores or hyphens')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'frame': 'native overview, no resize or crop', 'maps': [],
                'skipped_without_overview': sorted(maps.keys() - (bitmaps.keys() & texts.keys())),
                'surface_directory': str(surface_output.resolve()),
                'surface_install_directory': 'web/hlstatsimg/heatmap-surfaces/cstrike'}
    for name in names:
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
        surface, surface_report = prepare_surface_asset(
            name, maps[name], texts[name], bitmaps[name], image_path)
        surface_entry = publish_surface_asset(surface, surface_output)
        report = {'map': name, 'status': 'native_frame_import', 'candidate_config': config,
                  'served_size': list(served.size), 'native_size': list(served.size),
                  'world_to_served': matrix, 'world_to_native': matrix,
                  'bsp_sha256': bsp['sha256'], 'world_faces': len(bsp['polygons']),
                  'world_bounds': bsp['world_bounds'], 'python_roundtrip': roundtrip,
                  'surface_asset': surface_entry,
                  'surface_preparation': surface_report,
                  'prepared_assets': {
                      'image': str(image_path.relative_to(output)),
                      'geometry': str((directory / 'bsp-served-geometry.svg').relative_to(output)),
                      'registration': str((directory / 'registration-report.json').relative_to(output)),
                      'surface': str((surface_output / surface_entry['file']).resolve()),
                      'surface_manifest': str((surface_output / 'manifest.json').resolve())},
                  'asset_sha256': {key: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for key, path in [('overview', texts[name]), ('native_image', bitmaps[name]), ('served_image', image_path)]},
                  'acceptance_boundary': 'Native overview projection, product rounding and bounded BSP surface graph checked. Game files and database unchanged. Output stays local unless an explicit surface destination targets the site. Historical server-version identity and event coverage remain unverified.'}
        report['asset_sha256']['surface'] = surface_entry['sha256']
        (directory / 'registration-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        manifest['maps'].append(report)
        print(f'{name}: {len(bsp["polygons"])} faces, {surface["nodeCount"]} surface nodes, max error {roundtrip["max_euclidean_error_px"]:.3f} px', flush=True)
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
    parser.add_argument('--map', dest='map_name', help='Prepare only this map; default: every matched BSP/BMP/TXT')
    parser.add_argument('--surface-output', type=Path, help='Explicit surface destination; atomically replaces files and merges its validated manifest. Default: OUTPUT/heatmap-surfaces/cstrike')
    args = parser.parse_args()
    result = prepare(args.game_dir, args.output, args.map_name, args.surface_output)
    print(f'Prepared {len(result["maps"])} maps. Game files and database unchanged.')
