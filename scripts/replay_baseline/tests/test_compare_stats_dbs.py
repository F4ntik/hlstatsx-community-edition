from scripts.replay_baseline.compare_stats_dbs import (
    NormalizationContext,
    PlayerIdentity,
    normalize_chat_row,
    normalize_legacy_offline_chat_message,
)


def _context() -> NormalizationContext:
    return NormalizationContext(
        players={
            140: PlayerIdentity(
                game="cstrike",
                name="Lin Kuei",
                unique_ids=("STEAM_0:0:36417680",),
            )
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
