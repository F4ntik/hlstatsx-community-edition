from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from hlstats_py.heatmaps import (
    HeatmapConfig,
    HeatmapGenerator,
    HeatmapPoint,
    HeatmapRepository,
    HeatmapSettings,
    apply_brush_opacity,
    build_points_query,
    collect_projection_stats,
    crop_image,
    draw_hud,
    effective_image_size,
    load_settings,
    normalize_crop,
    normalize_scale,
    parse_goldsrc_overview,
    parse_source_overview,
    rotate_point,
    transform_point,
    unrotate_point,
    select_target_maps,
)
from PIL import Image, ImageChops


class FakeCursor:
    def __init__(
        self,
        rows_by_match: dict[str, list[tuple[object, ...]]],
        executed: list[str],
    ) -> None:
        self._rows_by_match = rows_by_match
        self._executed = executed
        self._rows: list[tuple[object, ...]] = []

    def execute(self, query: str, params=None) -> None:
        rendered = query if not params else f"{query} | {params!r}"
        self._executed.append(rendered)
        for marker, rows in self._rows_by_match.items():
            if marker in query:
                self._rows = rows
                return
        raise AssertionError(f"Unexpected query: {query}")

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def close(self) -> None:
        return None


class FakeConnection:
    def __init__(
        self,
        rows_by_match: dict[str, list[tuple[object, ...]]],
        executed: list[str],
    ) -> None:
        self._rows_by_match = rows_by_match
        self._executed = executed

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows_by_match, self._executed)


class FakeAdapter:
    def __init__(self, rows_by_match: dict[str, list[tuple[object, ...]]]) -> None:
        self.rows_by_match = rows_by_match
        self.executed: list[str] = []
        self.connected = False
        self.closed = False
        self._connection = FakeConnection(rows_by_match, self.executed)

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.closed = True

    def connection(self) -> FakeConnection:
        return self._connection


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "hlstats.conf"
    config_path.write_text(
        "\n".join(
            [
                "DBHost 127.0.0.1",
                "DBName hlstatsxce",
                "DBUsername hlstatsxce",
                "DBPassword hlx123",
                "BindIP 0.0.0.0",
                "Port 27500",
                "DebugLevel 0",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _make_settings(tmp_path: Path) -> HeatmapSettings:
    config_path = _write_config(tmp_path)
    heatmaps_root = tmp_path / "heatmaps"
    web_root = tmp_path / "web"
    return load_settings(
        [
            "--configfile",
            str(config_path),
            "--heatmaps-root",
            str(heatmaps_root),
            "--web-root",
            str(web_root),
            "--debug-level",
            "0",
        ]
    )


def _make_config() -> HeatmapConfig:
    return HeatmapConfig(
        code="cstrike",
        game="cstrike",
        map_name="de_dust2",
        xoffset=32,
        yoffset=32,
        flipx=False,
        flipy=False,
        rotate=0,
        days=30,
        brush="small",
        scale=1.0,
        font=10,
        thumbw=0.25,
        thumbh=0.25,
        cropx1=0,
        cropx2=0,
        cropy1=0,
        cropy2=0,
    )


def test_transform_point_supports_quarter_turn_rotations() -> None:
    point = HeatmapPoint(datetime(2026, 4, 19, 12, 0, 0), 10, 20)

    assert transform_point(point, _make_config()) == (42, 52)
    assert transform_point(point, replace(_make_config(), rotate=1, xoffset=0, yoffset=0)) == (-20, 10)
    assert transform_point(point, replace(_make_config(), rotate=2, xoffset=0, yoffset=0)) == (-10, -20)
    assert transform_point(point, replace(_make_config(), rotate=3, xoffset=0, yoffset=0)) == (20, -10)


def test_non_positive_scale_uses_safe_default() -> None:
    point = HeatmapPoint(datetime(2026, 4, 19, 12, 0, 0), 10, 20)
    assert normalize_scale(0) == 1.0
    assert normalize_scale(-2) == 1.0
    assert transform_point(point, replace(_make_config(), scale=0, xoffset=0, yoffset=0)) == (10, 20)


def test_rotation_round_trip_and_fourth_power() -> None:
    original = (17, -29)
    for steps in range(4):
        rotated = rotate_point(*original, steps)
        assert unrotate_point(*rotated, steps) == original
        after_four = rotated
        for _ in range(3):
            after_four = rotate_point(*after_four, steps)
        assert after_four == original


def test_crop_normalization_and_effective_canvas() -> None:
    config = replace(
        _make_config(),
        cropx1=90,
        cropy1=-5,
        cropx2=50,
        cropy2=100,
    )
    normalized = normalize_crop(config, (100, 80))
    assert (normalized.cropx1, normalized.cropy1, normalized.cropx2, normalized.cropy2) == (90, 0, 10, 80)
    assert effective_image_size(config, (100, 80)) == (10, 80)
    assert crop_image(Image.new("RGB", (100, 80)), config).size == (10, 80)


def test_projection_stats_use_cropped_canvas_coordinates() -> None:
    config = replace(_make_config(), xoffset=0, yoffset=0, cropx1=10, cropy1=20, cropx2=30, cropy2=40)
    points = [
        HeatmapPoint(datetime(2026, 4, 19, 12, 0, 0), 15, 25),
        HeatmapPoint(datetime(2026, 4, 19, 12, 1, 0), 50, 60),
    ]

    stats = collect_projection_stats(points, config, image_size=effective_image_size(config, (100, 100)))

    assert stats.in_bounds == 1
    assert stats.out_of_bounds == 1
    assert (stats.min_x, stats.max_x, stats.min_y, stats.max_y) == (5, 40, 5, 40)


def _make_rows(map_name: str) -> dict[str, list[tuple[object, ...]]]:
    return {
        "hlstats_Heatmap_Config": [
            (
                "cstrike",
                "cstrike",
                map_name,
                32,
                32,
                0,
                0,
                0,
                30,
                "small",
                1.0,
                10,
                0.25,
                0.25,
                0,
                0,
                0,
                0,
            )
        ],
        "WHERE hidden='0'": [("cstrike",)],
        "hlstats_Events_Frags": [
            ("frag", 1, map_name, "cstrike", datetime(2026, 4, 19, 12, 0, 0), 0, 0)
        ],
    }


def _assert_generated_outputs(
    settings: HeatmapSettings,
    map_name: str,
    results,
) -> None:
    output_file = (
        settings.web_root
        / "hlstatsimg"
        / "games"
        / "cstrike"
        / "heatmaps"
        / f"{map_name}-kill.jpg"
    )
    thumb_file = output_file.with_name(f"{map_name}-kill-thumb.jpg")
    cache_file = settings.cache_root / "cstrike" / f"{map_name}_1713520000.png"

    assert [result.generated for result in results] == [True]
    assert output_file.exists()
    assert thumb_file.exists()
    assert cache_file.exists()


def test_load_settings_resolves_legacy_default_paths(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)

    assert settings.web_root == (tmp_path / "web").resolve()
    assert settings.assets_root == (tmp_path / "heatmaps" / "src").resolve()
    assert settings.cache_root == (tmp_path / "heatmaps" / "cache").resolve()
    assert settings.hud_url == "http://www.hlxcommunity.com"
    assert settings.output_size == "medium"


def test_select_target_maps_uses_visible_games_when_no_filter() -> None:
    cfg = _make_config()
    selected = select_target_maps(
        {
            "cstrike": {"de_dust2": cfg},
            "hidden": {"de_train": cfg},
        },
        visible_games=["cstrike"],
        game=None,
        map_name=None,
    )

    assert list(selected) == ["cstrike"]
    assert list(selected["cstrike"]) == ["de_dust2"]


def test_build_points_query_wraps_limited_selects_for_mysql_union() -> None:
    query, params = build_points_query(
        _make_config(),
        ignore_infected=False,
        kill_limit=100,
        start_timestamp=None,
    )

    assert "(\n            SELECT" in query
    assert "\n        )\n\n        UNION ALL\n\n        (\n            SELECT" in query
    assert "LIMIT 100" in query
    assert params[0] == "de_dust2"
    assert params[3] == "de_dust2"


def test_apply_brush_opacity_handles_fully_opaque_pixels() -> None:
    brush = Image.new("RGBA", (2, 1))
    brush.putpixel((0, 0), (255, 255, 255, 0))
    brush.putpixel((1, 0), (255, 255, 255, 255))

    adjusted = apply_brush_opacity(brush, 50)

    assert adjusted.size == brush.size
    assert adjusted.getpixel((0, 0))[3] <= 255
    assert adjusted.getpixel((1, 0))[3] <= 255


def test_draw_hud_labels_the_configured_legacy_rolling_days(monkeypatch) -> None:
    captured: list[str] = []

    class FakeDraw:
        def rectangle(self, *args, **kwargs) -> None:
            return None

        def text(self, _position, text: str, **kwargs) -> None:
            captured.append(text)

    monkeypatch.setattr("hlstats_py.heatmaps.ImageDraw.Draw", lambda *args: FakeDraw())
    monkeypatch.setattr("hlstats_py.heatmaps.load_font", lambda *args: object())
    config = replace(_make_config(), days=7)

    draw_hud(
        Image.new("RGBA", (120, 80)),
        "de_dust2",
        config,
        hud_url="https://example.invalid",
        font_path=Path("missing.ttf"),
        now=1_735_732_800.0,
    )

    assert any("LEGACY ROLLING SNAPSHOT (7 DAYS)" in text for text in captured)
    assert any(
        text
        == "LEGACY ROLLING SNAPSHOT (7 DAYS): 12/25/24 - 01/01/25"
        for text in captured
    )


def test_heatmap_generator_writes_legacy_outputs_and_cache(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    asset_dir = settings.assets_root / "cstrike"
    asset_dir.mkdir(parents=True)
    settings.cache_root.mkdir(parents=True)
    settings.web_root.mkdir(parents=True)

    Image.new("RGB", (64, 64), (40, 40, 40)).save(asset_dir / "de_dust2.jpg", format="JPEG")
    Image.new("RGBA", (17, 17), (255, 255, 255, 255)).save(
        settings.assets_root / "brush_small.png",
        format="PNG",
    )

    rows_by_match = _make_rows("de_dust2")
    adapter = FakeAdapter(rows_by_match)
    repository = HeatmapRepository(adapter)  # type: ignore[arg-type]
    generator = HeatmapGenerator(settings, repository, clock=lambda: 1_713_520_000.0)

    results = generator.run()

    assert adapter.connected is True
    assert adapter.closed is True
    _assert_generated_outputs(settings, "de_dust2", results)
    assert any("hlstats_Events_Frags" in query for query in adapter.executed)


def test_heatmap_generator_writes_legacy_outputs_for_2x2_map_name(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    asset_dir = settings.assets_root / "cstrike"
    asset_dir.mkdir(parents=True)
    settings.cache_root.mkdir(parents=True)
    settings.web_root.mkdir(parents=True)

    Image.new("RGB", (64, 64), (40, 40, 40)).save(
        asset_dir / "de_dust2_2x2.jpg",
        format="JPEG",
    )
    Image.new("RGBA", (17, 17), (255, 255, 255, 255)).save(
        settings.assets_root / "brush_small.png",
        format="PNG",
    )

    rows_by_match = _make_rows("de_dust2_2x2")
    adapter = FakeAdapter(rows_by_match)
    repository = HeatmapRepository(adapter)  # type: ignore[arg-type]
    generator = HeatmapGenerator(settings, repository, clock=lambda: 1_713_520_000.0)

    results = generator.run()

    assert adapter.connected is True
    assert adapter.closed is True
    _assert_generated_outputs(settings, "de_dust2_2x2", results)
    assert any("hlstats_Events_Frags" in query for query in adapter.executed)


def test_collect_projection_stats_reports_in_bounds_and_out_of_bounds_points() -> None:
    config = _make_config()
    points = [
        HeatmapPoint(datetime(2026, 4, 19, 12, 0, 0), 0, 0),
        HeatmapPoint(datetime(2026, 4, 19, 12, 1, 0), 5000, 5000),
    ]

    stats = collect_projection_stats(points, config, image_size=(128, 128))

    assert stats.queried == 2
    assert stats.in_bounds == 1
    assert stats.out_of_bounds == 1
    assert stats.min_x == 32
    assert stats.max_x == 5032
    assert stats.min_y == 32
    assert stats.max_y == 5032


def test_collect_projection_stats_reports_raw_bounds_and_ratio() -> None:
    config = _make_config()
    points = [
        HeatmapPoint(datetime(2026, 4, 19, 12, 0, 0), -10, 40),
        HeatmapPoint(datetime(2026, 4, 19, 12, 1, 0), 5000, 6000),
    ]

    stats = collect_projection_stats(points, config, image_size=(128, 128))

    assert stats.raw_min_x == -10
    assert stats.raw_max_x == 5000
    assert stats.raw_min_y == 40
    assert stats.raw_max_y == 6000
    assert stats.in_bounds_ratio == 0.5


def test_parse_goldsrc_overview_requires_explicit_native_frame() -> None:
    import pytest
    with pytest.raises(ValueError, match="TXT alone"):
        parse_goldsrc_overview("ZOOM 1.5\nORIGIN 223 1097 0\nROTATED 0", code="cstrike", game="cstrike", map_name="de_dust2")


def test_parse_goldsrc_overview_matches_sdk_axes() -> None:
    import pytest
    for rotated in (0, 1):
        overview = parse_goldsrc_overview(
            f"ZOOM 1.5\nORIGIN 223 1097 0\nROTATED {rotated}",
            code="cstrike", game="cstrike", map_name="de_dust2",
            native_width=1024, native_height=768, registered_native_frame=True,
        )
        config = overview.to_legacy_config()
        assert config.scale == pytest.approx(16 / 3)
        for x, y in [(223, 1097), (0, 0), (-1700, 2500)]:
            point = HeatmapPoint(event_time=datetime(2026, 1, 1), pos_x=x, pos_y=y)
            actual = transform_point(point, config)
            expected = (512+(x-223)*.1875,384-(y-1097)*.1875) if rotated else (512-(y-1097)*.1875,384-(x-223)*.1875)
            assert abs(actual[0]-expected[0]) <= 1
            assert abs(actual[1]-expected[1]) <= 1


def test_parse_source_overview_converts_to_legacy_config() -> None:
    overview = parse_source_overview(
        """
        "de_dust2"
        {
            "material" "overviews/de_dust2"
            "pos_x" "-5290"
            "pos_y" "4259"
            "scale" "6.0"
            "rotate" "0"
        }
        """,
        code="css",
        game="css",
        map_name="de_dust2",
    )

    assert overview.projection == "source"
    assert overview.manual_required is False
    assert overview.to_legacy_config().xoffset == 5290
    assert overview.to_legacy_config().yoffset == 4259
    assert overview.to_legacy_config().scale == 6.0
    assert overview.to_legacy_config().flipy is True


def test_heatmap_generator_makes_sparse_points_visibly_readable(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    asset_dir = settings.assets_root / "cstrike"
    asset_dir.mkdir(parents=True)
    settings.cache_root.mkdir(parents=True)
    settings.web_root.mkdir(parents=True)

    source_file = asset_dir / "de_dust2.jpg"
    Image.new("RGB", (96, 96), (40, 40, 40)).save(source_file, format="JPEG")
    Image.new("RGBA", (17, 17), (255, 255, 255, 48)).save(
        settings.assets_root / "brush_small.png",
        format="PNG",
    )

    rows_by_match = _make_rows("de_dust2")
    adapter = FakeAdapter(rows_by_match)
    repository = HeatmapRepository(adapter)  # type: ignore[arg-type]
    generator = HeatmapGenerator(settings, repository, clock=lambda: 1_713_520_000.0)

    results = generator.run()

    output_file = results[0].output_file
    assert output_file is not None
    source = Image.open(source_file).convert("RGB").resize(Image.open(output_file).size)
    output = Image.open(output_file).convert("RGB")
    diff = ImageChops.difference(source, output)
    heat_pixels = [
        pixel
        for pixel in diff.crop((0, 96, diff.width, diff.height)).getdata()
        if max(pixel) >= 18
    ]
    assert len(heat_pixels) >= 600
    assert results[0].diagnostics is not None
    assert results[0].diagnostics.in_bounds == 1
