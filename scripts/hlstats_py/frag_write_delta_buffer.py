"""In-memory merge for additive frag-related counter writes during stdin batch import."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

ExecuteFn = Callable[[str, tuple[object, ...]], None]


@dataclass
class FragWriteDeltaBuffer:
    """Accumulate weapon upserts and server/map frag counters; flush with merged SQL."""

    _weapon: dict[tuple[str, str], tuple[str, float, int, int]] = field(default_factory=dict)
    _server_frags: dict[int, tuple[int, int]] = field(default_factory=dict)
    _map_counts: dict[tuple[str, str], tuple[int, int]] = field(default_factory=dict)

    def clear(self) -> None:
        self._weapon.clear()
        self._server_frags.clear()
        self._map_counts.clear()

    def add_weapon(self, game: str, code: str, name: str, modifier: float, kills: int, headshots: int) -> None:
        key = (game, code)
        cur = self._weapon.get(key)
        if cur is None:
            self._weapon[key] = (name, float(modifier), int(kills), int(headshots))
            return
        _old_name, mod, k, h = cur
        self._weapon[key] = (name, mod, k + int(kills), h + int(headshots))

    def add_server_frag_totals(self, kills: int, headshots: int, server_id: int) -> None:
        bk, bh = self._server_frags.get(server_id, (0, 0))
        self._server_frags[server_id] = (bk + int(kills), bh + int(headshots))

    def add_map_counts(self, game: str, map_name: str, kills: int, headshots: int) -> None:
        key = (game, map_name)
        ck, ch = self._map_counts.get(key, (0, 0))
        self._map_counts[key] = (ck + int(kills), ch + int(headshots))

    def flush(
        self,
        *,
        upsert_weapon_query: str,
        update_server_frag_query: str,
        upsert_map_counts_query: str,
        execute: ExecuteFn,
    ) -> int:
        """Apply pending deltas via *execute*; return approximate statement count."""

        writes = 0
        for (game, code), (name, modifier, kills, headshots) in self._weapon.items():
            execute(upsert_weapon_query, (game, code, name, modifier, kills, headshots))
            writes += 1
        for server_id, (kills, headshots) in self._server_frags.items():
            execute(update_server_frag_query, (kills, headshots, server_id))
            writes += 1
        for (game, map_name), (kills, headshots) in self._map_counts.items():
            execute(upsert_map_counts_query, (game, map_name, kills, headshots))
            writes += 1
        self.clear()
        return writes
