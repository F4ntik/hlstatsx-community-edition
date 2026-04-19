from __future__ import annotations

from datetime import datetime
from pathlib import Path

from hlstats_py.heatmaps import (
    HeatmapConfig,
    HeatmapGenerator,
    HeatmapRepository,
    HeatmapSettings,
    load_settings,
    select_target_maps,
)
from PIL import Image


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
        rotate=False,
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

    rows_by_match = {
        "hlstats_Heatmap_Config": [
            (
                "cstrike",
                "cstrike",
                "de_dust2",
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
            ("frag", 1, "de_dust2", "cstrike", datetime(2026, 4, 19, 12, 0, 0), 0, 0)
        ],
    }
    adapter = FakeAdapter(rows_by_match)
    repository = HeatmapRepository(adapter)  # type: ignore[arg-type]
    generator = HeatmapGenerator(settings, repository, clock=lambda: 1_713_520_000.0)

    results = generator.run()

    output_file = (
        settings.web_root
        / "hlstatsimg"
        / "games"
        / "cstrike"
        / "heatmaps"
        / "de_dust2-kill.jpg"
    )
    thumb_file = output_file.with_name("de_dust2-kill-thumb.jpg")
    cache_file = settings.cache_root / "cstrike" / "de_dust2_1713520000.png"

    assert adapter.connected is True
    assert adapter.closed is True
    assert [result.generated for result in results] == [True]
    assert output_file.exists()
    assert thumb_file.exists()
    assert cache_file.exists()
    assert any("hlstats_Events_Frags" in query for query in adapter.executed)
