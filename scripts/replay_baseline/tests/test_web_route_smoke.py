from __future__ import annotations

from pathlib import Path
import re

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
        "@media (max-width: 900px)",
        ".heatmap-explorer__floors.is-open",
        ".heatmap-explorer__inspector.is-open",
        "@media (max-width: 540px)",
        "min-height: 44px",
        ":focus-visible",
        "prefers-reduced-motion: reduce",
    ):
        assert token in css
    assert "min-height: 620px" not in css
    sized_stage = re.search(
        r'\.heatmap-explorer__stage\[data-heatmap-sized="1"\]\s*\{(?P<body>[^}]*)\}',
        css,
        re.S,
    )
    assert sized_stage is not None
    assert "min-height: 0;" in sized_stage.group("body")
    assert ".heatmap-explorer__stage:not([data-heatmap-sized=\"1\"])" in css
    assert "min-height: 360px" in css
    assert "min-height: 320px" in css
    assert "HeatmapExplorerWorkspace" in explorer_js
    assert "sceneUrl" in explorer_js
    assert "_renderFloors" in explorer_js
    assert "_syncStageAspect" in explorer_js
    assert "style.aspectRatio = size.width + ' / ' + size.height;" in explorer_js
    assert "workspaceSetAttribute(this._nodes.stage, 'data-heatmap-sized', '1');" in explorer_js
    assert "DOMContentLoaded" in explorer_js
    assert "data-heatmap-alert" in explorer_js
    assert "pointermove" in explorer_js
    assert "invalid_heatmap_url_state" in explorer_js
    assert "innerHTML" not in explorer_js


def test_heatmap_admin_mutation_boundary_is_fail_closed() -> None:
    """Admin writes stay behind the agreed session-bound request boundary."""

    admin = (REPOSITORY_ROOT / "web/heatmap_admin.php").read_text(encoding="utf-8")
    helper = (REPOSITORY_ROOT / "web/includes/heatmap_points.php").read_text(
        encoding="utf-8"
    )
    wizard = (REPOSITORY_ROOT / "web/pages/admintasks/heatmaps.php").read_text(
        encoding="utf-8"
    )
    client = (REPOSITORY_ROOT / "web/includes/js/heatmap.js").read_text(
        encoding="utf-8"
    )

    for token in (
        "heatmap_admin_session_csrf_token",
        "HTTP_X_HLX_CSRF",
        "hash_equals(",
        "HTTP_ORIGIN",
        "HTTP_REFERER",
        "REQUEST_METHOD",
        "array('save', 'upload')",
    ):
        assert token in admin
    assert "random_bytes(32)" in helper
    for token in (
        "heatmap_admin_config_hash",
        "hash_file('sha256'",
        "heatmap_admin_map_lock_path",
        "FOR UPDATE",
    ):
        assert token in helper
    assert "flock(" in admin
    assert "heatmap_clear_payload_cache" in admin
    assert "CONTENT_TYPE" in admin
    assert "application/json" in admin
    for token in (
        "data-heatmap-csrf",
        "data-heatmap-floor-rows",
        "data-heatmap-diagnostic-from",
        "data-heatmap-deployment-command",
    ):
        assert token in wizard
    assert "data-heatmap-admin-regenerate" not in wizard
    assert "'X-HLX-CSRF'" in client
    assert "heatmapSafeImageUrl" in client
    assert "innerHTML" not in client
    for forbidden in ("regenerate", "proc_open", "'detail' =>", "'command' =>"):
        assert forbidden not in admin


def test_heatmap_admin_preview_rejects_invalid_floor_before_scene_build() -> None:
    """An invalid admin floor id must fail closed as invalid_request before scene assembly."""

    helper = (REPOSITORY_ROOT / "web/includes/heatmap_points.php").read_text(
        encoding="utf-8"
    )
    admin = (REPOSITORY_ROOT / "web/heatmap_admin.php").read_text(encoding="utf-8")

    assert "function heatmap_floor_id_is_valid" in helper
    assert "heatmap_floor_id_is_valid($floor)" in admin
    preview_query = admin.index("function heatmap_admin_preview_query")
    floor_validation = admin.index("heatmap_floor_id_is_valid($floor)")
    build_scene = admin.index("heatmap_build_scene(")
    invalid_request = admin.index(
        "throw new HeatmapAdminException('invalid_request', 400);", floor_validation
    )

    assert preview_query < floor_validation < invalid_request < build_scene


def test_heatmap_admin_preview_preserves_domain_errors_before_preview_failed() -> None:
    """Preview should preserve HeatmapAdminException before the generic preview_failed catch."""

    admin = (REPOSITORY_ROOT / "web/heatmap_admin.php").read_text(encoding="utf-8")

    preview_payload = admin.index("function heatmap_admin_preview_payload")
    build_scene = admin.index("heatmap_build_scene(", preview_payload)
    passthrough_catch = admin.index(
        "catch (HeatmapAdminException $exception) {", build_scene
    )
    passthrough_throw = admin.index("throw $exception;", passthrough_catch)
    invalid_request = admin.index(
        "catch (InvalidArgumentException $exception) {", passthrough_throw
    )
    preview_failed = admin.index(
        "throw new HeatmapAdminException('preview_failed', 500);", invalid_request
    )

    assert (
        preview_payload
        < build_scene
        < passthrough_catch
        < passthrough_throw
        < invalid_request
        < preview_failed
    )


def test_heatmap_admin_transport_guard_rejects_oversize_post_before_session_boot() -> None:
    """The admin route must fail closed on oversized POST bodies before session/auth parsing."""

    admin = (REPOSITORY_ROOT / "web/heatmap_admin.php").read_text(encoding="utf-8")
    transport = (
        REPOSITORY_ROOT / "web/includes/heatmap_admin_transport.php"
    ).read_text(encoding="utf-8")
    app_limit_match = re.search(
        r"HEATMAP_ADMIN_MAX_IMAGE_BYTES\s*=\s*(\d+);", admin
    )
    transport_limit_match = re.search(
        r"HEATMAP_ADMIN_MAX_TRANSPORT_BYTES\s*=\s*(\d+);", transport
    )

    assert app_limit_match is not None
    assert transport_limit_match is not None
    app_limit = int(app_limit_match.group(1))
    transport_limit = int(transport_limit_match.group(1))

    assert app_limit == 20 * 1024 * 1024
    assert transport_limit == 21 * 1024 * 1024
    assert transport_limit > app_limit
    assert "function heatmap_admin_request_content_length(array $server): ?int" in transport
    assert "function heatmap_admin_request_exceeds_transport_limit(array $server): bool" in transport
    assert "function heatmap_admin_reject_oversize_post(array $server): bool" in transport
    assert "CONTENT_LENGTH" in transport
    assert "REQUEST_METHOD" in transport
    assert "'message' => 'The calibration request is invalid.'" in transport
    assert "'code' => 'invalid_request'" in transport
    assert "413" in transport

    require_transport = admin.index("require $includeRoot . '/heatmap_admin_transport.php';")
    guard = admin.index("if (heatmap_admin_reject_oversize_post($_SERVER)) {")
    guard_exit = admin.index("exit;", guard)
    session_boot = admin.index("session_start();", guard)
    access_boundary = admin.index("heatmap_admin_require_access();", guard)

    assert require_transport < guard < guard_exit < session_boot < access_boundary


def test_python_web_dockerfiles_pin_php_upload_limits_and_warning_visibility() -> None:
    """Local Python web images must keep the exact 21 MiB transport ceiling and suppress output leaks."""

    admin = (REPOSITORY_ROOT / "web/heatmap_admin.php").read_text(encoding="utf-8")
    app_limit_match = re.search(
        r"HEATMAP_ADMIN_MAX_IMAGE_BYTES\s*=\s*(\d+);", admin
    )
    assert app_limit_match is not None
    app_limit = int(app_limit_match.group(1))
    assert app_limit == 20 * 1024 * 1024

    for dockerfile in (
        REPOSITORY_ROOT / "scripts/replay_baseline/comparison/python/Dockerfile.web",
        REPOSITORY_ROOT / "scripts/proxy_daemon_py/fullstack/Dockerfile.web",
    ):
        source = dockerfile.read_text(encoding="utf-8")
        upload_match = re.search(r"upload_max_filesize=(\d+)M", source)
        post_match = re.search(r"post_max_size=(\d+)M", source)

        assert upload_match is not None, f"{dockerfile.name} should set upload_max_filesize"
        assert post_match is not None, f"{dockerfile.name} should set post_max_size"
        assert int(upload_match.group(1)) == 21
        assert int(post_match.group(1)) == 21
        assert int(upload_match.group(1)) * 1024 * 1024 > app_limit
        assert int(post_match.group(1)) * 1024 * 1024 > app_limit
        assert "display_errors=Off" in source
        assert "display_startup_errors=Off" in source
        assert "log_errors=On" in source


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
