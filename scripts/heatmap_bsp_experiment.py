"""Private offline experiment: floor samples + GoldSrc world collision + diffusion.

Does not change the game, database or product renderer. Requires Pillow/numpy.
The graph is a sampled point-clearance approximation, NOT player navigation.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, deque
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from heatmap_bsp_registration import overview_transform, project, read_bsp


class WorldCollision:
    """Hull 0: dnode children >=0 are nodes, <0 are -(leaf+1).

    Splits the entire segment at BSP planes, so a thin solid leaf cannot be
    skipped by fixed-distance point sampling. Only CONTENTS_EMPTY is accepted.
    No player-radius inflation, hull 1/2 or dynamic brush entity handling.
    """

    def __init__(self, path):
        raw = path.read_bytes()  # read_bsp must first validate version/lump bounds.
        def records(lump, fmt):
            off, size = struct.unpack_from("<ii", raw, 4 + lump * 8)
            width = struct.calcsize(fmt)
            if size % width:
                raise ValueError(f"Misaligned collision lump {lump}")
            return list(struct.iter_unpack(fmt, raw[off:off + size]))
        self.planes = records(1, "<4fi")
        self.nodes = records(5, "<i2h6h2H")
        self.leaves = records(10, "<ii6h2H4B")
        models = records(14, "<9f7i")
        self.root = models[0][9]
        if not 0 <= self.root < len(self.nodes):
            raise ValueError("Invalid world hull 0 root")
        for row in self.nodes:
            if not 0 <= row[0] < len(self.planes):
                raise ValueError("Invalid collision plane")
            for child in row[1:3]:
                if child >= len(self.nodes) or (child < 0 and -child - 1 >= len(self.leaves)):
                    raise ValueError("Invalid collision child")
        # Reject cycles rather than allowing malformed data to hang traversal.
        done, active = set(), set()
        def visit(node):
            if node < 0 or node in done:
                return
            if node in active:
                raise ValueError("Cycle in collision tree")
            active.add(node)
            for child in self.nodes[node][1:3]:
                visit(child)
            active.remove(node)
            done.add(node)
        visit(self.root)

    def contents(self, p):
        node = self.root
        while node >= 0:
            row = self.nodes[node]
            nx, ny, nz, dist, _ = self.planes[row[0]]
            d = nx * p[0] + ny * p[1] + nz * p[2] - dist
            node = row[1 if d >= 0 else 2]
        return self.leaves[-node - 1][0]

    def clear(self, a, b):
        stack = [(self.root, a, b)]
        while stack:
            node, p, q = stack.pop()
            if node < 0:
                if self.leaves[-node - 1][0] != -1:
                    return False
                continue
            row = self.nodes[node]
            nx, ny, nz, dist, _ = self.planes[row[0]]
            dp = nx * p[0] + ny * p[1] + nz * p[2] - dist
            dq = nx * q[0] + ny * q[1] + nz * q[2] - dist
            if dp >= 0 and dq >= 0:
                stack.append((row[1], p, q))
            elif dp < 0 and dq < 0:
                stack.append((row[2], p, q))
            else:
                t = dp / (dp - dq)
                mid = tuple(p[k] + t * (q[k] - p[k]) for k in range(3))
                side = 1 if dp >= 0 else 2
                stack.append((row[side], p, mid))
                stack.append((row[3 - side], mid, q))
        return True


def build_graph(bsp, collision, matrix, width, height, headroom=72, step=22):
    a, b, tx, c, d, ty = matrix
    det = a * d - b * c
    def unproject(u, v):
        return ((d * (u - tx) - b * (v - ty)) / det,
                (-c * (u - tx) + a * (v - ty)) / det)
    cells = [[] for _ in range(width * height)]
    candidates = [dict() for _ in cells]
    counters = Counter()
    for face in bsp["polygons"]:
        if face["normal_z"] < .7:
            counters["non_upward_or_steep_faces"] += 1
            continue
        verts = np.array(face["vertices"], dtype=float)
        uv = np.array([project(matrix, v) for v in verts])
        x0, x1 = max(0, math.ceil(uv[:, 0].min() - .5)), min(width - 1, math.floor(uv[:, 0].max() - .5))
        y0, y1 = max(0, math.ceil(uv[:, 1].min() - .5)), min(height - 1, math.floor(uv[:, 1].max() - .5))
        if x1 < x0 or y1 < y0:
            continue
        xx, yy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        xx, yy = xx.ravel(), yy.ravel()
        positive, negative = np.ones(xx.size, bool), np.ones(xx.size, bool)
        for p, q in zip(uv, np.roll(uv, -1, axis=0)):
            cross = (q[0] - p[0]) * (yy + .5 - p[1]) - (q[1] - p[1]) * (xx + .5 - p[0])
            positive &= cross >= -1e-7
            negative &= cross <= 1e-7
        inside = positive | negative
        normal = None
        for j in range(1, len(verts) - 1):
            trial = np.cross(verts[j] - verts[0], verts[j + 1] - verts[0])
            if abs(trial[2]) > 1e-6:
                normal = trial
                break
        if normal is None:
            continue
        for x, y in zip(xx[inside].tolist(), yy[inside].tolist()):
            wx, wy = unproject(x + .5, y + .5)
            z = verts[0, 2] - (normal[0] * (wx - verts[0, 0]) + normal[1] * (wy - verts[0, 1])) / normal[2]
            key = round(float(z), 2)
            candidates[y * width + x][key] = (wx, wy, float(z))
    xyz, pixel = [], []
    for cell, levels in enumerate(candidates):
        for z, p in sorted(levels.items()):
            counters["candidate_surface_samples"] += 1
            if collision.contents((p[0], p[1], p[2] - 1)) != -2:
                counters["excluded_no_solid_support"] += 1
                continue
            if not collision.clear((p[0], p[1], p[2] + 1), (p[0], p[1], p[2] + headroom)):
                counters["excluded_nonempty_or_low_headroom"] += 1
                continue
            cells[cell].append(len(xyz))
            xyz.append(p)
            pixel.append(cell)
    edges = []
    for cell, owners in enumerate(cells):
        x, y = cell % width, cell // width
        for other in ([cell + 1] if x + 1 < width else []) + ([cell + width] if y + 1 < height else []):
            for i in owners:
                matches = [j for j in cells[other] if abs(xyz[i][2] - xyz[j][2]) <= step]
                # One symmetric edge per direction. Ambiguity is rejected, not mixed.
                if len(matches) > 1:
                    counters["ambiguous_neighbor_directions_rejected"] += 1
                    continue
                if not matches:
                    continue
                j = matches[0]
                if sum(abs(xyz[k][2] - xyz[j][2]) <= step for k in owners) != 1:
                    counters["ambiguous_neighbor_directions_rejected"] += 1
                    continue
                p, q = xyz[i], xyz[j]
                z = max(p[2], q[2])
                if all(collision.clear((p[0], p[1], z + dz), (q[0], q[1], z + dz)) for dz in (1, headroom / 2, headroom)):
                    edges.append((i, j))
                else:
                    counters["blocked_neighbor_edges"] += 1
    neighbors = [[] for _ in xyz]
    for i, j in edges:
        neighbors[i].append(j)
        neighbors[j].append(i)
    component = [-1] * len(xyz)
    sizes = []
    for i in range(len(xyz)):
        if component[i] >= 0:
            continue
        idx = len(sizes)
        component[i] = idx
        queue, size = [i], 0
        while queue:
            k = queue.pop()
            size += 1
            for j in neighbors[k]:
                if component[j] < 0:
                    component[j] = idx
                    queue.append(j)
        sizes.append(size)
    counters.update(nodes=len(xyz), edges=len(edges), cells_with_surface=sum(bool(v) for v in cells),
                    overlapping_xy_cells=sum(len(v) > 1 for v in cells), components=len(sizes),
                    isolated_nodes=sum(len(v) == 0 for v in neighbors))
    assert max(map(len, neighbors), default=0) <= 4
    return dict(xyz=xyz, pixel=pixel, cells=cells, edges=edges, neighbors=neighbors,
                component=component, component_sizes=sizes, diagnostics=dict(counters))


def diffuse(count, edges, sources, iterations, alpha=.24):
    values = np.zeros(count, dtype=np.float64)
    for source in sources:
        values[source] += 1
    if edges:
        pairs = np.array(edges, dtype=np.int32)
        p, q = pairs[:, 0], pairs[:, 1]
        for _ in range(iterations):
            flow = alpha * (values[p] - values[q])
            delta = np.bincount(p, weights=-flow, minlength=count) + np.bincount(q, weights=flow, minlength=count)
            values += delta
    return values


def unrestricted(width, height, source, iterations, alpha=.24):
    a = np.zeros((height, width), dtype=np.float64)
    a[source // width, source % width] = 1
    for _ in range(iterations):
        delta = np.zeros_like(a)
        flow = alpha * (a[:, :-1] - a[:, 1:])
        delta[:, :-1] -= flow
        delta[:, 1:] += flow
        flow = alpha * (a[:-1, :] - a[1:, :])
        delta[:-1, :] -= flow
        delta[1:, :] += flow
        a += delta
    return a.ravel()


def verify_invariants():
    results = []
    def check(name, count, edges, source, probe, reachable):
        values = diffuse(count, edges, [source], 50)
        assert abs(float(values.sum()) - 1) < 1e-12
        assert float(values.min()) >= -1e-15
        assert (float(values[probe]) > 0) == reachable
        results.append(dict(name=name, passed=True, total_mass=float(values.sum()), probe=float(values[probe])))
    check("sealed_room", 4, [(0, 1), (2, 3)], 0, 3, False)
    check("thin_blocked_edge", 2, [], 0, 1, False)
    check("open_doorway", 4, [(0, 1), (1, 2), (2, 3)], 0, 3, True)
    check("no_diagonal_corner_cut", 4, [(0, 1), (2, 3)], 0, 3, False)
    check("two_coincident_levels_without_vertical_edge", 4, [(0, 1), (2, 3)], 0, 2, False)
    # Real collision traversal with a synthetic thin solid slab x in [-.1,.1].
    world = WorldCollision.__new__(WorldCollision)
    world.root = 0
    world.planes = [(1, 0, 0, .1, 0), (1, 0, 0, -.1, 0)]
    world.nodes = [(0, -1, 1), (1, -2, -1)]
    world.leaves = [(-1,), (-2,)]
    assert not world.clear((-1, 0, 0), (1, 0, 0))
    assert world.clear((.2, 0, 0), (1, 0, 0))
    results.append(dict(name="bsp_trace_detects_subsample_thin_solid_leaf", passed=True))
    return results


def find_wall_example(graph, collision, width, height):
    xyz, cells, pixel = graph["xyz"], graph["cells"], graph["pixel"]
    # Deterministic: choose a short Euclidean route crossing actual solid BSP,
    # with no allowed graph route within 40 steps. Avoid isolated tiny islands.
    for i in range(0, len(xyz), 7):
        if len(graph["neighbors"][i]) < 3 or graph["component_sizes"][graph["component"][i]] < 200:
            continue
        cell = pixel[i]
        x, y = cell % width, cell // width
        if not (width * .18 < x < width * .82 and height * .18 < y < height * .82):
            continue
        for dx, dy in ((4, 0), (0, 4), (-4, 0), (0, -4), (6, 0), (0, 6), (8, 0), (0, 8), (-8, 0), (0, -8), (12, 0), (0, 12), (8, 8), (-8, 8)):
            xx, yy = x + dx, y + dy
            if not (0 <= xx < width and 0 <= yy < height):
                continue
            for j in cells[yy * width + xx]:
                if abs(xyz[i][2] - xyz[j][2]) > 18 or len(graph["neighbors"][j]) < 2:
                    continue
                if graph["component"][i] != graph["component"][j]:
                    continue
                z = max(xyz[i][2], xyz[j][2]) + 36
                if collision.clear((*xyz[i][:2], z), (*xyz[j][:2], z)):
                    continue
                seen, queue = {i}, deque([(i, 0)])
                while queue:
                    k, distance = queue.popleft()
                    if distance >= 40:
                        continue
                    for nxt in graph["neighbors"][k]:
                        if nxt not in seen:
                            seen.add(nxt)
                            queue.append((nxt, distance + 1))
                if j not in seen:
                    return i, j
    raise RuntimeError("No clear wall comparison found; do not invent evidence")


def verify_live_fixtures(collision, graph, matrix, width):
    p = (320, 1744)
    endpoints = [collision.contents((*p, z)) for z in (1, 18, 36, 72)]
    assert endpoints == [-1, -1, -2, -1]
    assert not collision.clear((*p, 1), (*p, 72))
    stacked = []
    for z in (-128, 96):
        p = (304, 2096)
        assert collision.contents((*p, z - 1)) == -2
        assert collision.clear((*p, z + 1), (*p, z + 72))
        stacked.append(z)
    u, v = project(matrix, (304, 2096))
    cell = int(v) * width + int(u)
    ids = graph["cells"][cell]
    heights = [graph["xyz"][i][2] for i in ids]
    assert any(abs(z + 128) < 1 for z in heights) and any(abs(z - 96) < 1 for z in heights)
    assert all(b not in graph["neighbors"][a] for a in ids for b in ids)
    return [dict(name="live_dust2_obstacle_between_empty_headroom_endpoints", passed=True,
                 world_xy=[320, 1744], contents_at_z_1_18_36_72=endpoints),
            dict(name="live_dust2_two_floors_same_xy_remain_separate", passed=True,
                 world_xy=[304, 2096], floor_heights=stacked, sampled_node_ids=ids,
                 sampled_node_heights=heights, direct_vertical_edges=0)]


def shortest_distance(graph, source, probe):
    queue, seen = deque([(source, 0)]), {source}
    while queue:
        node, distance = queue.popleft()
        if node == probe:
            return distance
        for nxt in graph["neighbors"][node]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, distance + 1))
    return None


def comparison_image(background, graph, source, probe, ordinary, constrained, width, height, output):
    peak = max(float(ordinary.max()), float(constrained.max()))
    views = []
    for mode in (0, 1):
        layer = np.zeros((height * width, 4), dtype=np.uint8)
        values = ordinary.copy() if mode == 0 else np.zeros(width * height)
        if mode:
            np.maximum.at(values, np.array(graph["pixel"]), constrained)
        t = np.clip(values / peak, 0, 1) ** .45
        layer[:, 0] = 255
        layer[:, 1] = (210 * (1 - t)).astype(np.uint8)
        layer[:, 2] = 35
        layer[:, 3] = (210 * t).astype(np.uint8)
        overlay = Image.fromarray(layer.reshape(height, width, 4)).resize(background.size, Image.Resampling.NEAREST)
        canvas = background.convert("RGBA")
        canvas.alpha_composite(overlay)
        draw = ImageDraw.Draw(canvas)
        for node, color in ((source, "white"), (probe, "cyan")):
            cell = graph["pixel"][node]
            x, y = (cell % width + .5) * background.width / width, (cell // width + .5) * background.height / height
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=color, width=2)
        views.append(canvas.convert("RGB"))
    result = Image.new("RGB", (background.width * 2, background.height))
    result.paste(views[0], (0, 0))
    result.paste(views[1], (background.width, 0))
    result.save(output)
    # A readable evidence crop at normal chat/report width, not a screenshot.
    detail = Image.new("RGB", (1280, 438), "#101820")
    label = ImageDraw.Draw(detail)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 25)
        small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    except OSError:
        font = small = ImageFont.load_default()
    cell = graph["pixel"][source]
    cx, cy = (cell % width + .5) * background.width / width, (cell // width + .5) * background.height / height
    cropw, croph = 200, 100
    sx, sy = max(0, min(background.width - cropw, int(cx - cropw / 2))), max(0, min(background.height - croph, int(cy - croph / 2)))
    for side, title in enumerate(("Без учёта стен", "С учётом BSP")):
        x = side * 640
        label.text((x + 18, 12), title, fill="#e2ebef", font=font)
        crop = views[side].crop((sx, sy, sx + cropw, sy + croph)).resize((620, 310), Image.Resampling.NEAREST)
        detail.paste(crop, (x + 10, 53))
        value = ordinary[graph["pixel"][probe]] if side == 0 else constrained[probe]
        label.text((x + 18, 372), f"В голубой точке: {value:.3e}", fill="#62edff", font=small)
    label.text((18, 408), "de_dust2 · синтетическое событие · белый круг: источник · 150 шагов · общая шкала цвета", fill="#aec0cb", font=small)
    detail.save(output.with_name("comparison-detail.png"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bsp", type=Path)
    parser.add_argument("--overview", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    checks = verify_invariants()
    if args.verify_only:
        print(json.dumps(checks, indent=2))
        return
    if not all((args.bsp, args.overview, args.image, args.output)):
        parser.error("--bsp, --overview, --image and --output are required")
    if args.width < 64 or args.width > 512 or args.width % 4:
        parser.error("--width must be divisible by 4, from 64 to 512")
    start = time.perf_counter()
    bsp = read_bsp(args.bsp)
    collision = WorldCollision(args.bsp)
    width, height = args.width, args.width * 3 // 4
    overview = args.overview.read_text()
    matrix = overview_transform(overview, width, height)
    graph = build_graph(bsp, collision, matrix, width, height)
    live_checks = verify_live_fixtures(collision, graph, matrix, width) if bsp["sha256"] == "15945389528d113562ede0a2c80647ebfa799079ed1c05a25379bcf84e4e9286" else []
    source, probe = find_wall_example(graph, collision, width, height)
    iterations = 150
    ordinary = unrestricted(width, height, graph["pixel"][source], iterations)
    constrained = diffuse(len(graph["xyz"]), graph["edges"], [source], iterations)
    elapsed = time.perf_counter() - start
    args.output.mkdir(parents=True, exist_ok=True)
    background = Image.open(args.image).convert("RGB")
    bitmap = np.array(background)
    chromakey = np.all(bitmap == (0, 255, 0), axis=2)
    bitmap[chromakey] = (16, 32, 43)
    background = Image.fromarray(bitmap)
    background = Image.blend(background, Image.new("RGB", background.size, "#10202b"), .48)
    stream = io.BytesIO()
    background.save(stream, format="JPEG", quality=88)
    example = dict(source_node=source, probe_node=probe, source_world=graph["xyz"][source],
                   probe_world=graph["xyz"][probe], direct_segment_at_chest_blocked=True,
                   graph_distance_greater_than=40, iterations=iterations, alpha=.24,
                   graph_shortest_distance=shortest_distance(graph, source, probe),
                   ordinary_probe=float(ordinary[graph["pixel"][probe]]),
                   constrained_probe=float(constrained[probe]),
                   ordinary_total_mass=float(ordinary.sum()), constrained_total_mass=float(constrained.sum()),
                   ordinary_max=float(ordinary.max()), constrained_max=float(constrained.max()))
    report = dict(status="offline_experiment_only", map=args.bsp.stem, bsp_sha256=bsp["sha256"],
                  grid=[width, height], world_units_per_cell=1 / max(abs(v) for v in (matrix[0], matrix[1], matrix[3], matrix[4])),
                  headroom=72, max_step=22, minimum_upward_normal=.7, graph=graph["diagnostics"],
                  largest_component_sizes=sorted(graph["component_sizes"], reverse=True)[:20],
                  example=example, invariant_checks=checks, live_bsp_checks=live_checks,
                  background_chromakey_pixels=int(chromakey.sum()), elapsed_seconds=elapsed,
                  asset_sha256={"overview":hashlib.sha256(args.overview.read_bytes()).hexdigest(), "image":hashlib.sha256(args.image.read_bytes()).hexdigest()},
                  limitations=["Synthetic events, not actual player statistics", "Point-clearance hull 0, not player-width navigation", "Dynamic brush entities ignored", "Roofs and small components retained and counted, not classified as player-accessible", "Overlapping surfaces remain separate graph nodes; display maximum per XY, never sum", "Grid center sampling can miss narrow openings and subcell geometry", "Baseline is unrestricted diffusion, not the exact production Gaussian renderer"],
                  sources=["https://github.com/ValveSoftware/halflife/blob/master/utils/common/bspfile.h", "https://github.com/rehlds/ReHLDS/blob/master/rehlds/engine/world.cpp"])
    (args.output / "evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    data = dict(width=width, height=height, pixel=graph["pixel"], z=[round(p[2], 2) for p in graph["xyz"]],
                edges=graph["edges"], example=example, report=report,
                image="data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii"))
    template = Path(__file__).with_name("heatmap_bsp_experiment.html").read_text(encoding="utf-8")
    html = template.replace("__EXPERIMENT_DATA__", json.dumps(data, separators=(",", ":")))
    (args.output / "index.html").write_text(html, encoding="utf-8")
    comparison_image(background, graph, source, probe, ordinary, constrained, width, height, args.output / "comparison.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
