"""Legacy-compatible batch heatmap generator for HLstatsX."""

from __future__ import annotations

import argparse
import math
import re
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from hlx_core.bootstrap import database_config_from_proxy_config
from hlx_core.config import ConfigError, ProxyConfig, load_config
from hlx_core.db import SyncDatabaseAdapter

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - depends on runtime environment
    raise RuntimeError("Pillow is required for heatmap generation") from exc


LEGACY_HUD_URL = "http://www.hlxcommunity.com"
LEGACY_KILL_LIMIT = 10_000
LEGACY_OUTPUT_SIZES: dict[str, tuple[int, int] | None] = {
    "small": (800, 600),
    "medium": (1024, 768),
    "large": None,
}
LEGACY_CACHE_MAX_AGE_DAYS = 30
_CACHE_PATTERN = re.compile(r"^(?P<map>.+)_(?P<timestamp>\d+)\.png$", re.IGNORECASE)
_SOURCE_OVERVIEW_PAIR = re.compile(r'"(?P<key>[^"]+)"\s+"(?P<value>[^"]*)"')


def rotation_steps(value: Any) -> int:
    """Normalize stored heatmap rotation to quarter-turn steps."""

    return int(value or 0) % 4


def normalize_scale(value: Any) -> float:
    """Return a finite positive projection scale for all render paths."""

    try:
        scale = float(value)
    except (TypeError, ValueError):
        return 1.0
    return scale if math.isfinite(scale) and scale > 0 else 1.0


@dataclass(frozen=True, slots=True)
class HeatmapCliOptions:
    """Raw CLI options accepted by the batch generator."""

    configfile: Path
    game: str | None
    map_name: str | None
    disable_cache: bool
    ignore_infected: bool
    web_root: Path | None
    heatmaps_root: Path | None
    assets_root: Path | None
    cache_root: Path | None
    font_path: Path | None
    hud_url: str
    output_size: str
    kill_limit: int
    debug_level: int
    diagnose: bool
    diagnose_projection: bool
    legacy_visuals: bool


@dataclass(frozen=True, slots=True)
class HeatmapSettings:
    """Expanded runtime settings derived from CLI and ``hlstats.conf``."""

    config: ProxyConfig
    cli: HeatmapCliOptions
    repo_root: Path
    web_root: Path
    heatmaps_root: Path
    assets_root: Path
    cache_root: Path
    font_path: Path
    hud_url: str
    output_size: str
    kill_limit: int
    debug_level: int
    diagnose: bool
    diagnose_projection: bool
    legacy_visuals: bool


@dataclass(frozen=True, slots=True)
class HeatmapConfig:
    """One row from ``hlstats_Heatmap_Config`` mapped to a concrete game code."""

    code: str
    game: str
    map_name: str
    xoffset: int
    yoffset: int
    flipx: bool
    flipy: bool
    rotate: int
    days: int
    brush: str
    scale: float
    font: int
    thumbw: float
    thumbh: float
    cropx1: int
    cropx2: int
    cropy1: int
    cropy2: int


def rotate_point(x: int, y: int, steps: int) -> tuple[int, int]:
    """Rotate a projected point counter-clockwise by quarter turns."""

    normalized = rotation_steps(steps)
    if normalized == 1:
        return -y, x
    if normalized == 2:
        return -x, -y
    if normalized == 3:
        return y, -x
    return x, y


def unrotate_point(x: int, y: int, steps: int) -> tuple[int, int]:
    """Apply the inverse of :func:`rotate_point`."""

    return rotate_point(x, y, 4 - rotation_steps(steps))


def normalize_crop(config: HeatmapConfig, image_size: tuple[int, int]) -> HeatmapConfig:
    """Clamp a crop rectangle to the source JPEG without mutating stored config."""

    width, height = max(0, int(image_size[0])), max(0, int(image_size[1]))
    x1 = max(0, int(config.cropx1))
    y1 = max(0, int(config.cropy1))
    x2 = max(0, int(config.cropx2))
    y2 = max(0, int(config.cropy2))
    if x2 <= 0 or y2 <= 0 or width <= 0 or height <= 0:
        return replace(config, cropx1=0, cropy1=0, cropx2=0, cropy2=0)
    x1 = min(width - 1, x1)
    y1 = min(height - 1, y1)
    x2 = min(width - x1, x2)
    y2 = min(height - y1, y2)
    if x2 <= 0 or y2 <= 0:
        return replace(config, cropx1=0, cropy1=0, cropx2=0, cropy2=0)
    return replace(config, cropx1=x1, cropy1=y1, cropx2=x2, cropy2=y2)


def effective_image_size(config: HeatmapConfig, image_size: tuple[int, int]) -> tuple[int, int]:
    """Return the canvas size after applying a normalized crop."""

    normalized = normalize_crop(config, image_size)
    if normalized.cropx2 > 0 and normalized.cropy2 > 0:
        return normalized.cropx2, normalized.cropy2
    return int(image_size[0]), int(image_size[1])


@dataclass(frozen=True, slots=True)
class HeatmapPoint:
    """One stored frag/teamkill position used to build the overlay."""

    event_time: datetime
    pos_x: int
    pos_y: int


@dataclass(frozen=True, slots=True)
class ImportedOverview:
    """Map overview metadata converted into the legacy projection shape."""

    projection: str
    code: str
    game: str
    map_name: str
    xoffset: int
    yoffset: int
    scale: float
    flipx: bool
    flipy: bool
    rotate: int
    image: str | None = None
    height: int | None = None
    material: str | None = None
    manual_required: bool = False

    def to_legacy_config(self) -> HeatmapConfig:
        return HeatmapConfig(
            code=self.code,
            game=self.game,
            map_name=self.map_name,
            xoffset=self.xoffset,
            yoffset=self.yoffset,
            flipx=self.flipx,
            flipy=self.flipy,
            rotate=self.rotate,
            days=30,
            brush="small",
            scale=self.scale,
            font=10,
            thumbw=0.170312,
            thumbh=0.170312,
            cropx1=0,
            cropx2=0,
            cropy1=0,
            cropy2=0,
        )


@dataclass(frozen=True, slots=True)
class ProjectionStats:
    """Diagnostic summary for one map's transformed heatmap coordinates."""

    queried: int
    in_bounds: int
    out_of_bounds: int
    min_x: int | None
    max_x: int | None
    min_y: int | None
    max_y: int | None
    cache_status: str
    raw_min_x: int | None = None
    raw_max_x: int | None = None
    raw_min_y: int | None = None
    raw_max_y: int | None = None

    @property
    def in_bounds_ratio(self) -> float:
        if self.queried <= 0:
            return 0.0
        return self.in_bounds / self.queried


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Cached overlay state reused across generator runs."""

    path: Path
    timestamp: int


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Outcome of one map render attempt."""

    code: str
    map_name: str
    generated: bool
    points: int
    output_file: Path | None = None
    diagnostics: ProjectionStats | None = None


class SupportsCursor(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...

    def close(self) -> None: ...


class SupportsConnection(Protocol):
    def cursor(self) -> SupportsCursor: ...


class HeatmapLogger:
    """Small logger mirroring the legacy ``show::Event`` output shape."""

    def __init__(self, debug_level: int) -> None:
        self._debug_level = debug_level

    def event(self, category: str, message: str, level: int) -> None:
        if level > self._debug_level:
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp}\t\t{category}: {message}")


class HeatmapRepository:
    """MySQL accessors for map metadata and kill coordinates."""

    _MAPINFO_QUERY = """
        SELECT
            g.code,
            hc.game,
            hc.map,
            hc.xoffset,
            hc.yoffset,
            hc.flipx,
            hc.flipy,
            hc.rotate,
            hc.days,
            hc.brush,
            hc.scale,
            hc.font,
            hc.thumbw,
            hc.thumbh,
            hc.cropx1,
            hc.cropx2,
            hc.cropy1,
            hc.cropy2
        FROM
            hlstats_Games AS g
        INNER JOIN
            hlstats_Heatmap_Config AS hc
        ON
            hc.game = g.realgame
        WHERE 1=1
        ORDER BY code ASC, game ASC, map ASC
    """
    _VISIBLE_GAMES_QUERY = "SELECT code FROM hlstats_Games WHERE hidden='0'"

    def __init__(self, adapter: SyncDatabaseAdapter) -> None:
        self._adapter = adapter

    def connect(self) -> None:
        self._adapter.connect()

    def close(self) -> None:
        self._adapter.close()

    def fetch_map_configs(self) -> dict[str, dict[str, HeatmapConfig]]:
        rows = self._fetchall(self._MAPINFO_QUERY, None)
        configs: dict[str, dict[str, HeatmapConfig]] = {}
        for row in rows:
            config = HeatmapConfig(
                code=str(row[0]),
                game=str(row[1]),
                map_name=str(row[2]),
                xoffset=int(row[3]),
                yoffset=int(row[4]),
                flipx=bool(int(row[5])),
                flipy=bool(int(row[6])),
                rotate=rotation_steps(row[7] or 0),
                days=int(row[8]),
                brush=str(row[9]),
                scale=normalize_scale(row[10]),
                font=int(row[11]),
                thumbw=float(row[12]),
                thumbh=float(row[13]),
                cropx1=int(row[14]),
                cropx2=int(row[15]),
                cropy1=int(row[16]),
                cropy2=int(row[17]),
            )
            configs.setdefault(config.code, {})[config.map_name] = config
        return configs

    def fetch_visible_games(self) -> list[str]:
        rows = self._fetchall(self._VISIBLE_GAMES_QUERY, None)
        return [str(row[0]) for row in rows]

    def fetch_points(
        self,
        config: HeatmapConfig,
        *,
        ignore_infected: bool,
        kill_limit: int,
        start_timestamp: int | None,
    ) -> list[HeatmapPoint]:
        query, params = build_points_query(
            config,
            ignore_infected=ignore_infected,
            kill_limit=kill_limit,
            start_timestamp=start_timestamp,
        )
        rows = self._fetchall(query, params)
        return [
            HeatmapPoint(
                event_time=row[4],
                pos_x=int(row[5]),
                pos_y=int(row[6]),
            )
            for row in rows
        ]

    def _fetchall(self, query: str, params: Sequence[Any] | None) -> Sequence[Any]:
        connection = self._adapter.connection()
        cursor = connection.cursor()
        try:
            if params is None:
                cursor.execute(query)
            else:
                cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()


class HeatmapGenerator:
    """Generate legacy-compatible heatmap JPEGs and cached overlays."""

    def __init__(
        self,
        settings: HeatmapSettings,
        repository: HeatmapRepository,
        *,
        clock: callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._clock = clock or time.time
        self._logger = HeatmapLogger(settings.debug_level)

    def run(self) -> list[GenerationResult]:
        self._repository.connect()
        try:
            map_configs = self._repository.fetch_map_configs()
            targets = select_target_maps(
                map_configs,
                visible_games=self._repository.fetch_visible_games(),
                game=self._settings.cli.game,
                map_name=self._settings.cli.map_name,
            )
            results: list[GenerationResult] = []
            for code, game_configs in targets.items():
                for map_name, config in game_configs.items():
                    results.append(self._generate_one(code, map_name, config))
            self._logger.event("CREATE", "Heatmap creation done.", 1)
            return results
        finally:
            self._repository.close()

    def _generate_one(self, code: str, map_name: str, config: HeatmapConfig) -> GenerationResult:
        source_path = self._settings.assets_root / config.game / f"{map_name}.jpg"
        if not source_path.exists():
            self._logger.event("FILE", f"{source_path} doesn't exist", 1)
            return GenerationResult(code=code, map_name=map_name, generated=False, points=0)

        output_dir = self._settings.web_root / "hlstatsimg" / "games" / code / "heatmaps"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._logger.event("PATH", str(output_dir), 3)
        base_image = Image.open(source_path).convert("RGBA")
        config = normalize_crop(config, base_image.size)

        cache_dir = self._settings.cache_root / code
        cache_entry = resolve_cache_entry(
            cache_dir,
            map_name,
            disable_cache=self._settings.cli.disable_cache,
            now=self._clock(),
            logger=self._logger,
        )
        points = self._repository.fetch_points(
            config,
            ignore_infected=self._settings.cli.ignore_infected,
            kill_limit=self._settings.kill_limit,
            start_timestamp=None if cache_entry is None else cache_entry.timestamp,
        )
        cache_status = "none" if cache_entry is None else "reused"
        if not points:
            diagnostics = ProjectionStats(
                queried=0,
                in_bounds=0,
                out_of_bounds=0,
                min_x=None,
                max_x=None,
                min_y=None,
                max_y=None,
                cache_status=cache_status,
            )
            self._log_projection_stats(code, map_name, diagnostics)
            self._logger.event(
                "IGNORE",
                f"Game: {code}, Map: {map_name}, Kills: 0, (to few kills)",
                1,
            )
            return GenerationResult(
                code=code,
                map_name=map_name,
                generated=False,
                points=0,
                diagnostics=diagnostics,
            )

        self._logger.event("CREATE", f"Game: {code}, Map: {map_name}, Kills: {len(points)}", 1)
        overlay_path = None if cache_entry is None else cache_entry.path
        overlay = load_overlay(base_image.size, overlay_path)
        first_event = min(point.event_time for point in points)
        diagnostics = collect_projection_stats(
            points,
            config,
            image_size=effective_image_size(config, base_image.size),
            cache_status=cache_status,
        )
        self._log_projection_stats(code, map_name, diagnostics)

        brush_image = load_brush(self._settings.assets_root, config.brush)
        brush = prepare_brush_for_visibility(
            brush_image,
            len(points),
            legacy_visuals=self._settings.legacy_visuals,
        )
        brush = apply_brush_opacity(
            brush,
            compute_opacity(len(points), legacy_visuals=self._settings.legacy_visuals),
        )

        for point in points:
            draw_brush_point(overlay, brush, point, config)

        rendered = compose_heatmap(base_image, overlay)
        rendered = crop_image(rendered, config)
        write_thumbnail(rendered, config, output_dir, map_name)
        final_image = draw_hud(
            resize_image(rendered, self._settings.output_size, self._logger),
            map_name,
            config,
            hud_url=self._settings.hud_url,
            font_path=self._settings.font_path,
            now=self._clock(),
        )

        output_file = output_dir / f"{map_name}-kill.jpg"
        final_image.convert("RGB").save(output_file, format="JPEG", quality=100)

        cache_dir.mkdir(parents=True, exist_ok=True)
        new_timestamp = int(self._clock())
        cache_path = cache_dir / f"{map_name}_{new_timestamp}.png"
        overlay.save(cache_path, format="PNG", compress_level=9)
        if cache_entry is not None and cache_entry.path.exists() and cache_entry.path != cache_path:
            cache_entry.path.unlink()

        self._logger.event(
            "CREATE",
            f"Generated {output_file.name} from {first_event.isoformat(sep=' ')}",
            2,
        )
        return GenerationResult(
            code=code,
            map_name=map_name,
            generated=True,
            points=len(points),
            output_file=output_file,
            diagnostics=diagnostics,
        )

    def _log_projection_stats(
        self,
        code: str,
        map_name: str,
        diagnostics: ProjectionStats,
    ) -> None:
        if not self._settings.diagnose and self._settings.debug_level < 2:
            return
        self._logger.event(
            "DIAG",
            (
                f"Game: {code}, Map: {map_name}, Points: {diagnostics.queried}, "
                f"InBounds: {diagnostics.in_bounds}, OutOfBounds: {diagnostics.out_of_bounds}, "
                f"Ratio: {diagnostics.in_bounds_ratio:.3f}, "
                f"RawX: {diagnostics.raw_min_x}..{diagnostics.raw_max_x}, "
                f"RawY: {diagnostics.raw_min_y}..{diagnostics.raw_max_y}, "
                f"X: {diagnostics.min_x}..{diagnostics.max_x}, "
                f"Y: {diagnostics.min_y}..{diagnostics.max_y}, "
                f"Cache: {diagnostics.cache_status}"
            ),
            1,
        )


class HeatmapProjectionDiagnoser:
    """DB-first projection report that does not write heatmap artifacts."""

    def __init__(self, settings: HeatmapSettings, repository: HeatmapRepository) -> None:
        self._settings = settings
        self._repository = repository
        self._logger = HeatmapLogger(max(1, settings.debug_level))

    def run(self) -> list[GenerationResult]:
        self._repository.connect()
        try:
            map_configs = self._repository.fetch_map_configs()
            targets = select_target_maps(
                map_configs,
                visible_games=self._repository.fetch_visible_games(),
                game=self._settings.cli.game,
                map_name=self._settings.cli.map_name,
            )
            results: list[GenerationResult] = []
            for code, game_configs in targets.items():
                for map_name, config in game_configs.items():
                    results.append(self._diagnose_one(code, map_name, config))
            return results
        finally:
            self._repository.close()

    def _diagnose_one(self, code: str, map_name: str, config: HeatmapConfig) -> GenerationResult:
        image_size = self._image_size(config, map_name)
        config = normalize_crop(config, image_size)
        canvas_size = effective_image_size(config, image_size)
        points = self._repository.fetch_points(
            config,
            ignore_infected=self._settings.cli.ignore_infected,
            kill_limit=self._settings.kill_limit,
            start_timestamp=None,
        )
        diagnostics = collect_projection_stats(points, config, image_size=canvas_size)
        self._logger.event(
            "PROJECTION",
            (
                f"Game: {code}, Map: {map_name}, Image: {canvas_size[0]}x{canvas_size[1]}, "
                f"Points: {diagnostics.queried}, InBounds: {diagnostics.in_bounds}, "
                f"OutOfBounds: {diagnostics.out_of_bounds}, Ratio: {diagnostics.in_bounds_ratio:.3f}, "
                f"RawX: {diagnostics.raw_min_x}..{diagnostics.raw_max_x}, "
                f"RawY: {diagnostics.raw_min_y}..{diagnostics.raw_max_y}, "
                f"X: {diagnostics.min_x}..{diagnostics.max_x}, "
                f"Y: {diagnostics.min_y}..{diagnostics.max_y}, "
                f"Config: xoffset={config.xoffset}, yoffset={config.yoffset}, "
                f"scale={config.scale}, flipx={int(config.flipx)}, flipy={int(config.flipy)}, "
                f"rotate={rotation_steps(config.rotate)}"
            ),
            1,
        )
        return GenerationResult(
            code=code,
            map_name=map_name,
            generated=False,
            points=len(points),
            diagnostics=diagnostics,
        )

    def _image_size(self, config: HeatmapConfig, map_name: str) -> tuple[int, int]:
        source_path = self._settings.assets_root / config.game / f"{map_name}.jpg"
        if not source_path.exists():
            self._logger.event("FILE", f"{source_path} doesn't exist", 1)
            return (0, 0)
        with Image.open(source_path) as image:
            return image.size


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser matching the legacy batch generator behaviour."""

    parser = argparse.ArgumentParser(prog="hlstats-heatmaps")
    parser.add_argument("--configfile", type=Path, required=True, help="Path to hlstats.conf")
    parser.add_argument("--game", help="Generate only one visible HLstats game code")
    parser.add_argument("--map", dest="map_name", help="Generate only one map for --game")
    parser.add_argument(
        "--disablecache",
        "--disable-cache",
        action="store_true",
        dest="disable_cache",
        help="Ignore cached overlays and regenerate from scratch",
    )
    parser.add_argument(
        "--ignoreinfected",
        "--ignore-infected",
        action="store_true",
        dest="ignore_infected",
        help="Exclude infected victims from frag input when supported by the game",
    )
    parser.add_argument("--web-root", type=Path, help="Path to the legacy PHP web root")
    parser.add_argument("--heatmaps-root", type=Path, help="Path to the legacy heatmaps directory")
    parser.add_argument("--assets-root", type=Path, help="Path to heatmaps/src")
    parser.add_argument("--cache-root", type=Path, help="Path to heatmaps/cache")
    parser.add_argument("--font-path", type=Path, help="Path to the HUD TTF font")
    parser.add_argument(
        "--hud-url",
        default=LEGACY_HUD_URL,
        help="Footer URL rendered into the HUD",
    )
    parser.add_argument(
        "--output-size",
        choices=tuple(LEGACY_OUTPUT_SIZES),
        default="medium",
        help="Legacy output size preset",
    )
    parser.add_argument(
        "--kill-limit",
        type=int,
        default=LEGACY_KILL_LIMIT,
        help="Maximum number of frags and teamkills queried per map bucket",
    )
    parser.add_argument(
        "--debug-level",
        type=int,
        default=1,
        help="Legacy-style logging verbosity (1-3)",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print projection diagnostics for each generated map",
    )
    parser.add_argument(
        "--diagnose-projection",
        action="store_true",
        help="Print DB-first projection diagnostics without generating image outputs",
    )
    parser.add_argument(
        "--legacy-visuals",
        action="store_true",
        help="Use legacy opacity and brush sizing without sparse-map visibility boosts",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> HeatmapCliOptions:
    """Parse *argv* into a structured CLI options object."""

    parsed = build_parser().parse_args(list(argv) if argv is not None else None)
    return HeatmapCliOptions(
        configfile=parsed.configfile,
        game=parsed.game,
        map_name=parsed.map_name,
        disable_cache=parsed.disable_cache,
        ignore_infected=parsed.ignore_infected,
        web_root=parsed.web_root,
        heatmaps_root=parsed.heatmaps_root,
        assets_root=parsed.assets_root,
        cache_root=parsed.cache_root,
        font_path=parsed.font_path,
        hud_url=parsed.hud_url,
        output_size=parsed.output_size,
        kill_limit=parsed.kill_limit,
        debug_level=parsed.debug_level,
        diagnose=parsed.diagnose,
        diagnose_projection=parsed.diagnose_projection,
        legacy_visuals=parsed.legacy_visuals,
    )


def load_settings(argv: Sequence[str] | None = None) -> HeatmapSettings:
    """Load configuration and derive filesystem defaults for the generator."""

    options = parse_args(argv)
    if options.map_name and not options.game:
        raise ConfigError("--map requires --game")
    if options.kill_limit <= 0:
        raise ConfigError("--kill-limit must be greater than zero")
    if options.debug_level < 0:
        raise ConfigError("--debug-level must be non-negative")

    config = load_config(options.configfile)
    repo_root = Path(__file__).resolve().parents[2]
    heatmaps_root = (options.heatmaps_root or (repo_root / "heatmaps")).resolve()
    assets_root = (options.assets_root or (heatmaps_root / "src")).resolve()
    cache_root = (options.cache_root or (heatmaps_root / "cache")).resolve()
    font_path = (options.font_path or (heatmaps_root / "DejaVuSans.ttf")).resolve()
    web_root = (options.web_root or (repo_root / "web")).resolve()

    return HeatmapSettings(
        config=config,
        cli=options,
        repo_root=repo_root,
        web_root=web_root,
        heatmaps_root=heatmaps_root,
        assets_root=assets_root,
        cache_root=cache_root,
        font_path=font_path,
        hud_url=options.hud_url,
        output_size=options.output_size,
        kill_limit=options.kill_limit,
        debug_level=options.debug_level,
        diagnose=options.diagnose,
        diagnose_projection=options.diagnose_projection,
        legacy_visuals=options.legacy_visuals,
    )


def select_target_maps(
    map_configs: dict[str, dict[str, HeatmapConfig]],
    *,
    visible_games: Iterable[str],
    game: str | None,
    map_name: str | None,
) -> dict[str, dict[str, HeatmapConfig]]:
    """Apply legacy ``--game`` / ``--map`` selection rules."""

    if game is not None:
        if game not in map_configs:
            raise ConfigError(f"Game: {game} doesn't exists, escaping")
        if map_name is not None:
            if map_name not in map_configs[game]:
                raise ConfigError(f"Game: {game} Map: {map_name} doesn't exists, escaping")
            return {game: {map_name: map_configs[game][map_name]}}
        return {game: dict(map_configs[game])}

    selected: dict[str, dict[str, HeatmapConfig]] = {}
    for code in visible_games:
        if code in map_configs:
            selected[code] = dict(map_configs[code])
    return selected


def parse_goldsrc_overview(
    content: str,
    *,
    code: str,
    game: str,
    map_name: str,
    native_width: int | None = None,
    native_height: int | None = None,
    registered_native_frame: bool = False,
) -> ImportedOverview:
    """Convert SDK overview coordinates only for an explicitly registered native frame.

    Arbitrary repository JPGs require native-to-served image registration first.
    Use heatmap_bsp_registration.py for that workflow; ZOOM is not units/pixel.
    """
    if not registered_native_frame or not native_width or not native_height:
        raise ValueError('GoldSrc TXT alone cannot register the served image. Use scripts/heatmap_bsp_registration.py; native dimensions and registered_native_frame are required.')
    if native_width <= 0 or native_height <= 0 or native_width * 3 != native_height * 4:
        raise ValueError('GoldSrc native overview frame must have a 4:3 aspect ratio')

    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line or line in {"{", "}"}:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].upper()
        if key in {"ZOOM", "HEIGHT", "IMAGE", "ROTATED"}:
            values[key] = parts[1].strip('"')
        elif key == "ORIGIN" and len(parts) >= 3:
            values["ORIGIN_X"] = parts[1]
            values["ORIGIN_Y"] = parts[2]

    missing = {"ZOOM", "ORIGIN_X", "ORIGIN_Y"} - set(values)
    if missing:
        raise ValueError(f"GoldSrc overview missing required keys: {', '.join(sorted(missing))}")

    zoom = float(values['ZOOM'])
    origin_x, origin_y = float(values['ORIGIN_X']), float(values['ORIGIN_Y'])
    if not all(math.isfinite(value) for value in (zoom, origin_x, origin_y)) or zoom <= 0:
        raise ValueError('GoldSrc overview requires finite origins and positive zoom')
    scale = 8192.0 / (zoom * native_width)
    rotated = values.get('ROTATED', '0').lower() not in {'0', 'false'}

    return ImportedOverview(
        projection="goldsrc",
        code=code,
        game=game,
        map_name=map_name,
        xoffset=round(native_width / 2 * scale - origin_x) if rotated else round(origin_x + native_height / 2 * scale),
        yoffset=round(native_height / 2 * scale + origin_y) if rotated else round(-origin_y - native_width / 2 * scale),
        scale=scale,
        flipx=not rotated,
        flipy=rotated,
        rotate=0 if rotated else 1,
        image=values.get("IMAGE"),
        height=int(float(values["HEIGHT"])) if "HEIGHT" in values else None,
        manual_required=False,
    )


def parse_source_overview(
    content: str,
    *,
    code: str,
    game: str,
    map_name: str,
) -> ImportedOverview:
    """Parse a Source/CSGO ``resource/overviews/<map>.txt`` file."""

    values = {match.group("key").lower(): match.group("value") for match in _SOURCE_OVERVIEW_PAIR.finditer(content)}
    missing = {"pos_x", "pos_y", "scale"} - set(values)
    if missing:
        raise ValueError(f"Source overview missing required keys: {', '.join(sorted(missing))}")

    return ImportedOverview(
        projection="source",
        code=code,
        game=game,
        map_name=map_name,
        xoffset=round(-float(values["pos_x"])),
        yoffset=round(float(values["pos_y"])),
        scale=normalize_scale(values["scale"]),
        flipx=False,
        flipy=True,
        # Source rotate controls panel presentation, not the raw overview texture.
        rotate=0,
        material=values.get("material"),
        manual_required=False,
    )


def build_points_query(
    config: HeatmapConfig,
    *,
    ignore_infected: bool,
    kill_limit: int,
    start_timestamp: int | None,
) -> tuple[str, tuple[Any, ...]]:
    """Build the legacy frag + teamkill union query for one map."""

    timescope = int(time.time()) - (60 * 60 * 24 * config.days)
    comparator = ">" if start_timestamp is not None else ">="
    boundary = start_timestamp if start_timestamp is not None else timescope
    ignore_clause = 'AND hef.victimRole != "infected"\n' if ignore_infected else ""
    query = f"""
        (
            SELECT
                "frag" AS killtype,
                hef.id,
                hef.map,
                hs.game,
                hef.eventTime,
                hef.pos_x,
                hef.pos_y
            FROM
                hlstats_Events_Frags AS hef,
                hlstats_Servers AS hs
            WHERE 1=1
            AND hef.map = %s
            AND hs.serverId = hef.serverId
            AND hs.game = %s
            AND hef.pos_x IS NOT NULL
            AND hef.pos_y IS NOT NULL
            AND hef.eventTime {comparator} FROM_UNIXTIME(%s)
            {ignore_clause}LIMIT {kill_limit}
        )

        UNION ALL

        (
            SELECT
                "teamkill" AS killtype,
                hef.id,
                hef.map,
                hs.game,
                hef.eventTime,
                hef.pos_x,
                hef.pos_y
            FROM
                hlstats_Events_Teamkills AS hef,
                hlstats_Servers AS hs
            WHERE 1=1
            AND hef.map = %s
            AND hs.serverId = hef.serverId
            AND hs.game = %s
            AND hef.pos_x IS NOT NULL
            AND hef.pos_y IS NOT NULL
            AND hef.eventTime {comparator} FROM_UNIXTIME(%s)
            LIMIT {kill_limit}
        )
    """
    params = (config.map_name, config.code, boundary, config.map_name, config.code, boundary)
    return query, params


def resolve_cache_entry(
    cache_dir: Path,
    map_name: str,
    *,
    disable_cache: bool,
    now: float,
    logger: HeatmapLogger,
) -> CacheEntry | None:
    """Return the reusable cache entry for *map_name* if one is still valid."""

    if not cache_dir.exists():
        return None

    entries: list[CacheEntry] = []
    for candidate in cache_dir.iterdir():
        match = _CACHE_PATTERN.match(candidate.name)
        if not candidate.is_file() or match is None:
            continue
        if match.group("map") != map_name:
            continue
        entries.append(CacheEntry(path=candidate, timestamp=int(match.group("timestamp"))))

    if not entries:
        return None

    latest = max(entries, key=lambda item: item.timestamp)
    age_days = int((now - latest.timestamp) // 86400)
    if disable_cache:
        logger.event("ARGS", "--disable-cache=true", 2)
        latest.path.unlink(missing_ok=True)
        return None
    if age_days > LEGACY_CACHE_MAX_AGE_DAYS:
        logger.event(
            "CACHE",
            f"Cache file is obsolite, {age_days} days old. Generating from scratch",
            1,
        )
        latest.path.unlink(missing_ok=True)
        return None

    logger.event(
        "CACHE",
        f"Found cached file ({latest.path.name}), reusing timestamp {latest.timestamp}",
        1,
    )
    return latest


def load_overlay(size: tuple[int, int], cache_path: Path | None) -> Image.Image:
    """Load an existing cached overlay or create a transparent canvas."""

    if cache_path is not None and cache_path.exists():
        return Image.open(cache_path).convert("RGBA")
    return Image.new("RGBA", size, (0, 0, 0, 0))


def load_brush(assets_root: Path, brush_name: str) -> Image.Image:
    """Load the configured legacy brush PNG."""

    brush_path = assets_root / f"brush_{brush_name}.png"
    if not brush_path.exists():
        raise FileNotFoundError(brush_path)
    return Image.open(brush_path).convert("RGBA")


def compute_opacity(point_count: int, *, legacy_visuals: bool = False) -> int:
    """Return the per-dot opacity percentage."""

    safe_points = point_count or 1
    opacity = int((500 / safe_points) * 100)
    if opacity > 40:
        opacity = 40
    if opacity < 1:
        opacity = 2
    if legacy_visuals:
        return opacity
    if safe_points <= 5:
        return max(opacity, 85)
    if safe_points <= 25:
        return max(opacity, 65)
    return opacity


def prepare_brush_for_visibility(
    brush: Image.Image,
    point_count: int,
    *,
    legacy_visuals: bool = False,
) -> Image.Image:
    """Increase sparse-map dot radius while retaining legacy mode."""

    if legacy_visuals or point_count > 5 or min(brush.size) >= 33:
        return brush
    return brush.resize((33, 33), Image.Resampling.LANCZOS)


def apply_brush_opacity(brush: Image.Image, opacity_percent: int) -> Image.Image:
    """Scale the legacy brush alpha channel like ``printHeatDot``."""

    brush = brush.copy()
    pixels = brush.load()
    width, height = brush.size
    min_alpha = 255
    for x in range(width):
        for y in range(height):
            alpha = pixels[x, y][3]
            if alpha < min_alpha:
                min_alpha = alpha

    opacity_ratio = opacity_percent / 100.0
    min_gd_alpha = round((255 - min_alpha) * 127 / 255)
    for x in range(width):
        for y in range(height):
            red, green, blue, alpha = pixels[x, y]
            gd_alpha = round((255 - alpha) * 127 / 255)
            if min_gd_alpha != 127:
                new_gd_alpha = 127 + 127 * opacity_ratio * (gd_alpha - 127) / (127 - min_gd_alpha)
            else:
                new_gd_alpha = gd_alpha + 127 * opacity_ratio
            new_gd_alpha = max(0, min(127, int(round(new_gd_alpha))))
            new_alpha = int(round((127 - new_gd_alpha) * 255 / 127))
            pixels[x, y] = (red, green, blue, new_alpha)
    return brush


def draw_brush_point(
    overlay: Image.Image,
    brush: Image.Image,
    point: HeatmapPoint,
    config: HeatmapConfig,
) -> None:
    """Apply one transformed kill position to the overlay."""

    x, y = transform_point(point, config, apply_crop=False)

    if x < 0 or y < 0 or x >= overlay.width or y >= overlay.height:
        return

    red = overlay.getpixel((x, y))[0]
    if red > 200:
        return

    destination = (int(x - (brush.width / 2)), int(y - (brush.height / 2)))
    overlay.paste(brush, destination, brush)


def transform_point(
    point: HeatmapPoint,
    config: HeatmapConfig,
    *,
    apply_crop: bool = True,
) -> tuple[int, int]:
    """Transform a stored world coordinate into final heatmap canvas pixels."""

    pos_x = -point.pos_x if config.flipx else point.pos_x
    pos_y = -point.pos_y if config.flipy else point.pos_y
    scale = normalize_scale(config.scale)
    x = int((pos_x + config.xoffset) / scale)
    y = int((pos_y + config.yoffset) / scale)
    x, y = rotate_point(x, y, config.rotate)
    if apply_crop and config.cropx2 > 0 and config.cropy2 > 0:
        x -= config.cropx1
        y -= config.cropy1
    return x, y


def collect_projection_stats(
    points: Sequence[HeatmapPoint],
    config: HeatmapConfig,
    *,
    image_size: tuple[int, int],
    cache_status: str = "none",
) -> ProjectionStats:
    """Summarize transformed coordinate coverage for diagnostics and tests."""

    transformed = [transform_point(point, config) for point in points]
    width, height = image_size
    in_bounds = sum(1 for x, y in transformed if 0 <= x < width and 0 <= y < height)
    queried = len(transformed)
    if transformed:
        xs = [point[0] for point in transformed]
        ys = [point[1] for point in transformed]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        raw_xs = [point.pos_x for point in points]
        raw_ys = [point.pos_y for point in points]
        raw_min_x = min(raw_xs)
        raw_max_x = max(raw_xs)
        raw_min_y = min(raw_ys)
        raw_max_y = max(raw_ys)
    else:
        min_x = max_x = min_y = max_y = None
        raw_min_x = raw_max_x = raw_min_y = raw_max_y = None
    return ProjectionStats(
        queried=queried,
        in_bounds=in_bounds,
        out_of_bounds=queried - in_bounds,
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        cache_status=cache_status,
        raw_min_x=raw_min_x,
        raw_max_x=raw_max_x,
        raw_min_y=raw_min_y,
        raw_max_y=raw_max_y,
    )


def build_color_gradient() -> list[tuple[int, int, int]]:
    """Reproduce the legacy blue -> green -> red palette array."""

    gradient: list[tuple[int, int, int]] = [(0, 0, 255)] * 256
    colors = [0, 0, 255]
    for line in range(128):
        colors = [0, colors[1] + 2, colors[2] - 2]
        gradient[line] = (colors[0], colors[1], colors[2])
    for line in range(128, 255):
        colors = [colors[0] + 2, colors[1] - 2, 0]
        gradient[line] = (colors[0], colors[1], colors[2])
    gradient[255] = gradient[254]
    return gradient


def compose_heatmap(base_image: Image.Image, overlay: Image.Image) -> Image.Image:
    """Colorize the overlay and alpha-composite it onto the map JPEG."""

    gradient = build_color_gradient()
    heat = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    overlay_pixels = overlay.load()
    heat_pixels = heat.load()
    for x in range(overlay.width):
        for y in range(overlay.height):
            red = overlay_pixels[x, y][0]
            if red <= 0:
                continue
            color = gradient[min(255, red)]
            heat_pixels[x, y] = (color[0], color[1], color[2], min(255, red))
    return Image.alpha_composite(base_image, heat)


def crop_image(image: Image.Image, config: HeatmapConfig) -> Image.Image:
    """Apply the legacy crop rectangle if it is configured."""

    config = normalize_crop(config, image.size)
    if config.cropx2 <= 0 or config.cropy2 <= 0:
        return image
    return image.crop(
        (
            config.cropx1,
            config.cropy1,
            config.cropx1 + config.cropx2,
            config.cropy1 + config.cropy2,
        )
    )


def write_thumbnail(
    image: Image.Image,
    config: HeatmapConfig,
    output_dir: Path,
    map_name: str,
) -> None:
    """Write the legacy ``*-kill-thumb.jpg`` derivative when enabled."""

    if config.thumbw <= 0 or config.thumbh <= 0:
        return
    width = max(1, int(image.width * config.thumbw))
    height = max(1, int(image.height * config.thumbh))
    thumb = image.resize((width, height), Image.Resampling.LANCZOS)
    thumb.convert("RGB").save(output_dir / f"{map_name}-kill-thumb.jpg", format="JPEG", quality=100)


def resize_image(image: Image.Image, output_size: str, logger: HeatmapLogger) -> Image.Image:
    """Resize the generated image according to the legacy size preset."""

    target = LEGACY_OUTPUT_SIZES[output_size]
    if target is None:
        return image
    logger.event("RESIZE", f"Adjusting Heatmap to current setting: {output_size}", 2)
    resized = image.resize(target, Image.Resampling.NEAREST)
    logger.event("RESIZE", "Done...", 2)
    return resized


def draw_hud(
    image: Image.Image,
    map_name: str,
    config: HeatmapConfig,
    *,
    hud_url: str,
    font_path: Path,
    now: float,
) -> Image.Image:
    """Render the semi-transparent legacy HUD strip on top of the output image."""

    image = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    font = load_font(font_path, config.font)
    start_date = time.strftime(
        "%m/%d/%y",
        time.localtime(now - 60 * 60 * 24 * config.days),
    )
    end_date = time.strftime("%m/%d/%y", time.localtime(now))
    hud_text = [
        f"{map_name.upper()} - HLX:CE HEATMAP - TOTAL KILLS",
        f"LEGACY ROLLING SNAPSHOT ({config.days} DAYS): {start_date} - {end_date}",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}",
        hud_url,
    ]
    hud_height = int((config.font + 4) * (len(hud_text) + 1) + 8)
    draw.rectangle((0, 0, image.width - 1, hud_height), fill=(0, 0, 0, 74))

    for index, text in enumerate(hud_text, start=1):
        y = int((config.font + 4) * index + 8)
        draw.text((10, y), text, font=font, fill=(255, 255, 255, 255))
    return image


def load_font(font_path: Path, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load the configured font or fall back to Pillow's built-in one."""

    try:
        return ImageFont.truetype(str(font_path), size=max(1, size))
    except OSError:
        return ImageFont.load_default()


def build_generator(settings: HeatmapSettings) -> HeatmapGenerator:
    """Construct the concrete generator wired to the shared MySQL adapter."""

    database = SyncDatabaseAdapter(database_config_from_proxy_config(settings.config))
    repository = HeatmapRepository(database)
    return HeatmapGenerator(settings, repository)


def build_projection_diagnoser(settings: HeatmapSettings) -> HeatmapProjectionDiagnoser:
    """Construct the DB-first projection diagnostic runner."""

    database = SyncDatabaseAdapter(database_config_from_proxy_config(settings.config))
    repository = HeatmapRepository(database)
    return HeatmapProjectionDiagnoser(settings, repository)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m hlstats_py.heatmaps``."""

    try:
        settings = load_settings(argv)
        if settings.cli.diagnose_projection:
            build_projection_diagnoser(settings).run()
        else:
            generator = build_generator(settings)
            generator.run()
    except (ConfigError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    raise SystemExit(main())
