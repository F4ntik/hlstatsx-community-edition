"""Prepare bounded, wall-aware surface graphs from local GoldSrc BSP v30 maps.

Reads game files only. Publishes derived topology and hashes, never BSP/BMP data.
Requires numpy/Pillow and the adjacent heatmap_bsp_experiment.py prototype.
"""
from __future__ import annotations

import argparse
import ast
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import tempfile
import time

import numpy as np
from PIL import Image

from heatmap_bsp_experiment import WorldCollision, build_graph
from heatmap_bsp_registration import candidate_config, overview_transform, read_bsp

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Half-Life\cstrike")
MAX_NODES, MAX_EDGES = 196608, 393216
MAP_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
PROJECTION_KEYS = ("xoffset", "yoffset", "scale", "flipx", "flipy", "rotate",
                   "cropx1", "cropx2", "cropy1", "cropy2")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def seed_projections(path):
    """Read the existing installation seeds without executing SQL or changing DB."""
    text = path.read_text(encoding="utf-8")
    columns = ("map", "game", "xoffset", "yoffset", "flipx", "flipy", "days", "brush",
               "scale", "font", "thumbw", "thumbh", "cropx1", "cropy1", "cropx2", "cropy2")
    seeds = {}
    for match in re.finditer(r"^\('([a-z0-9_]+)', 'cstrike',[^\n]+\)", text, re.M):
        row = dict(zip(columns, ast.literal_eval(match[0])))
        row["rotate"] = 0
        seeds[row["map"]] = {key: row[key] for key in PROJECTION_KEYS}
    for match in re.finditer(r"UPDATE `hlstats_Heatmap_Config` SET `rotate` = ([0-3]) WHERE `game` = 'cstrike' AND `map` IN \(([^;]+)\);", text):
        for name in re.findall(r"'([a-z0-9_]+)'", match[2]):
            seeds[name]["rotate"] = int(match[1])
    return seeds


def validate_asset(asset):
    """Decode and validate the exact browser/PHP contract; return compact facts."""
    if asset.get("schemaVersion") != 1 or not MAP_NAME.fullmatch(asset.get("map", "")):
        raise ValueError("Invalid surface identity")
    image, grid = asset["image"], asset["grid"]
    for digest in (asset["bspSha256"], image["sha256"]):
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid SHA-256")
    width, height = grid["width"], grid["height"]
    if not (0 < width <= 512 and 0 < height <= 384 and image["width"] > 0 and image["height"] > 0):
        raise ValueError("Invalid dimensions")
    projection = asset["projection"]
    if set(projection) != set(PROJECTION_KEYS) or any(not math.isfinite(projection[k]) for k in PROJECTION_KEYS):
        raise ValueError("Invalid projection")
    if projection["scale"] <= 0 or projection["rotate"] not in range(4):
        raise ValueError("Invalid scale/rotation")
    n, e = asset["nodeCount"], asset["edgeCount"]
    if not (0 < n <= MAX_NODES and 0 <= e <= MAX_EDGES):
        raise ValueError("Graph exceeds bounded contract")
    buffers = [base64.b64decode(asset[key], validate=True) for key in ("pixelData", "heightData", "edgeData")]
    if [len(raw) for raw in buffers] != [4 * n, 4 * n, 8 * e]:
        raise ValueError("Incorrect typed-array byte length")
    pixels = [x[0] for x in struct.iter_unpack("<I", buffers[0])]
    heights = [x[0] for x in struct.iter_unpack("<f", buffers[1])]
    if any(p >= width * height for p in pixels) or any(not math.isfinite(z) for z in heights):
        raise ValueError("Invalid pixel/height")
    ordered = list(zip(pixels, heights))
    if ordered != sorted(ordered) or len(set(ordered)) != n:
        raise ValueError("Nodes must be unique and sorted by pixel/height")
    pairs = list(struct.iter_unpack("<II", buffers[2]))
    degrees = [0] * n
    if len(set(pairs)) != e:
        raise ValueError("Duplicate edges")
    for a, b in pairs:
        if not 0 <= a < b < n:
            raise ValueError("Invalid edge endpoints")
        pa, pb = pixels[a], pixels[b]
        if abs(pa % width - pb % width) + abs(pa // width - pb // width) != 1:
            raise ValueError("Non-cardinal edge")
        if abs(heights[a] - heights[b]) > 22.001:
            raise ValueError("Edge crosses disconnected elevation")
        degrees[a] += 1
        degrees[b] += 1
    if max(degrees, default=0) > 4:
        raise ValueError("Degree exceeds four")
    return {"maxDegree": max(degrees, default=0), "decodedBytes": sum(map(len, buffers))}


def prepare_surface_asset(name, bsp_path, overview_path, bmp_path, image_path,
                          width=320, height=240):
    """Build one native-frame asset from explicit paths, without writing files."""
    start = time.perf_counter()
    if not MAP_NAME.fullmatch(name):
        raise ValueError(f"Unsupported surface map name: {name}; use a letter followed by up to 31 letters, digits, underscores or hyphens")
    if not (0 < width <= 512 and 0 < height <= 384 and width * 3 == height * 4):
        raise ValueError("Grid must be 4:3, at most 512x384")
    raw_image = image_path.read_bytes()
    image_hash = sha256(raw_image)
    with Image.open(image_path) as image, Image.open(bmp_path) as native:
        size = image.size
        if size != native.size:
            raise ValueError(f"{name}: image is not in native overview frame")
        # Existing assets are JPEG conversions of these overviews. Reject a
        # changed/cropped source rather than silently registering the wrong frame.
        source = np.asarray(native.convert("RGB"), dtype=np.float32)
        served = np.asarray(image.convert("RGB"), dtype=np.float32)
        # Bundled images replace the overview's green chroma-key background.
        # Compare the actual map pixels, leaving that intentional color change out.
        background = (source[:, :, 1] > source[:, :, 0] + 30) & (source[:, :, 1] > source[:, :, 2] + 30)
        if np.count_nonzero(~background) < 10000:
            raise ValueError(f"{name}: insufficient overview map pixels")
        mae = float(np.abs(served - source)[~background].mean())
        if mae > 8:
            raise ValueError(f"{name}: native overview/image differ (MAE {mae:.3f})")
    overview_text = overview_path.read_text(encoding="utf-8-sig")
    projection = candidate_config(overview_transform(overview_text, *size))
    bsp = read_bsp(bsp_path)
    matrix = overview_transform(overview_text, width, height)
    graph = build_graph(bsp, WorldCollision(bsp_path), matrix, width, height)
    asset = dict(schemaVersion=1, map=name, bspSha256=bsp["sha256"],
                 image=dict(width=size[0], height=size[1], sha256=image_hash),
                 projection=projection, grid=dict(width=width, height=height),
                 nodeCount=len(graph["pixel"]), edgeCount=len(graph["edges"]),
                 pixelData=base64.b64encode(b"".join(struct.pack("<I", p) for p in graph["pixel"])).decode("ascii"),
                 heightData=base64.b64encode(b"".join(struct.pack("<f", p[2]) for p in graph["xyz"])).decode("ascii"),
                 edgeData=base64.b64encode(b"".join(struct.pack("<II", *edge) for edge in graph["edges"])).decode("ascii"))
    validation = validate_asset(asset)
    raw = json_bytes(asset)
    if len(raw) > 6500000:
        raise ValueError(f"{name}: surface asset exceeds the public loader limit")
    report = dict(map=name, **validation, **graph["diagnostics"], jsonBytes=len(raw),
                  gzipBytes=len(gzip.compress(raw, mtime=0)), seconds=round(time.perf_counter() - start, 3),
                  nativeImageMeanAbsoluteError=round(mae, 4))
    return asset, report


def publish_surface_asset(asset, output):
    """Merge one validated asset into an explicitly selected local directory.

    Existing entries are retained. Readers see complete files; the directory
    lock rejects overlapping publishers rather than losing a manifest update.
    """
    validate_asset(asset)
    raw = json_bytes(asset)
    if len(raw) > 6500000:
        raise ValueError("Surface asset exceeds the public loader limit")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.manifest.lock'
    # Exclusive creation is scoped to this output, never a global/game lock.
    with lock.open('x'):
        pass
    temporary = []
    try:
        manifest_path = output / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
        if not isinstance(manifest, dict):
            raise ValueError("Invalid existing surface manifest")
        for name, entry in manifest.items():
            if not MAP_NAME.fullmatch(name) or not isinstance(entry, dict) or entry.get('file') != name + '.json':
                raise ValueError("Unsafe existing surface manifest entry")
            previous = (output / entry['file']).read_bytes()
            previous_asset = json.loads(previous)
            validate_asset(previous_asset)
            if (previous_asset['map'], sha256(previous), previous_asset['image']['sha256'],
                previous_asset['nodeCount'], previous_asset['edgeCount']) != (
                    name, entry.get('sha256'), entry.get('imageHash'), entry.get('nodeCount'), entry.get('edgeCount')):
                raise ValueError("Existing surface manifest identity mismatch")
        name = asset['map']
        entry = dict(file=name + '.json', sha256=sha256(raw), imageHash=asset['image']['sha256'],
                     nodeCount=asset['nodeCount'], edgeCount=asset['edgeCount'])
        manifest[name] = entry
        for target, data in ((output / entry['file'], raw),
                             (manifest_path, json_bytes(dict(sorted(manifest.items()))))):
            with tempfile.NamedTemporaryFile(dir=output, prefix='.' + target.name + '.', delete=False) as stream:
                temporary.append((Path(stream.name), target))
                stream.write(data)
            # These are public web assets. NamedTemporaryFile starts at 0600
            # on POSIX, which would otherwise prevent a separate web user reading them.
            Path(stream.name).chmod(0o644)
        for stage, target in temporary:
            stage.replace(target)
        return entry
    finally:
        for stage, _ in temporary:
            stage.unlink(missing_ok=True)
        lock.unlink()


def export_map(name, args, geometry_manifest, seeds):
    image_path = args.image_root / (name + ".jpg")
    if sha256(image_path.read_bytes()) != geometry_manifest[name]["imageHash"]:
        raise ValueError(f"{name}: bundled image does not match existing geometry manifest")
    asset, report = prepare_surface_asset(
        name, args.game_root / "maps" / (name + ".bsp"),
        args.game_root / "overviews" / (name + ".txt"),
        args.game_root / "overviews" / (name + ".bmp"), image_path,
        args.width, args.height)
    projection = asset["projection"]
    report["seedMismatches"] = {
        key: {"seed": seeds.get(name, {}).get(key), "asset": projection[key]}
        for key in PROJECTION_KEYS if key not in seeds.get(name, {}) or
        not math.isclose(seeds[name][key], projection[key], rel_tol=1e-9, abs_tol=1e-8)}
    raw = json_bytes(asset)
    path = args.output / (name + ".json")
    path.write_bytes(raw)
    # Read back exactly what will be shipped, including its manifest digest.
    disk = path.read_bytes()
    validate_asset(json.loads(disk))
    entry = dict(file=path.name, sha256=sha256(disk), imageHash=asset["image"]["sha256"],
                 nodeCount=asset["nodeCount"], edgeCount=asset["edgeCount"])
    return entry, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--map", dest="map_name")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--image-root", type=Path, default=ROOT / "heatmaps/src/cstrike")
    parser.add_argument("--geometry-manifest", type=Path, default=ROOT / "web/hlstatsimg/heatmap-geometry/cstrike/manifest.json")
    parser.add_argument("--seeds", type=Path, default=ROOT / "sql/install.sql")
    parser.add_argument("--output", type=Path, default=ROOT / "web/hlstatsimg/heatmap-surfaces/cstrike")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--report", type=Path, help="Optional local JSON evidence report")
    args = parser.parse_args()
    if not (0 < args.width <= 512 and 0 < args.height <= 384 and args.width * 3 == args.height * 4):
        parser.error("Grid must be 4:3, at most 512x384")
    # The exporter must never create/replace a file under the game directory.
    game = args.game_root.resolve()
    for output in [args.output] + ([args.report] if args.report else []):
        if output.resolve().is_relative_to(game):
            parser.error("Outputs must be outside the game directory")
    geometry_manifest = json.loads(args.geometry_manifest.read_text(encoding="utf-8"))
    names = sorted(geometry_manifest) if args.all else [args.map_name]
    if any(not MAP_NAME.fullmatch(name) or name not in geometry_manifest for name in names):
        parser.error("Select a map from the bundled geometry manifest")
    seeds = seed_projections(args.seeds)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.json"
    manifest = {} if args.all or not manifest_path.exists() else json.loads(manifest_path.read_text(encoding="utf-8"))
    start = time.perf_counter()
    reports, errors = [], []
    for name in names:
        try:
            entry, report = export_map(name, args, geometry_manifest, seeds)
            manifest[name] = entry
            reports.append(report)
            print(json.dumps(report), flush=True)
        except (ValueError, OSError, KeyError) as error:
            errors.append(dict(map=name, error=str(error)))
            print(json.dumps(errors[-1]), flush=True)
    manifest_path.write_bytes(json_bytes(dict(sorted(manifest.items()))))
    for name, entry in manifest.items():
        if name not in geometry_manifest or not MAP_NAME.fullmatch(name) or entry["file"] != name + ".json":
            raise ValueError("Unsafe manifest file")
        raw = (args.output / entry["file"]).read_bytes()
        asset = json.loads(raw)
        validate_asset(asset)
        if asset["map"] != name:
            raise ValueError("Manifest map mismatch")
        if (sha256(raw), asset["image"]["sha256"], asset["nodeCount"], asset["edgeCount"]) != (entry["sha256"], entry["imageHash"], entry["nodeCount"], entry["edgeCount"]):
            raise ValueError("Manifest identity mismatch")
    report = dict(requested=len(names), generated=len(reports), errors=errors,
                  seedMismatchMaps=[r["map"] for r in reports if r["seedMismatches"]],
                  jsonBytes=sum(r["jsonBytes"] for r in reports),
                  gzipBytes=sum(r["gzipBytes"] for r in reports),
                  seconds=round(time.perf_counter() - start, 3), maps=reports)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(json_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k != "maps"}), flush=True)
    return 1 if errors or report["seedMismatchMaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
