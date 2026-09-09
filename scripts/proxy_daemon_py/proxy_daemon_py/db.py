"""Compatibility wrapper for shared HLstatsX database helpers."""

from hlx_core.db import *  # noqa: F403
from hlx_core.db import _UPSERT_DAEMON_STATE_QUERY as _UPSERT_DAEMON_STATE_QUERY
from hlx_core.db import DatabaseAdapter as DatabaseAdapter
from hlx_core.db import DatabaseConfig as DatabaseConfig
from hlx_core.db import DatabaseError as DatabaseError
from hlx_core.db import GameServer as GameServer
from hlx_core.db import ProxyDaemonState as ProxyDaemonState
from hlx_core.db import ProxyDaemonTarget as ProxyDaemonTarget
from hlx_core.db import StoredProxyDaemon as StoredProxyDaemon
from hlx_core.db import SupportsConnection as SupportsConnection
from hlx_core.db import SupportsCursor as SupportsCursor
from hlx_core.db import SyncDatabaseAdapter as SyncDatabaseAdapter
