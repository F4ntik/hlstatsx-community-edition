"""Offline GoldSrc BSP/overview diagnostic; never writes game files or a database.

Geometry: ValveSoftware/halflife utils/common/bspfile.h (BSP v30).
Overview: cl_dll/hud_spectator.cpp DrawOverviewLayer (fixed 4:3 frame).
Pillow is needed for overlays; optional OpenCV supplies image registration.
Derived reports are diagnostic evidence, not independent landmark acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path


def read_bsp(path: Path) -> dict:
    if path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("BSP exceeds 128 MiB limit")
    raw = path.read_bytes()
    if len(raw) < 124 or struct.unpack_from("<i", raw)[0] != 30:
        raise ValueError("Expected GoldSrc BSP version 30")
    lumps = []
    intervals = []
    for index in range(15):
        offset, size = struct.unpack_from("<ii", raw, 4 + index * 8)
        if offset < 0 or size < 0 or offset + size > len(raw) or (size and offset < 124):
            raise ValueError(f"Invalid lump bounds: {index}")
        if size:
            if any(offset < end and start < offset + size for start, end in intervals):
                raise ValueError("Overlapping BSP lumps")
            intervals.append((offset, offset + size))
        lumps.append(raw[offset:offset + size])

    def records(index, fmt):
        width = struct.calcsize(fmt)
        if len(lumps[index]) % width:
            raise ValueError(f"Misaligned BSP lump: {index}")
        return list(struct.iter_unpack(fmt, lumps[index]))

    vertices = records(3, "<3f")
    planes = records(1, "<4fi")
    edges = records(12, "<2H")
    surfedges = [row[0] for row in records(13, "<i")]
    faces = records(7, "<Hhihh4Bi")
    models = records(14, "<9f7i")
    if not models or not vertices or any(not all(math.isfinite(v) for v in p) for p in vertices):
        raise ValueError("Missing or invalid world geometry")
    if any(not all(math.isfinite(v) for v in p[:4]) for p in planes):
        raise ValueError("Invalid BSP planes")
    first, count = models[0][-2:]
    if first < 0 or count < 0 or first + count > len(faces):
        raise ValueError("Invalid world face range")
    polygons = []
    for face in faces[first:first + count]:
        plane, side, edge_start, edge_count = face[:4]
        if plane >= len(planes) or side not in (0, 1) or edge_count < 3 or edge_start < 0 or edge_start + edge_count > len(surfedges):
            raise ValueError("Invalid world face")
        polygon = []
        for signed in surfedges[edge_start:edge_start + edge_count]:
            if abs(signed) >= len(edges):
                raise ValueError("Invalid surface edge reference")
            vertex = edges[abs(signed)][0 if signed >= 0 else 1]
            if vertex >= len(vertices):
                raise ValueError("Invalid vertex reference")
            polygon.append(vertices[vertex])
        normal_z = planes[plane][2] * (-1 if side else 1)
        polygons.append({"vertices": polygon, "normal_z": normal_z})
    entities = []
    entity_text = lumps[0].rstrip(b"\x00").decode("latin1")
    for block in re.findall(r"\{([^{}]*)\}", entity_text):
        pairs = dict(re.findall(r'"([^"\r\n]+)"\s*"([^"\r\n]*)"', block))
        if "origin" in pairs:
            try:
                origin = tuple(float(v) for v in pairs["origin"].split())
            except ValueError as error:
                raise ValueError("Invalid entity origin") from error
            if len(origin) != 3 or not all(math.isfinite(v) for v in origin):
                raise ValueError("Invalid entity origin")
            entities.append({"classname": pairs.get("classname", ""), "origin": origin})
    return {"sha256": hashlib.sha256(raw).hexdigest(), "polygons": polygons,
            "entities": entities, "world_bounds": [models[0][:3], models[0][3:6]]}


def overview_transform(text: str, width: int, height: int):
    """Return native bitmap affine coefficients (a,b,tx,c,d,ty)."""
    if width <= 0 or height <= 0 or width * 3 != height * 4:
        raise ValueError("GoldSrc native overview must have 4:3 aspect")
    text = re.sub(r"//[^\n]*", "", text)
    number = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    zoom = re.search(r"\bZOOM\s+" + number, text, re.I)
    origin = re.search(r"\bORIGIN\s+" + number + r"\s+" + number, text, re.I)
    rotated = re.search(r"\bROTATED\s+([^\s}]+)", text, re.I)
    if not zoom or not origin or not rotated or rotated[1] not in ("0", "1"):
        raise ValueError("Overview needs ZOOM, ORIGIN and ROTATED 0/1")
    z, ox, oy = float(zoom[1]), float(origin[1]), float(origin[2])
    if not all(math.isfinite(v) for v in (z, ox, oy)) or z <= 0:
        raise ValueError("Invalid overview numbers")
    k = z * width / 8192.0
    if rotated[1] == "1":
        return (k, 0.0, width / 2 - k * ox, 0.0, -k, height / 2 + k * oy)
    return (0.0, -k, width / 2 + k * oy, -k, 0.0, height / 2 + k * ox)


def project(matrix, point):
    a, b, tx, c, d, ty = matrix
    x, y = point[:2]
    return (a * x + b * y + tx, c * x + d * y + ty)


def compose(left, right):
    a, b, tx, c, d, ty = left
    e, f, ux, g, h, uy = right
    return (a * e + b * g, a * f + b * h, a * ux + b * uy + tx,
            c * e + d * g, c * f + d * h, c * ux + d * uy + ty)


def candidate_config(matrix):
    """Convert a uniform signed permutation to the persisted product contract."""
    if len(matrix) != 6 or not all(math.isfinite(v) for v in matrix):
        raise ValueError("Invalid projection matrix")
    a, b, tx, c, d, ty = matrix
    k = max(abs(v) for v in (a, b, c, d))
    if k <= 0:
        raise ValueError("Degenerate projection matrix")
    rotations = ((1, 0, 0, 1), (0, -1, 1, 0), (-1, 0, 0, -1), (0, 1, -1, 0))
    for rotate, (ra, rb, rc, rd) in enumerate(rotations):
        for flipx, flipy in ((False, False), (True, False), (False, True), (True, True)):
            sx, sy = (-1 if flipx else 1), (-1 if flipy else 1)
            expected = (k * ra * sx, k * rb * sy, k * rc * sx, k * rd * sy)
            if all(math.isclose(v, e, rel_tol=1e-10, abs_tol=k * 1e-10) for v, e in zip((a, b, c, d), expected)):
                # Offsets are applied BEFORE quarter-turn; inverse rotation is transpose.
                return dict(xoffset=round((ra * tx + rc * ty) / k),
                            yoffset=round((rb * tx + rd * ty) / k), scale=1 / k,
                            flipx=flipx, flipy=flipy, rotate=rotate,
                            cropx1=0, cropx2=0, cropy1=0, cropy2=0)
    raise ValueError("Projection is not a supported orthogonal uniform transform")


def product_roundtrip(bsp, matrix, candidate):
    """Exercise actual product code, including its integer rasterization."""
    from datetime import datetime
    from hlstats_py.heatmaps import HeatmapConfig, HeatmapPoint, transform_point
    config = HeatmapConfig(code="cstrike", game="cstrike", map_name="diagnostic",
                           days=30, brush="", font=0, thumbw=0, thumbh=0, **candidate)
    points = sorted({(int(p[0]), int(p[1])) for face in bsp["polygons"] for p in face["vertices"]})
    errors = []
    samples = []
    for x, y in points:
        result = transform_point(HeatmapPoint(datetime(2000, 1, 1), x, y), config)
        errors.append(math.dist(result, project(matrix, (x, y))))
    entities = [e for e in bsp["entities"] if e["classname"] in ("info_player_start", "info_player_deathmatch", "info_bomb_target")]
    for entity in entities[::5]:
        x, y = map(int, entity["origin"][:2])
        samples.append(dict(world=[x, y], pixel=transform_point(HeatmapPoint(datetime(2000, 1, 1), x, y), config)))
    if not errors:
        raise ValueError("No BSP points for product roundtrip")
    return dict(points=len(points), max_euclidean_error_px=max(errors),
                rmse_px=math.sqrt(sum(e * e for e in errors) / len(errors)), samples=samples)


def spatial_holdouts(source, target, cell_size=1.0):
    """Union duplicate physical features on EITHER image before splitting groups.

    Spatial buckets group SIFT orientation/scale duplicates and many-to-one
    matches. Connected groups cannot cross the train/holdout boundary.
    """
    if len(source) != len(target) or cell_size <= 0:
        raise ValueError("Invalid image correspondence groups")
    parents = list(range(len(source)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners = {}
    for index, pair in enumerate(zip(source, target)):
        for side, point in enumerate(pair):
            if not all(math.isfinite(float(v)) for v in point):
                raise ValueError("Invalid feature coordinate")
            key = (side, math.floor(float(point[0]) / cell_size), math.floor(float(point[1]) / cell_size))
            if key in owners:
                parents[root(index)] = root(owners[key])
            else:
                owners[key] = index
    groups = {}
    for index in range(len(source)):
        groups.setdefault(root(index), []).append(index)
    # Order by physical coordinates, not detector orientation ordering.
    ordered = sorted(groups.values(), key=lambda rows: min(tuple(map(float, source[i])) + tuple(map(float, target[i])) for i in rows))
    result = [False] * len(source)
    for rank, rows in enumerate(ordered):
        for index in rows:
            result[index] = rank % 5 == 0
    return result


def register_images(native, served):
    """Independent feature correspondences; fit train subset, measure holdouts."""
    import cv2
    import numpy as np

    cv2.setRNGSeed(719)
    detector = cv2.SIFT_create(nfeatures=6000)
    kp1, desc1 = detector.detectAndCompute(np.array(native.convert("L")), None)
    kp2, desc2 = detector.detectAndCompute(np.array(served.convert("L")), None)
    if desc1 is None or desc2 is None:
        raise ValueError("No image features")
    matches = cv2.BFMatcher().knnMatch(desc1, desc2, k=2)
    good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < .7 * pair[1].distance]
    if len(good) < 30:
        raise ValueError("Insufficient image correspondences")
    src = np.float32([kp1[m.queryIdx].pt for m in good])
    dst = np.float32([kp2[m.trainIdx].pt for m in good])
    holdout = np.array(spatial_holdouts(src, dst), dtype=bool)
    if int(holdout.sum()) < 10 or int((~holdout).sum()) < 20:
        raise ValueError("Insufficient independent spatial feature groups")
    affine, mask = cv2.estimateAffinePartial2D(src[~holdout], dst[~holdout], method=cv2.RANSAC, ransacReprojThreshold=2, maxIters=10000, confidence=.999)
    if affine is None or mask is None or int(mask.sum()) < 20:
        raise ValueError("Image registration failed")
    # Existing product supports uniform axis-aligned scale, not arbitrary angles.
    angle = math.degrees(math.atan2(affine[1, 0], affine[0, 0]))
    if abs(angle) > .15 or affine[0, 0] <= 0:
        raise ValueError("Image registration requires unsupported rotation")
    train_src = src[~holdout][mask.ravel() == 1]
    train_dst = dst[~holdout][mask.ravel() == 1]
    centered_src = train_src - train_src.mean(axis=0)
    centered_dst = train_dst - train_dst.mean(axis=0)
    scale = float((centered_src * centered_dst).sum() / (centered_src ** 2).sum())
    translation = train_dst.mean(axis=0) - scale * train_src.mean(axis=0)
    residual = np.linalg.norm(src * scale + translation - dst, axis=1)
    accepted_holdout = residual[holdout] <= 2
    if accepted_holdout.sum() < 10 or float(accepted_holdout.mean()) < .7:
        raise ValueError("Independent image holdouts disagree")
    quadrants = {(int(p[0] >= native.width / 2), int(p[1] >= native.height / 2)) for p in train_src}
    if len(quadrants) != 4:
        raise ValueError("Image matches do not cover all quadrants")
    matrix = (scale, 0.0, float(translation[0]), 0.0, scale, float(translation[1]))
    return matrix, {"matches": len(good), "training_inliers": int(mask.sum()),
        "holdout_split": "connected source-and-target 1px spatial groups, every fifth group",
        "holdouts": int(holdout.sum()), "holdout_inliers": int(accepted_holdout.sum()),
        "holdout_inlier_rmse_px": float(np.sqrt(np.mean(residual[holdout][accepted_holdout] ** 2))),
        "holdout_all_median_px": float(np.median(residual[holdout])),
        "quadrants": len(quadrants), "unconstrained_rotation_degrees": angle}


def draw_overlay(image, bsp, matrix, output: Path):
    from PIL import ImageDraw
    image = image.convert("RGB")
    draw = ImageDraw.Draw(image)
    for face in bsp["polygons"]:
        if face["normal_z"] > .65:
            points = [project(matrix, p) for p in face["vertices"]]
            draw.line(points + points[:1], fill=(0, 255, 200), width=1)
    for entity in bsp["entities"]:
        classname = entity["classname"]
        if classname not in ("info_player_start", "info_player_deathmatch", "info_bomb_target"):
            continue
        x, y = project(matrix, entity["origin"])
        color = (70, 130, 255) if classname == "info_player_start" else (255, 70, 70)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color, outline="white")
    image.save(output)


def write_geometry_svg(bsp, matrix, size, output):
    """Derived geometry only: never embeds game textures or local asset paths."""
    width, height = size
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
             '<title>BSP floor outlines and spawn origins, diagnostic only</title>',
             f'<rect width="{width}" height="{height}" fill="#14212c"/>',
             '<g fill="none" stroke="#4acbbb" stroke-width="0.7">']
    for face in bsp["polygons"]:
        if face["normal_z"] > .65:
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (project(matrix, p) for p in face["vertices"]))
            lines.append(f'<polygon points="{points}"/>')
    lines.append('</g>')
    for entity in bsp["entities"]:
        kind = entity["classname"]
        if kind in ("info_player_start", "info_player_deathmatch"):
            x, y = project(matrix, entity["origin"])
            color = "#4682ff" if kind == "info_player_start" else "#ff4646"
            lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{color}"/>')
    lines.append('</svg>')
    output.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bsp", type=Path, required=True)
    parser.add_argument("--overview", type=Path, required=True)
    parser.add_argument("--native-image", type=Path, required=True)
    parser.add_argument("--served-image", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Private local diagnostic output directory")
    args = parser.parse_args()
    from PIL import Image
    bsp = read_bsp(args.bsp)
    native = Image.open(args.native_image)
    matrix = overview_transform(args.overview.read_text(), *native.size)
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"status": "diagnostic_only_not_landmark_accepted", "bsp_sha256": bsp["sha256"],
        "world_bounds": bsp["world_bounds"], "world_faces": len(bsp["polygons"]),
        "world_to_native": matrix, "native_size": native.size,
        "entities": [{**e, "native_pixel": project(matrix, e["origin"])} for e in bsp["entities"] if e["classname"] in ("info_player_start", "info_player_deathmatch", "info_bomb_target")],
        "sources": ["https://github.com/ValveSoftware/halflife/blob/master/utils/common/bspfile.h", "https://github.com/ValveSoftware/halflife/blob/master/cl_dll/hud_spectator.cpp"],
        "asset_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (("overview", args.overview), ("native_image", args.native_image))}}
    draw_overlay(native, bsp, matrix, args.output / "bsp-native-overlay.png")
    write_geometry_svg(bsp, matrix, native.size, args.output / "bsp-native-geometry.svg")
    final_matrix = matrix
    if args.served_image:
        served = Image.open(args.served_image)
        registration, evidence = register_images(native, served)
        composed = compose(registration, matrix)
        final_matrix = composed
        report.update(native_to_served=registration, world_to_served=composed, image_registration=evidence, served_size=served.size)
        report["asset_sha256"]["served_image"] = hashlib.sha256(args.served_image.read_bytes()).hexdigest()
        draw_overlay(served, bsp, composed, args.output / "bsp-served-overlay.png")
        write_geometry_svg(bsp, composed, served.size, args.output / "bsp-served-geometry.svg")
    report["candidate_config"] = candidate_config(final_matrix)
    report["candidate_image"] = "served_image" if args.served_image else "native_image"
    report["python_roundtrip"] = product_roundtrip(bsp, final_matrix, report["candidate_config"])
    report["acceptance_boundary"] = "Diagnostic geometry and image registration; real event landmark acceptance remains separate. No database mutation."
    (args.output / "registration-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "entities"}, indent=2))


if __name__ == "__main__":
    main()
