from __future__ import annotations

import argparse
import html
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hlstats_py.heatmaps import (  # noqa: E402
    HeatmapConfig,
    HeatmapPoint,
    HeatmapRepository,
    collect_projection_stats,
    effective_image_size,
    load_settings,
    normalize_crop,
    normalize_scale,
    parse_goldsrc_overview,
    parse_source_overview,
)
from hlx_core.bootstrap import database_config_from_proxy_config  # noqa: E402
from hlx_core.db import SyncDatabaseAdapter  # noqa: E402
from PIL import Image  # noqa: E402


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="heatmap_projection_calibrate",
        description="DB-first heatmap projection preview and guarded config apply tool.",
    )
    parser.add_argument("--configfile", type=Path, required=True, help="Path to hlstats.conf")
    parser.add_argument("--game", required=True, help="Visible HLstats game code, e.g. cstrike")
    parser.add_argument("--map", dest="map_name", required=True, help="Map name, e.g. de_dust2")
    parser.add_argument("--heatmaps-root", type=Path, help="Path to the legacy heatmaps directory")
    parser.add_argument("--assets-root", type=Path, help="Path to heatmaps/src")
    parser.add_argument("--kill-limit", type=int, default=10_000, help="Maximum DB points to preview")
    parser.add_argument("--output", type=Path, help="HTML preview output path")
    parser.add_argument("--overview-file", type=Path, help="GoldSrc or Source overview .txt to import")
    parser.add_argument(
        "--overview-format",
        choices=("auto", "goldsrc", "source"),
        default="auto",
        help="Overview file format",
    )
    parser.add_argument("--apply", action="store_true", help="Apply projection values to hlstats_Heatmap_Config")
    parser.add_argument(
        "--runtime-gate-approved",
        action="store_true",
        help="Explicitly acknowledge the separate runtime gate required by --apply.",
    )
    parser.add_argument("--xoffset", type=int, help="Projection xoffset to apply")
    parser.add_argument("--yoffset", type=int, help="Projection yoffset to apply")
    parser.add_argument("--scale", type=float, help="Projection scale to apply")
    parser.add_argument("--flipx", type=int, choices=(0, 1), help="Projection flipx to apply")
    parser.add_argument("--flipy", type=int, choices=(0, 1), help="Projection flipy to apply")
    parser.add_argument("--rotate", type=int, choices=(0, 1, 2, 3), help="Projection quarter-turn rotate to apply")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Minimum in-bounds ratio required for --apply unless --force is used",
    )
    parser.add_argument("--force", action="store_true", help="Allow --apply below threshold")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.apply and not args.runtime_gate_approved:
        parser.error("--apply requires --runtime-gate-approved")
    if args.scale is not None and (not math.isfinite(args.scale) or args.scale <= 0):
        parser.error("--scale must be a finite value greater than zero")
    return args


def load_heatmap_settings(args: argparse.Namespace):
    cli = [
        "--configfile",
        str(args.configfile),
        "--game",
        args.game,
        "--map",
        args.map_name,
        "--kill-limit",
        str(args.kill_limit),
        "--debug-level",
        "0",
    ]
    if args.heatmaps_root:
        cli.extend(["--heatmaps-root", str(args.heatmaps_root)])
    if args.assets_root:
        cli.extend(["--assets-root", str(args.assets_root)])
    return load_settings(cli)


def selected_config(repository: HeatmapRepository, game: str, map_name: str) -> HeatmapConfig:
    configs = repository.fetch_map_configs()
    try:
        return configs[game][map_name]
    except KeyError as exc:
        raise RuntimeError(f"heatmap config not found for {game}/{map_name}") from exc


def override_from_args(config: HeatmapConfig, args: argparse.Namespace) -> HeatmapConfig:
    updates = {}
    for name in ("xoffset", "yoffset", "scale"):
        value = getattr(args, name)
        if value is not None:
            if name == "scale" and value <= 0:
                raise ValueError("--scale must be greater than zero")
            updates[name] = normalize_scale(value) if name == "scale" else value
    for name in ("flipx", "flipy"):
        value = getattr(args, name)
        if value is not None:
            updates[name] = bool(value)
    if args.rotate is not None:
        updates["rotate"] = args.rotate % 4
    return replace(config, **updates)


def override_from_overview(config: HeatmapConfig, args: argparse.Namespace) -> HeatmapConfig:
    if args.overview_file is None:
        return config
    content = args.overview_file.read_text(encoding="utf-8", errors="replace")
    fmt = args.overview_format
    if fmt == "auto":
        fmt = "source" if '"pos_x"' in content or '"scale"' in content else "goldsrc"
    if fmt == "goldsrc":
        imported = parse_goldsrc_overview(
            content,
            code=config.code,
            game=config.game,
            map_name=config.map_name,
        )
    else:
        imported = parse_source_overview(
            content,
            code=config.code,
            game=config.game,
            map_name=config.map_name,
        )
    imported_config = imported.to_legacy_config()
    return replace(
        config,
        xoffset=imported_config.xoffset,
        yoffset=imported_config.yoffset,
        scale=imported_config.scale,
        flipx=imported_config.flipx,
        flipy=imported_config.flipy,
        rotate=imported_config.rotate,
    )


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def fetch_points(repository: HeatmapRepository, config: HeatmapConfig, limit: int) -> list[HeatmapPoint]:
    return repository.fetch_points(
        config,
        ignore_infected=False,
        kill_limit=limit,
        start_timestamp=None,
    )


def write_preview(
    output: Path,
    *,
    image_path: Path,
    image_size_value: tuple[int, int],
    points: list[HeatmapPoint],
    config: HeatmapConfig,
) -> None:
    raw_points = [{"x": point.pos_x, "y": point.pos_y} for point in points]
    payload = {
        "image": image_path.resolve().as_uri(),
        "width": image_size_value[0],
        "height": image_size_value[1],
        "points": raw_points,
        "config": {
            "xoffset": config.xoffset,
            "yoffset": config.yoffset,
            "scale": config.scale,
            "flipx": int(config.flipx),
            "flipy": int(config.flipy),
            "rotate": int(config.rotate),
            "cropx1": int(config.cropx1),
            "cropy1": int(config.cropy1),
            "cropx2": int(config.cropx2),
            "cropy2": int(config.cropy2),
            "game": config.game,
        },
        "game": config.code,
        "map": config.map_name,
    }
    data = json.dumps(payload, separators=(",", ":"))
    title = html.escape(f"{config.code}/{config.map_name} heatmap projection")
    output.write_text(
        f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font: 13px Arial, sans-serif; margin: 16px; color: #222; }}
.layout {{ display: flex; gap: 16px; align-items: flex-start; }}
.stage {{ position: relative; line-height: 0; max-width: min(1280px, 75vw); }}
.stage img {{ display: block; max-width: 100%; height: auto; }}
.stage canvas {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
.panel {{ width: 280px; }}
label {{ display: grid; grid-template-columns: 76px 1fr 58px; gap: 6px; align-items: center; margin-bottom: 8px; }}
input[type=number] {{ width: 58px; }}
textarea {{ width: 100%; height: 90px; font: 11px Consolas, monospace; }}
.bad {{ color: #a22; font-weight: bold; }}
.ok {{ color: #176a2c; font-weight: bold; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="layout">
<div class="stage"><img id="map" src=""><canvas id="canvas"></canvas></div>
<div class="panel">
<p id="stats"></p>
<label>xoffset <input id="xoffset" type="range" min="-8000" max="12000" step="1"><input id="xoffset_n" type="number"></label>
<label>yoffset <input id="yoffset" type="range" min="-8000" max="12000" step="1"><input id="yoffset_n" type="number"></label>
<label>scale <input id="scale" type="range" min="0.1" max="32" step="0.01"><input id="scale_n" type="number" step="0.01"></label>
<label>flipx <input id="flipx" type="checkbox"><span></span></label>
<label>flipy <input id="flipy" type="checkbox"><span></span></label>
<label>rotate <input id="rotate" type="number" min="0" max="3" step="1"><span></span></label>
<textarea id="sql" readonly></textarea>
</div>
</div>
<script>
const data = {data};
const img = document.getElementById('map');
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const fields = ['xoffset', 'yoffset', 'scale'];
img.src = data.image;
canvas.width = data.width;
canvas.height = data.height;
function bind(id) {{
  const range = document.getElementById(id);
  const number = document.getElementById(id + '_n');
  range.value = data.config[id];
  number.value = data.config[id];
  range.oninput = () => {{ number.value = range.value; draw(); }};
  number.oninput = () => {{ range.value = number.value; draw(); }};
}}
fields.forEach(bind);
['flipx','flipy'].forEach(id => {{
  const input = document.getElementById(id);
  input.checked = Boolean(data.config[id]);
  input.onchange = draw;
}});
document.getElementById('rotate').value = data.config.rotate || 0;
document.getElementById('rotate').oninput = draw;
function normalizeRotation(value) {{
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  const rounded = Math.round(numeric) % 4;
  return rounded < 0 ? rounded + 4 : rounded;
}}
function normalizeScale(value) {{
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 1;
}}
function rotatePoint(x, y, steps) {{
  const normalized = normalizeRotation(steps);
  if (normalized === 1) return {{x: -y, y: x}};
  if (normalized === 2) return {{x: -x, y: -y}};
  if (normalized === 3) return {{x: y, y: -x}};
  return {{x, y}};
}}
function unrotatePoint(x, y, steps) {{
  return rotatePoint(x, y, 4 - normalizeRotation(steps));
}}
function cfg() {{
  return {{
    xoffset: Number(document.getElementById('xoffset_n').value),
    yoffset: Number(document.getElementById('yoffset_n').value),
    scale: normalizeScale(document.getElementById('scale_n').value),
    flipx: document.getElementById('flipx').checked ? 1 : 0,
    flipy: document.getElementById('flipy').checked ? 1 : 0,
    rotate: normalizeRotation(document.getElementById('rotate').value),
    cropx1: data.config.cropx1 || 0,
    cropy1: data.config.cropy1 || 0,
    cropx2: data.config.cropx2 || 0,
    cropy2: data.config.cropy2 || 0
  }};
}}
function project(p, c) {{
  const xw = c.flipx ? -p.x : p.x;
  const yw = c.flipy ? -p.y : p.y;
  let x = Math.trunc((xw + c.xoffset) / c.scale);
  let y = Math.trunc((yw + c.yoffset) / c.scale);
  const rotated = rotatePoint(x, y, c.rotate);
  x = rotated.x;
  y = rotated.y;
  if (c.cropx2 > 0 && c.cropy2 > 0) {{
    x -= c.cropx1;
    y -= c.cropy1;
  }}
  return {{x, y}};
}}
function draw() {{
  const c = cfg();
  let inBounds = 0;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  data.points.forEach(p => {{
    const q = project(p, c);
    const ok = q.x >= 0 && q.y >= 0 && q.x < data.width && q.y < data.height;
    if (ok) inBounds++;
    ctx.fillStyle = ok ? 'rgba(255,40,0,.65)' : 'rgba(0,60,255,.35)';
    ctx.beginPath();
    ctx.arc(Math.max(0, Math.min(data.width - 1, q.x)), Math.max(0, Math.min(data.height - 1, q.y)), ok ? 5 : 3, 0, Math.PI * 2);
    ctx.fill();
  }});
  const ratio = data.points.length ? inBounds / data.points.length : 0;
  document.getElementById('stats').className = ratio >= .8 ? 'ok' : 'bad';
  document.getElementById('stats').textContent = inBounds + '/' + data.points.length + ' in bounds (' + ratio.toFixed(3) + ')';
  document.getElementById('sql').value =
    `UPDATE hlstats_Heatmap_Config SET xoffset=${{Math.round(c.xoffset)}}, yoffset=${{Math.round(c.yoffset)}}, scale=${{c.scale}}, flipx=${{c.flipx}}, flipy=${{c.flipy}}, rotate=${{c.rotate}} WHERE game='${{data.config.game}}' AND map='${{data.map}}';`;
}}
img.onload = function() {{
  if (!img.getAttribute('data-cropped') && data.config.cropx2 > 0 && data.config.cropy2 > 0) {{
    const crop = document.createElement('canvas');
    crop.width = data.config.cropx2;
    crop.height = data.config.cropy2;
    crop.getContext('2d').drawImage(img, data.config.cropx1, data.config.cropy1, crop.width, crop.height, 0, 0, crop.width, crop.height);
    img.setAttribute('data-cropped', '1');
    img.src = crop.toDataURL('image/jpeg', 0.92);
    return;
  }}
  draw();
}};
draw();
</script>
</body>
</html>
""",
        encoding="utf-8",
    )


def apply_projection(adapter: SyncDatabaseAdapter, config: HeatmapConfig) -> None:
    cursor = adapter.connection().cursor()
    try:
        cursor.execute(
            """
            UPDATE hlstats_Heatmap_Config
            SET xoffset = %s, yoffset = %s, scale = %s, flipx = %s, flipy = %s, rotate = %s
            WHERE game = %s AND map = %s
            """,
            (
                config.xoffset,
                config.yoffset,
                config.scale,
                int(config.flipx),
                int(config.flipy),
                int(config.rotate),
                config.game,
                config.map_name,
            ),
        )
    finally:
        cursor.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = load_heatmap_settings(args)

    adapter = SyncDatabaseAdapter(database_config_from_proxy_config(settings.config))
    repository = HeatmapRepository(adapter)
    repository.connect()
    try:
        config = selected_config(repository, args.game, args.map_name)
        try:
            config = override_from_overview(config, args)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        config = override_from_args(config, args)
        image_path = settings.assets_root / config.game / f"{config.map_name}.jpg"
        if not image_path.exists():
            print(f"error: map image not found: {image_path}", file=sys.stderr)
            return 1
        size = image_size(image_path)
        config = normalize_crop(config, size)
        canvas_size = effective_image_size(config, size)
        points = fetch_points(repository, config, args.kill_limit)
        stats = collect_projection_stats(points, config, image_size=canvas_size)

        if args.apply:
            if stats.in_bounds_ratio < args.threshold and not args.force:
                print(
                    f"error: projection ratio {stats.in_bounds_ratio:.3f} is below threshold {args.threshold:.3f}",
                    file=sys.stderr,
                )
                return 1
            apply_projection(adapter, config)
            print(
                f"applied {config.code}/{config.map_name}: "
                f"{stats.in_bounds}/{stats.queried} in bounds ({stats.in_bounds_ratio:.3f})"
            )
            return 0

        output = args.output or Path(f"heatmap_projection_{args.game}_{args.map_name}.html")
        write_preview(output, image_path=image_path, image_size_value=canvas_size, points=points, config=config)
        print(
            f"wrote {output}: {stats.in_bounds}/{stats.queried} in bounds "
            f"({stats.in_bounds_ratio:.3f})"
        )
        return 0
    finally:
        repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
