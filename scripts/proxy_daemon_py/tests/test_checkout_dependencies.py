from __future__ import annotations

import inspect
from pathlib import Path

from proxy_daemon_py import db
from proxy_daemon_py.transport import ProxyUdpServer


def _source_path(value: object) -> Path:
    source = inspect.getsourcefile(value)
    assert source is not None
    return Path(source).resolve()


def test_proxy_suite_uses_checkout_shared_core() -> None:
    scripts_root = Path(__file__).resolve().parents[2]
    shared_core = scripts_root / "hlx_core"

    assert _source_path(db.SyncDatabaseAdapter) == shared_core / "db.py"
    assert _source_path(ProxyUdpServer) == shared_core / "transport.py"
