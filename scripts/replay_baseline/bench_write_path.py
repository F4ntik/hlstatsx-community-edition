#!/usr/bin/env python3
"""
Micro-benchmark for hlstats_py write path (stdin batch + buffers).

- ``--mode fake``: in-process FakeConnection (no MySQL, no Docker).
- ``--mode subprocess``: pipe synthetic **lines** to ``python -m hlstats_py.runtime --stdin`` (not multi-file).

For benchmarks over **many separate .log files**, use
``direct_import_artifacts.py --file-count N`` (see ``Run-LogFilesBenchEphemeral.ps1``).

For an isolated DB that does not touch the main Python comparison stack, see
``scripts/replay_baseline/bench_ephemeral/README.md`` and ``Run-WriteBenchEphemeral.ps1``.

Run from repo root with:
``PYTHONPATH=scripts;scripts/proxy_daemon_py`` (Windows: semicolon separator).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Dict, List

_SCRIPT_DIR = Path(__file__).resolve().parent
# bench_write_path.py lives in .../scripts/replay_baseline/
_SCRIPTS = _SCRIPT_DIR.parent
_REPO_ROOT = _SCRIPTS.parent
if not (_SCRIPTS / "hlstats_py").is_dir():
    raise RuntimeError(f"Expected hlstats_py under {_SCRIPTS}")
if _SCRIPTS.is_dir() and str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_pp = _SCRIPTS / "proxy_daemon_py"
if _pp.is_dir() and str(_pp) not in sys.path:
    sys.path.insert(0, str(_pp))


def _load_test_storage_module():
    test_path = _SCRIPTS / "hlstats_py" / "tests" / "test_storage.py"
    name = "hlstats_test_storage_bench"
    spec = importlib.util.spec_from_file_location(name, test_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {test_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_chat_log_lines(count: int) -> bytes:
    lines = []
    for i in range(count):
        lines.append(
            f'L 01/02/2024 - 03:04:{i % 60:02d}: "Alice<2><STEAM_1:2><CT>" say "bench-{i}"\n'
        )
    return "".join(lines).encode("utf-8")


def _run_fake_mode(*, lines: int, batch_size: int, buffer_size: int) -> None:
    from hlstats_py.events import ChatEventHandler, EventDispatcher
    from hlstats_py import EventContext, LocalizationCatalog
    from hlstats_py.events import ActionDefinition, GameSchema, WeaponDefinition
    from hlstats_py.protocol import parse_log_event
    from hlstats_py.storage import _INSERT_CHAT_QUERY, _PLAYER_BY_UNIQUE_QUERY, EventStorage

    mod = _load_test_storage_module()
    FakeConnection = mod.FakeConnection
    QueryResponse = mod.QueryResponse
    StubAdapter = mod.StubAdapter

    schema = GameSchema(
        game="csgo",
        weapons={"ak47": WeaponDefinition(code="ak47", name="AK-47")},
        actions={"planted_bomb": ActionDefinition(code="planted_bomb", description="Bomb")},
    )
    localization = LocalizationCatalog(templates={}, default_template="{event_code}")
    event_context = EventContext(
        server_id=7,
        game="csgo",
        schema=schema,
        localization=localization,
        extras={"map": "de_dust2"},
    )
    chat_dispatcher = EventDispatcher([ChatEventHandler()])

    key = (_PLAYER_BY_UNIQUE_QUERY, ("STEAM_1:2", "csgo"))
    responses: Dict[tuple[str, tuple[object, ...] | None], List[QueryResponse]] = defaultdict(list)
    for _ in range(lines):
        responses[key].append(QueryResponse(fetchone=(101,)))

    connection = FakeConnection(dict(responses))
    adapter = StubAdapter(connection)
    storage = EventStorage(adapter, clock=lambda: datetime(2024, 1, 2, 3, 4, 5))
    storage.begin_stdin_batch(transaction_batch_size=batch_size)
    storage.configure_event_buffer(max_buffered_events=buffer_size)

    raw = _build_chat_log_lines(lines)
    t0 = perf_counter()
    for line in raw.splitlines():
        text = line.decode("utf-8")
        event = parse_log_event(text, server_address="127.0.0.1:27015")
        update = chat_dispatcher.dispatch(event, event_context)
        storage.record(update, event_context)
    storage.finalize_import()
    storage.end_stdin_batch()
    elapsed = perf_counter() - t0

    chat_n = sum(1 for q, _ in connection.executed if q == _INSERT_CHAT_QUERY)
    print(f"mode=fake lines={lines} batch_size={batch_size} buffer_size={buffer_size}")
    print(f"elapsed_sec={elapsed:.4f} lines_per_sec={lines / elapsed:.1f}")
    print(f"commits={connection.commit_calls} chat_inserts_executed={chat_n}")


def _run_subprocess_mode(
    *,
    lines: int,
    configfile: Path,
    batch_size: int,
    parser_backend: str,
    server_ip: str,
    server_port: int,
) -> int:
    data = _build_chat_log_lines(lines)
    env = os.environ.copy()
    sep = ";" if sys.platform == "win32" else ":"
    env["PYTHONPATH"] = sep.join([str(_SCRIPTS), str(_SCRIPTS / "proxy_daemon_py")])
    cmd = [
        sys.executable,
        "-m",
        "hlstats_py.runtime",
        "--configfile",
        str(configfile),
        "--stdin",
        "--server-ip",
        server_ip,
        "--server-port",
        str(server_port),
        "--stdin-transaction-batch-size",
        str(batch_size),
        "--parser-backend",
        parser_backend,
    ]
    t0 = perf_counter()
    proc = subprocess.run(
        cmd,
        input=data,
        env=env,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        timeout=600,
    )
    elapsed = perf_counter() - t0
    print(
        f"mode=subprocess lines={lines} exit={proc.returncode} "
        f"elapsed_sec={elapsed:.4f} lines_per_sec={lines / elapsed:.1f}"
    )
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, default=300, help="Synthetic chat lines (default: 300).")
    parser.add_argument("--mode", choices=("fake", "subprocess"), default="fake")
    parser.add_argument(
        "--configfile",
        type=Path,
        default=_SCRIPT_DIR / "bench_ephemeral" / "hlstats.host.conf",
        help="subprocess: hlstats.conf with reachable DB.",
    )
    parser.add_argument("--stdin-transaction-batch-size", type=int, default=2500)
    parser.add_argument("--buffer-max-events", type=int, default=5000)
    parser.add_argument("--parser-backend", choices=("python", "native"), default="native")
    parser.add_argument(
        "--server-ip",
        default="172.19.0.1",
        help="Must match hlstats_Servers in DB (baseline default 172.19.0.1).",
    )
    parser.add_argument("--server-port", type=int, default=27015)
    args = parser.parse_args()

    if args.lines < 1:
        print("--lines must be >= 1", file=sys.stderr)
        return 2

    if args.mode == "fake":
        _run_fake_mode(
            lines=args.lines,
            batch_size=args.stdin_transaction_batch_size,
            buffer_size=args.buffer_max_events,
        )
        return 0

    if not args.configfile.is_file():
        print(f"Config not found: {args.configfile}", file=sys.stderr)
        return 2
    return _run_subprocess_mode(
        lines=args.lines,
        configfile=args.configfile,
        batch_size=args.stdin_transaction_batch_size,
        parser_backend=args.parser_backend,
        server_ip=args.server_ip,
        server_port=args.server_port,
    )


if __name__ == "__main__":
    raise SystemExit(main())
