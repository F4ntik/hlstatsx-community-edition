"""Behavior decisions for runtime/storage parity gates."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import AbstractSet


_STEAM_PREFIX_RE = re.compile(r"^STEAM_\d+:", re.IGNORECASE)
_TRANSIENT_UNIQUE_IDS = {
    "UNKNOWN",
    "STEAM_ID_PENDING",
    "STEAM_ID_LAN",
    "VALVE_ID_PENDING",
    "VALVE_ID_LAN",
}


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


def canonical_unique_id(unique_id: str) -> str:
    """Return the legacy DB form for Steam-style unique ids."""

    return _STEAM_PREFIX_RE.sub("", unique_id.strip())


def is_transient_unique_id(unique_id: str | None) -> bool:
    """Return whether a unique id is a legacy transient identity token."""

    if not unique_id:
        return False
    return unique_id.strip().upper() in _TRANSIENT_UNIQUE_IDS


def should_persist_player_identity(*, unique_id: str | None, name: str) -> Decision:
    """Return whether a descriptor has enough stable identity to persist."""

    if is_transient_unique_id(unique_id):
        return Decision(False, "identity_gate_reject", "transient_unique_id")
    if not (unique_id or name.strip()):
        return Decision(False, "identity_gate_reject", "empty_descriptor")
    return Decision(True, "identity", "stable")
