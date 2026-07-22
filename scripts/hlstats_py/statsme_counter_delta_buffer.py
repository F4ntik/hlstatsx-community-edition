"""In-memory merge for additive Statsme counters during stdin batch import."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ExecuteFn = Callable[[str, tuple[object, ...]], None]


@dataclass
class StatsmeCounterDeltaBuffer:
    """Accumulate player and server shots/hits without buffering event rows."""

    _player: dict[int, tuple[int, int]] = field(default_factory=dict)
    _server: dict[tuple[int, str], tuple[int, int, int, int]] = field(default_factory=dict)

    def clear(self) -> None:
        self._player.clear()
        self._server.clear()

    def add_player(self, player_id: int, shots: int, hits: int) -> None:
        old_shots, old_hits = self._player.get(player_id, (0, 0))
        self._player[player_id] = (old_shots + int(shots), old_hits + int(hits))

    def add_server(
        self,
        server_id: int,
        team: str,
        shots: int,
        hits: int,
        map_shots: int,
        map_hits: int,
    ) -> None:
        key = (server_id, team)
        old_shots, old_hits, old_map_shots, old_map_hits = self._server.get(key, (0, 0, 0, 0))
        self._server[key] = (
            old_shots + int(shots),
            old_hits + int(hits),
            old_map_shots + int(map_shots),
            old_map_hits + int(map_hits),
        )

    def flush(
        self,
        *,
        update_player_query: str,
        update_server_ct_query: str,
        update_server_ts_query: str,
        execute: ExecuteFn,
    ) -> int:
        writes = 0
        for player_id, (shots, hits) in sorted(self._player.items()):
            execute(update_player_query, (shots, hits, player_id))
            writes += 1
        for (server_id, team), (shots, hits, map_shots, map_hits) in sorted(self._server.items()):
            query = update_server_ct_query if team == "CT" else update_server_ts_query
            execute(query, (shots, hits, map_shots, map_hits, server_id))
            writes += 1
        self.clear()
        return writes
