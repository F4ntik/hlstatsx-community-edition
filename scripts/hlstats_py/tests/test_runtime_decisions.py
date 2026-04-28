from hlstats_py.runtime_decisions import should_ignore_bot, should_reward_team_player


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
