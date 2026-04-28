"""Behavior decisions for runtime/storage parity gates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet


@dataclass(frozen=True, slots=True)
class Decision:
    """Structured allow/reject result for a parity-sensitive gate."""

    allowed: bool
    gate: str
    reason: str


def should_reward_team_player(
    *,
    player_id: int,
    active_players: AbstractSet[int],
    reward_eligible_players: AbstractSet[int],
) -> Decision:
    """Return whether a player is in the legacy-style TeamBonuses roster."""

    if player_id in reward_eligible_players:
        return Decision(True, "team_bonus_eligibility", "reward_eligible")
    if player_id in active_players:
        return Decision(True, "team_bonus_eligibility", "active_roster")
    return Decision(False, "eligible_gate_reject", "not_reward_eligible_or_active")


def should_ignore_bot(*, ignored_by_policy: bool) -> Decision:
    """Return whether the storage adapter's IgnoreBots policy rejects an actor."""

    if ignored_by_policy:
        return Decision(False, "ignore_bots_gate_reject", "ignore_bots_bot")
    return Decision(True, "ignore_bots", "allowed")
