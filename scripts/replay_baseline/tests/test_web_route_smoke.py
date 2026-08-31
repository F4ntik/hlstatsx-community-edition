from __future__ import annotations

from pathlib import Path

from scripts.replay_baseline import web_route_smoke


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_heatmap_explorer_mount_contract_has_a_shared_strict_rollout_helper() -> None:
    """A wrong rollout branch must never emit both interactive mounts."""

    helper = (REPOSITORY_ROOT / "web/includes/heatmap_points.php").read_text(
        encoding="utf-8"
    )
    mapinfo = (REPOSITORY_ROOT / "web/pages/mapinfo.php").read_text(
        encoding="utf-8"
    )
    player = (
        REPOSITORY_ROOT / "web/pages/playerinfo_mapperformance.php"
    ).read_text(encoding="utf-8")

    assert "function heatmap_should_render_explorer" in helper
    assert "heatmap_explorer=1" in helper
    assert "heatmap_legacy=1" in helper
    assert "function heatmap_render_explorer_workspace" in helper
    assert "data-heatmap-interactive" in helper
    assert "data-heatmap-static" in helper
    assert "<noscript>" in helper
    assert "heatmap_should_render_explorer" in mapinfo
    assert "heatmap_should_render_explorer" in player


def test_heatmap_explorer_public_contract_keeps_i18n_controls_and_safe_shells_in_sync() -> None:
    """The two public mounts, dictionaries, and responsive shell stay one contract."""

    helper = (REPOSITORY_ROOT / "web/includes/heatmap_points.php").read_text(
        encoding="utf-8"
    )
    header = (REPOSITORY_ROOT / "web/pages/header.php").read_text(encoding="utf-8")
    mapinfo = (REPOSITORY_ROOT / "web/pages/mapinfo.php").read_text(
        encoding="utf-8"
    )
    player = (
        REPOSITORY_ROOT / "web/pages/playerinfo_mapperformance.php"
    ).read_text(encoding="utf-8")
    css = (REPOSITORY_ROOT / "web/hlstats.css").read_text(encoding="utf-8")
    explorer_js = (
        REPOSITORY_ROOT / "web/includes/js/heatmap-explorer.js"
    ).read_text(encoding="utf-8")
    options = (REPOSITORY_ROOT / "web/pages/admintasks/options.php").read_text(
        encoding="utf-8"
    )
    en = (REPOSITORY_ROOT / "web/lang/en.php").read_text(encoding="utf-8")
    ru = (REPOSITORY_ROOT / "web/lang/ru.php").read_text(encoding="utf-8")

    required_hooks = {
        "data-heatmap-interactive",
        "data-heatmap-stage",
        "data-heatmap-camera",
        "data-heatmap-image",
        "data-heatmap-canvas",
        "data-heatmap-static",
        "data-heatmap-status",
    }
    for hook in required_hooks:
        assert hook in helper
    assert "data-heatmap-lang" in helper
    assert "data-heatmap-sheet-toggle" in helper
    assert "data-heatmap-range" in helper
    assert "data-heatmap-floor-options" in helper
    assert "'lang' => current_lang()" in mapinfo
    assert "'lang' => current_lang()" in player
    assert header.index("/js/heatmap.js") < header.index("/js/heatmap-explorer.js")
    assert "'heatmapExplorer' => array(" in header

    en_keys = {
        line.split("' =>", 1)[0].strip().strip("'")
        for line in en.splitlines()
        if line.strip().startswith("'heatmapExplorer.")
    }
    ru_keys = {
        line.split("' =>", 1)[0].strip().strip("'")
        for line in ru.splitlines()
        if line.strip().startswith("'heatmapExplorer.")
    }
    assert en_keys == ru_keys
    assert {
        "heatmapExplorer.loading",
        "heatmapExplorer.failed",
        "heatmapExplorer.differenceBothCorrected",
        "heatmapExplorer.noscript",
        "heatmapExplorer.staticJpeg",
        "heatmapExplorer.navigation",
    } <= en_keys
    assert "HeatmapExplorerBeta" in options
    assert "choice.heatmap_explorer.off" in options
    assert "choice.heatmap_explorer.opt_in" in options
    assert "choice.heatmap_explorer.default" in options
    for token in (
        "--hm-bg:#0d1117",
        "--hm-panel:#151b24",
        "--hm-panel-raised:#1b2430",
        "--hm-border:#2a3544",
        "--hm-text:#eef3f8",
        "--hm-muted:#9eabb8",
        "--hm-kill:#ff9f2f",
        "--hm-death:#35c6e8",
        "--hm-focus:#f5c451",
        "grid-template-columns: 220px minmax(0, 1fr) 300px",
        "min-height: 620px",
        "@media (max-width: 900px)",
        ".heatmap-explorer__floors.is-open",
        ".heatmap-explorer__inspector.is-open",
        "@media (max-width: 540px)",
        "min-height: 44px",
        ":focus-visible",
        "prefers-reduced-motion: reduce",
    ):
        assert token in css
    assert "HeatmapExplorerWorkspace" in explorer_js
    assert "sceneUrl" in explorer_js
    assert "_renderFloors" in explorer_js
    assert "DOMContentLoaded" in explorer_js
    assert "data-heatmap-alert" in explorer_js
    assert "pointermove" in explorer_js
    assert "invalid_heatmap_url_state" in explorer_js
    assert "innerHTML" not in explorer_js


def test_representative_routes_include_populated_cstrike_award_tabs() -> None:
    award_tabs = {
        params["tab"]
        for route, params in web_route_smoke.ROUTES
        if route == "hlstats.php" and params.get("mode") == "awards"
    }

    assert award_tabs == {"daily", "global", "ribbons"}
    assert all(
        params.get("game") == "cstrike"
        for route, params in web_route_smoke.ROUTES
        if route == "hlstats.php" and params.get("mode") == "awards"
    )


def test_build_url_preserves_award_route_contract_for_each_language() -> None:
    url = web_route_smoke.build_url(
        "http://127.0.0.1:8281/",
        "hlstats.php",
        {"mode": "awards", "game": "cstrike", "tab": "ribbons"},
        "ru",
    )

    assert url == (
        "http://127.0.0.1:8281/hlstats.php?mode=awards&game=cstrike&tab=ribbons&lang=ru"
    )


def test_signature_player_ids_map_to_languages_in_requested_order() -> None:
    assert web_route_smoke.map_signature_player_ids(
        ["en", "ru"], ["101", "202"]
    ) == {"en": "101", "ru": "202"}


def test_signature_player_id_mapping_rejects_missing_duplicate_and_invalid_ids() -> None:
    cases = (
        (["en", "ru"], None),
        (["en", "ru"], ["101"]),
        (["en", "ru"], ["101", "101"]),
        (["en", "ru"], ["101", "0"]),
        (["en", "en"], ["101", "202"]),
    )

    for langs, player_ids in cases:
        try:
            web_route_smoke.map_signature_player_ids(langs, player_ids)
        except ValueError:
            continue
        raise AssertionError(f"expected invalid signature mapping for {langs!r}, {player_ids!r}")


def test_main_smokes_each_language_with_its_mapped_signature_player_id(monkeypatch) -> None:
    signature_urls: list[str] = []
    monkeypatch.setattr(web_route_smoke, "assert_route", lambda *_: [])
    monkeypatch.setattr(
        web_route_smoke,
        "assert_signature_route",
        lambda url, _: signature_urls.append(url) or [],
    )

    assert web_route_smoke.main(
        [
            "--base-url",
            "http://127.0.0.1:8281",
            "--langs",
            "en",
            "ru",
            "--sig-player-id",
            "101",
            "--sig-player-id",
            "202",
        ]
    ) == 0

    assert signature_urls == [
        "http://127.0.0.1:8281/sig.php?player_id=101&lang=en",
        "http://127.0.0.1:8281/sig.php?player_id=202&lang=ru",
    ]
