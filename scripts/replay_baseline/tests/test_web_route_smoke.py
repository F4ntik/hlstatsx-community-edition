from __future__ import annotations

from scripts.replay_baseline import web_route_smoke


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
