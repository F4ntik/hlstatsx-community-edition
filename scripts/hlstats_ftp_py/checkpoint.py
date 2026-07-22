"""Durable MySQL checkpoint support for FTP log imports.

The FTP file marker is useful for compatibility, but it cannot be advanced in
the same transaction as game-log writes.  This module owns the database cursor
used by the FTP runner instead.  It deliberately does not retry a failed
commit: a network failure at ``COMMIT`` has an unknown outcome and the caller
must stop rather than create an unbounded duplicate-import loop.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Sequence

if TYPE_CHECKING:
    from hlstats_ftp_py.core import LogFileEntry


class SupportsCursor(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...

    def close(self) -> None: ...


class SupportsConnection(Protocol):
    def cursor(self) -> SupportsCursor: ...

    def autocommit(self, value: bool) -> Any: ...

    def commit(self) -> Any: ...

    def rollback(self) -> Any: ...


class SupportsAdapter(Protocol):
    def connection(self) -> SupportsConnection: ...


class CheckpointError(RuntimeError):
    """The durable FTP cursor cannot be used safely."""


class CheckpointSchemaError(CheckpointError):
    """The required checkpoint migration is absent or non-transactional."""


class CheckpointLockError(CheckpointError):
    """Another FTP importer already owns this source cursor."""


class CheckpointCommitUncertainError(CheckpointError):
    """MySQL did not acknowledge COMMIT; its outcome must be treated as unknown."""


@dataclass(frozen=True, slots=True)
class FtpCheckpoint:
    """The last committed remote log cursor.

    ``name=None`` represents a bootstrapped legacy ``.last`` marker.  Such a
    cursor deliberately retains the legacy strict-mtime selection rule so that
    enabling durable checkpoints cannot silently reimport same-mtime files.
    """

    mtime_us: int
    name: str | None


def mtime_to_us(mtime: float) -> int:
    """Normalize FTP timestamps for stable MySQL cursor comparisons."""

    return int(round(float(mtime) * 1_000_000))


def checkpoint_identity(
    *,
    game_server_ip: str,
    game_server_port: int,
    ftp_host: str,
    ftp_port: int,
    ftp_dir: str,
) -> str:
    """Return a stable, non-secret identity for one configured FTP source."""

    source = {
        "version": 1,
        "game_server": f"{game_server_ip.strip().lower()}:{int(game_server_port)}",
        "ftp_host": ftp_host.strip().lower(),
        "ftp_port": int(ftp_port),
        "ftp_dir": ftp_dir.strip(),
    }
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DurableFtpCheckpoint:
    """Own a database-backed FTP cursor on the importer's one DB connection."""

    _CHECKPOINT_TABLE = "hlstats_FTP_Checkpoints"
    # Every table EventStorage can mutate while FTP parses a log or performs
    # its finite-import tail flush.  Keep this explicit rather than treating
    # unrelated legacy read tables as a migration blocker.
    _MUTATED_TABLES = (
        "hlstats_Actions",
        "hlstats_Events_Admin",
        "hlstats_Events_ChangeTeam",
        "hlstats_Events_Chat",
        "hlstats_Events_Connects",
        "hlstats_Events_Disconnects",
        "hlstats_Events_Entries",
        "hlstats_Events_Frags",
        "hlstats_Events_PlayerActions",
        "hlstats_Events_PlayerPlayerActions",
        "hlstats_Events_Statsme",
        "hlstats_Events_Statsme2",
        "hlstats_Events_Suicides",
        "hlstats_Events_TeamBonuses",
        "hlstats_Events_Teamkills",
        "hlstats_Maps_Counts",
        "hlstats_PlayerNames",
        "hlstats_Players",
        "hlstats_Players_History",
        "hlstats_PlayerUniqueIds",
        "hlstats_Servers",
        "hlstats_Weapons",
    )

    def __init__(self, adapter: SupportsAdapter, *, source_key: str) -> None:
        self._adapter = adapter
        self._source_key = source_key
        self._lock_name = f"hlstats-ftp:{source_key}"
        self._lock_held = False
        self._transaction_active = False
        self._active_connection: SupportsConnection | None = None

    @property
    def transaction_active(self) -> bool:
        return self._transaction_active

    def acquire_lock(self) -> None:
        """Prevent concurrent runners from observing the same cursor."""

        row = self._fetchone("SELECT GET_LOCK(%s, 0)", (self._lock_name,))
        if not row or int(row[0] or 0) != 1:
            raise CheckpointLockError("another hlstats FTP importer owns this source checkpoint")
        self._lock_held = True

    def release_lock(self) -> None:
        if not self._lock_held:
            return
        try:
            self._fetchone("SELECT RELEASE_LOCK(%s)", (self._lock_name,))
        except Exception:
            # Closing the MySQL connection releases the advisory lock.  Do not
            # mask the original import error during teardown.
            pass
        finally:
            self._lock_held = False

    def verify_schema(self) -> None:
        """Require the P1 migration and transactional importer write tables.

        A mixed-engine write path cannot atomically advance the cursor with
        game state.  Default durable mode therefore refuses it before FTP work
        starts; operators who retain the old marker must opt in explicitly to
        ``--legacy-file-marker``.
        """

        row = self._fetchone(
            "SELECT ENGINE FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (self._CHECKPOINT_TABLE,),
        )
        if not row:
            raise CheckpointSchemaError(
                "missing hlstats_FTP_Checkpoints; apply sql/migrations/2026_07_22_ftp_checkpoint.sql"
            )
        engine = "" if row[0] is None else str(row[0]).strip().lower()
        if engine != "innodb":
            raise CheckpointSchemaError(
                "hlstats_FTP_Checkpoints must use InnoDB for transactional checkpointing"
            )
        placeholders = ", ".join("%s" for _ in self._MUTATED_TABLES)
        rows = self._fetchall(
            "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ({placeholders}) "
            "ORDER BY TABLE_NAME",
            self._MUTATED_TABLES,
        )
        engines = {str(row[0]): "" if row[1] is None else str(row[1]).strip().lower() for row in rows}
        missing = [table for table in self._MUTATED_TABLES if table not in engines]
        non_transactional = [
            table for table in self._MUTATED_TABLES if table in engines and engines[table] != "innodb"
        ]
        if missing or non_transactional:
            problems = [f"missing={','.join(missing)}"] if missing else []
            if non_transactional:
                problems.append(f"non_innodb={','.join(non_transactional)}")
            raise CheckpointSchemaError(
                "durable FTP mode requires InnoDB for every importer write table ("
                + "; ".join(problems)
                + "); migrate the schema or use explicit --legacy-file-marker (non-atomic)"
            )

    def load(self) -> FtpCheckpoint | None:
        row = self._fetchone(
            "SELECT checkpoint_mtime_us, checkpoint_name "
            "FROM hlstats_FTP_Checkpoints WHERE source_key = %s",
            (self._source_key,),
        )
        if not row:
            return None
        return FtpCheckpoint(mtime_us=int(row[0]), name=None if row[1] is None else str(row[1]))

    def bootstrap_legacy_marker(self, legacy_mtime: float) -> FtpCheckpoint:
        """Persist an existing file marker once, preserving its strict-mtime rule."""

        checkpoint = FtpCheckpoint(mtime_us=mtime_to_us(legacy_mtime), name=None)
        self._execute(
            "INSERT INTO hlstats_FTP_Checkpoints "
            "(source_key, checkpoint_mtime_us, checkpoint_name) VALUES (%s, %s, NULL) "
            "ON DUPLICATE KEY UPDATE source_key = source_key",
            (self._source_key, checkpoint.mtime_us),
        )
        return checkpoint

    def begin(self) -> None:
        if self._transaction_active:
            raise CheckpointError("FTP checkpoint transaction already active")
        try:
            connection = self._connection()
            # SyncDatabaseAdapter otherwise pings/reconnects opportunistically.
            # Reconnecting in the middle of a transaction would detach the
            # cursor from already-written game state, so a lost connection must
            # fail a write/commit instead of silently continuing on a new one.
            self._set_skip_adapter_ping(True)
            connection.autocommit(False)
        except Exception as exc:
            self._set_skip_adapter_ping(False)
            raise CheckpointError("cannot begin FTP checkpoint transaction") from exc
        self._active_connection = connection
        self._transaction_active = True

    def advance(self, entry: "LogFileEntry") -> None:
        if not self._transaction_active:
            raise CheckpointError("FTP checkpoint advance requires an active transaction")
        self._execute(
            "INSERT INTO hlstats_FTP_Checkpoints "
            "(source_key, checkpoint_mtime_us, checkpoint_name) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE checkpoint_mtime_us = VALUES(checkpoint_mtime_us), "
            "checkpoint_name = VALUES(checkpoint_name), updated_at = CURRENT_TIMESTAMP",
            (self._source_key, mtime_to_us(entry.mtime), entry.name),
        )

    def commit(self) -> None:
        if not self._transaction_active:
            raise CheckpointError("FTP checkpoint commit requires an active transaction")
        try:
            self._connection().commit()
        except Exception as exc:
            with contextlib.suppress(Exception):
                self._connection().rollback()
            raise CheckpointCommitUncertainError(
                "MySQL did not acknowledge FTP import COMMIT; transaction outcome is unknown"
            ) from exc
        finally:
            self._transaction_active = False
            with contextlib.suppress(Exception):
                self._connection().autocommit(True)
            self._active_connection = None
            self._set_skip_adapter_ping(False)

    def rollback(self) -> None:
        if not self._transaction_active:
            return
        try:
            self._connection().rollback()
        finally:
            self._transaction_active = False
            with contextlib.suppress(Exception):
                self._connection().autocommit(True)
            self._active_connection = None
            self._set_skip_adapter_ping(False)

    def _connection(self) -> SupportsConnection:
        return self._active_connection or self._adapter.connection()

    def _set_skip_adapter_ping(self, enabled: bool) -> None:
        setter = getattr(self._adapter, "set_skip_connection_ping", None)
        if callable(setter):
            setter(enabled)

    def _fetchone(self, query: str, params: Sequence[Any] | None = None) -> Any:
        cursor = self._connection().cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _fetchall(self, query: str, params: Sequence[Any] | None = None) -> Sequence[Any]:
        cursor = self._connection().cursor()
        try:
            cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def _execute(self, query: str, params: Sequence[Any] | None = None) -> None:
        cursor = self._connection().cursor()
        try:
            cursor.execute(query, params)
        finally:
            cursor.close()
