from hlstats_py.runtime_decisions import (
    canonical_unique_id,
    is_transient_unique_id,
    should_ignore_bot,
    should_persist_player_identity,
    should_reward_team_player,
)


def test_should_reward_team_player_allows_reward_eligible_player() -> None:
    decision = should_reward_team_player(
        player_id=101,
        active_players=set(),
        reward_eligible_players={101},
    )

    assert decision.allowed
    assert decision.gate == "team_bonus_eligibility"
    assert decision.reason == "reward_eligible"


def test_should_reward_team_player_allows_active_roster_player_without_entry() -> None:
    decision = should_reward_team_player(
        player_id=101,
        active_players={101},
        reward_eligible_players=set(),
    )

    assert decision.allowed
    assert decision.gate == "team_bonus_eligibility"
    assert decision.reason == "active_roster"


def test_should_reward_team_player_rejects_connected_only_player() -> None:
    decision = should_reward_team_player(
        player_id=101,
        active_players=set(),
        reward_eligible_players={202},
    )

    assert not decision.allowed
    assert decision.gate == "eligible_gate_reject"
    assert decision.reason == "not_reward_eligible_or_active"


def test_should_ignore_bot_rejects_only_when_policy_does() -> None:
    rejected = should_ignore_bot(ignored_by_policy=True)
    allowed = should_ignore_bot(ignored_by_policy=False)

    assert not rejected.allowed
    assert rejected.gate == "ignore_bots_gate_reject"
    assert allowed.allowed
    assert allowed.gate == "ignore_bots"


def test_canonical_unique_id_matches_legacy_storage_form() -> None:
    assert canonical_unique_id("STEAM_3:0:247752695") == "0:247752695"
    assert canonical_unique_id("STEAM_0:1:45686725") == "1:45686725"
    assert canonical_unique_id("1:45686725") == "1:45686725"


def test_transient_unique_id_detection_matches_legacy_tokens() -> None:
    assert is_transient_unique_id("STEAM_ID_LAN")
    assert is_transient_unique_id("valve_id_pending")
    assert not is_transient_unique_id("1:45686725")
    assert not is_transient_unique_id(None)


def test_should_persist_player_identity_rejects_transient_or_empty_descriptors() -> None:
    transient = should_persist_player_identity(unique_id="STEAM_ID_LAN", name="Player")
    empty = should_persist_player_identity(unique_id=None, name=" ")
    stable_unique = should_persist_player_identity(unique_id="1:45686725", name="")
    stable_name = should_persist_player_identity(unique_id=None, name="Alice")

    assert not transient.allowed
    assert transient.gate == "identity_gate_reject"
    assert transient.reason == "transient_unique_id"
    assert not empty.allowed
    assert empty.reason == "empty_descriptor"
    assert stable_unique.allowed
    assert stable_unique.gate == "identity"
    assert stable_name.allowed
