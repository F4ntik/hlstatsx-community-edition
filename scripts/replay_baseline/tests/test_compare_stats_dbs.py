from scripts.replay_baseline.compare_stats_dbs import (
    AwardIdentity,
    NormalizationContext,
    PlayerIdentity,
    RibbonIdentity,
    canonicalize,
    normalize_award_row,
    normalize_chat_row,
    normalize_legacy_offline_chat_message,
    normalize_player_award_row,
    normalize_player_ribbon_row,
    normalize_player_row,
)


def _context() -> NormalizationContext:
    return NormalizationContext(
        players={
            140: PlayerIdentity(
                game="cstrike",
                name="Lin Kuei",
                unique_ids=("STEAM_0:0:36417680",),
            ),
            240: PlayerIdentity(
                game="cstrike",
                name="Murkowski",
                unique_ids=("STEAM_0:1:2084898310",),
            ),
        },
        actions={},
        servers={
            1: {
                "address": "172.19.0.1",
                "port": 27015,
                "endpoint": "172.19.0.1:27015",
                "name": "Pikabu",
                "game": "cstrike",
            }
        },
        awards={
            10: AwardIdentity(
                game="cstrike",
                award_type="W",
                code="ak47",
            )
        },
        ribbons={
            22: RibbonIdentity(
                game="cstrike",
                award_code="ak47",
                award_count=25,
                special=0,
            )
        },
    )


def test_normalize_legacy_offline_chat_message_keeps_ascii_text() -> None:
    assert normalize_legacy_offline_chat_message("Hold position!") == "Hold position!"


def test_normalize_legacy_offline_chat_message_masks_non_ascii_text() -> None:
    source = "дизморалити!"

    normalized = normalize_legacy_offline_chat_message(source)

    assert normalized == ("?" * len("дизморалити")) + "!"


def test_normalize_chat_row_masks_unicode_payload_for_parity() -> None:
    row = {
        "eventTime": "2026-04-17 19:11:37",
        "serverId": "1",
        "map": "de_dust2",
        "playerId": "140",
        "message_mode": "1",
        "message": "дизморалити!",
    }

    normalized = normalize_chat_row(row, _context())

    assert normalized["message"] == ("?" * len("дизморалити")) + "!"
    assert normalized["message_mode"] == 1
    assert normalized["map"] == "de_dust2"


def test_maintenance_normalizers_use_stable_award_ribbon_and_player_identities() -> None:
    context = _context()

    award = normalize_award_row(
        {
            "awardId": "501",
            "awardType": "W",
            "game": "cstrike",
            "code": "ak47",
            "name": "AK Master",
            "verb": "AK kills",
            "d_winner_id": "140",
            "d_winner_count": "12",
            "g_winner_id": "240",
            "g_winner_count": "89",
        },
        context,
    )
    player_award = normalize_player_award_row(
        {
            "awardTime": "2026-07-22",
            "awardId": "10",
            "playerId": "140",
            "count": "12",
            "game": "cstrike",
        },
        context,
    )
    ribbon = normalize_player_ribbon_row(
        {"playerId": "140", "ribbonId": "22", "game": "cstrike"},
        context,
    )

    assert award["daily_winner"]["unique_ids"] == ["STEAM_0:0:36417680"]
    assert award["global_winner"]["unique_ids"] == ["STEAM_0:1:2084898310"]
    assert "awardId" not in player_award
    assert player_award["award"] == {
        "game": "cstrike",
        "award_type": "W",
        "code": "ak47",
    }
    assert "ribbonId" not in ribbon
    assert ribbon["ribbon"]["award_count"] == 25


def test_maintenance_normalizers_preserve_meaningful_winner_and_geoip_differences() -> None:
    context = _context()
    base_award = {
        "awardId": "501",
        "awardType": "W",
        "game": "cstrike",
        "code": "ak47",
        "name": "AK Master",
        "verb": "AK kills",
        "d_winner_id": "140",
        "d_winner_count": "12",
        "g_winner_id": "240",
        "g_winner_count": "89",
    }
    changed_award = {**base_award, "d_winner_count": "13"}
    base_player = {
        "playerId": "140",
        "lastAddress": "8.8.8.8",
        "flag": "US",
        "country": "United States",
        "city": "Mountain View",
        "state": "California",
        "lat": "37.3860",
        "lng": "-122.0838",
    }
    changed_player = {**base_player, "city": "Los Angeles"}

    assert canonicalize(normalize_award_row(base_award, context)) != canonicalize(
        normalize_award_row(changed_award, context)
    )
    normalized_player = normalize_player_row(base_player, context)
    assert normalized_player["lat"] == 37.386
    assert normalized_player["lng"] == -122.0838
    assert canonicalize(normalized_player) != canonicalize(
        normalize_player_row(changed_player, context)
    )
