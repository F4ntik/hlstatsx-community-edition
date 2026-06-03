#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cProfile
import pstats
import shutil
import tempfile
from argparse import Namespace
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

from hlstats_ftp_py.core import LogFileEntry
from hlstats_ftp_py.main import _build_runtime_settings, _import_logs_batch
from hlstats_py.storage import EventStorage

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[2]
_DEFAULT_ARTIFACTS = _SCRIPT_DIR / "artifacts"
_DEFAULT_CONFIG_DOCKER = Path("/app/hlstats.conf")
_DEFAULT_CONFIG_REPO = _SCRIPT_DIR / "comparison" / "python" / "hlstats.conf"
_DEFAULT_AUDIT = _REPO_ROOT / "docs" / "audits" / "legacy-python-parity-20260423"


def _default_artifacts_dir() -> Path:
    if _DEFAULT_ARTIFACTS.is_dir():
        return _DEFAULT_ARTIFACTS
    docker = Path("/app/scripts/replay_baseline/artifacts")
    return docker if docker.is_dir() else _DEFAULT_ARTIFACTS


def _default_configfile() -> Path:
    if _DEFAULT_CONFIG_DOCKER.is_file():
        return _DEFAULT_CONFIG_DOCKER
    if _DEFAULT_CONFIG_REPO.is_file():
        return _DEFAULT_CONFIG_REPO
    return _DEFAULT_CONFIG_DOCKER


def _default_audit_dir() -> Path:
    if (_REPO_ROOT / "docs").is_dir():
        return _DEFAULT_AUDIT
    return Path("/app/docs/audits/legacy-python-parity-20260423")


def _build_entries(artifacts: Path, *, max_files: int | None = None) -> list[LogFileEntry]:
    entries: list[LogFileEntry] = []
    for path in artifacts.glob("*.log"):
        try:
            entries.append(LogFileEntry(name=path.name, mtime=path.stat().st_mtime))
        except OSError:
            continue
    entries.sort(key=lambda item: item.name)
    if max_files is not None and max_files > 0:
        entries = entries[:max_files]
    return entries


def _stage_replicated_log_files(artifacts: Path, work: Path, file_count: int) -> tuple[list[LogFileEntry], Path]:
    """Copy ``file_count`` ``*.log`` paths into *work*/bench_staged_logs for throughput tests."""

    sources = sorted(p for p in artifacts.glob("*.log") if p.is_file())
    if not sources:
        raise SystemExit(f"No .log files under {artifacts}")
    staged = work / "bench_staged_logs"
    if staged.is_dir():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    entries: list[LogFileEntry] = []
    for idx in range(file_count):
        src = sources[idx % len(sources)]
        name = f"_bench_{idx:05d}__{src.name}"
        dst = staged / name
        shutil.copy2(src, dst)
        entries.append(LogFileEntry(name=name, mtime=dst.stat().st_mtime))
    return entries, staged


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Direct local artifacts import helper for hlstats_py runtime."
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directory containing *.log artifacts (default: next to this script, or /app/... in Docker).",
    )
    parser.add_argument(
        "--configfile",
        type=Path,
        default=None,
        help="hlstats.conf for DB and worker options (default: /app/hlstats.conf or comparison/python/hlstats.conf).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Working directory for .last / temp state (default: /tmp/ftp_work or a temp dir under tempfile).",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=None,
        help="Directory for perf-profile.txt when --profile (default: repo docs/audits/... or under /app/docs).",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Enable cProfile and write top functions to perf-profile.txt.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional cap for number of input .log files (useful for quick profiling).",
    )
    parser.add_argument(
        "--file-count",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Process exactly N .log files: if the artifacts directory has fewer than N files, "
            "copy real logs round-robin into work/bench_staged_logs (for throughput benchmarks). "
            "Ignores --max-files when set."
        ),
    )
    parser.add_argument(
        "--parser-backend",
        choices=("python", "native"),
        default="native",
        help="Parser backend for stdin parsing (default: native).",
    )
    parser.add_argument(
        "--stdin-transaction-batch-size",
        type=int,
        default=1000,
        help="Commit DB transaction every N stdin records (default: 1000).",
    )
    parser.add_argument(
        "--gs-ip",
        default="172.19.0.1",
        help="Game server IP in hlstats_Servers for stdin routing (default matches baseline_reset dump).",
    )
    parser.add_argument(
        "--gs-port",
        type=int,
        default=27015,
        help="Game server port for stdin routing (default 27015).",
    )
    return parser.parse_args()


def main() -> int:
    cli = _parse_args()
    artifacts = cli.artifacts_dir or _default_artifacts_dir()
    if not artifacts.is_dir():
        raise SystemExit(f"Artifacts directory does not exist or is not a directory: {artifacts}")

    configfile = cli.configfile or _default_configfile()
    if not configfile.is_file():
        raise SystemExit(f"Config file not found: {configfile}")

    work = cli.work_dir
    if work is None:
        if _DEFAULT_CONFIG_DOCKER.is_file():
            work = Path("/tmp/ftp_work")
        else:
            work = Path(tempfile.gettempdir()) / "hlstats_direct_import_work"
    work.mkdir(parents=True, exist_ok=True)
    safe_ip = str(cli.gs_ip).replace(":", "_")
    last_path = work / f"direct-artifacts-{safe_ip}-{cli.gs_port}.last"
    if cli.file_count is not None and cli.file_count > 0:
        entries, read_dir = _stage_replicated_log_files(artifacts, work, cli.file_count)
    else:
        read_dir = artifacts
        entries = _build_entries(artifacts, max_files=cli.max_files)

    args = Namespace(
        gs_ip=cli.gs_ip,
        gs_port=cli.gs_port,
        ftp_ip="log-ftp",
        ftp_port=21,
        ftp_active=True,
        ftp_usr="hlxslogs",
        ftp_pwd="hlxftp123",
        ftp_dir="/",
        configfile=configfile,
        quiet=True,
        cwd=work,
        max_import_files=None,
        ftp_probe_limit=None,
        legacy_per_file_runtime=False,
        disable_mlsd=False,
        stdin_verbose_events=False,
        parser_backend=cli.parser_backend,
        stdin_transaction_batch_size=cli.stdin_transaction_batch_size,
    )

    settings = _build_runtime_settings(args)
    profiler: cProfile.Profile | None = None
    query_counter: Counter[str] = Counter()
    original_execute = EventStorage._execute

    def _counting_execute(
        self: EventStorage,
        connection: Any,
        query: str,
        params: tuple[Any, ...] | None,
    ) -> None:
        query_counter[query] += 1
        original_execute(self, connection, query, params)

    started = perf_counter()
    if cli.profile:
        profiler = cProfile.Profile()
        profiler.enable()
        EventStorage._execute = _counting_execute

    try:
        records = _import_logs_batch(entries, read_dir, args=args, settings=settings, last_path=last_path)
    finally:
        if cli.profile:
            EventStorage._execute = original_execute
            if profiler is not None:
                profiler.disable()
    elapsed = perf_counter() - started

    audit_dir = cli.audit_dir or _default_audit_dir()
    profile_txt = audit_dir / "perf-profile.txt"
    if cli.profile and profiler is not None:
        audit_dir.mkdir(parents=True, exist_ok=True)
        with profile_txt.open("w", encoding="utf-8") as out:
            out.write("# cProfile top-30 (cumtime)\n")
            stats = pstats.Stats(profiler, stream=out).sort_stats("cumtime")
            stats.print_stats(30)
            out.write("\n# SQL template counts (top-30)\n")
            for query, count in query_counter.most_common(30):
                out.write(f"{count:>10} | {query}\n")
            out.write("\n")
            lines_per_sec = (records / elapsed) if elapsed > 0 else 0.0
            sql_total = sum(query_counter.values())
            out.write(
                "baseline-metrics: "
                f"files={len(entries)}, records={records}, elapsed_s={elapsed:.3f}, "
                f"lines_per_sec={lines_per_sec:.2f}, sql_exec_total={sql_total}, "
                f"sql_per_record={(sql_total / records) if records else 0:.3f}\n"
            )
        print(f"direct-import profile written: {profile_txt}", flush=True)

    lines_per_sec = (records / elapsed) if elapsed > 0 else 0.0
    sql_extra = ""
    if cli.profile and query_counter:
        sql_total = sum(query_counter.values())
        sql_extra = f", sql_exec_total={sql_total}, sql_per_record={(sql_total / records) if records else 0:.3f}"
    print(
        "direct-import summary: "
        f"files={len(entries)}, records={records}, elapsed_s={elapsed:.3f}, "
        f"lines_per_sec={lines_per_sec:.2f}, "
        f"mode=batch-stdin-local, parser={cli.parser_backend}{sql_extra}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
