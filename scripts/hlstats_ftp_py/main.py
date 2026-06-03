"""CLI: FTP pull + ``python -m hlstats_py.runtime --stdin``."""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from ftplib import FTP, error_perm
from pathlib import Path

from hlstats_py.cli import RuntimeSettings, load_settings
from hlstats_py.goldsrc_physical_lines import iter_merged_goldsrc_physical_lines
from hlstats_py.runtime import HlstatsRuntime, build_dispatcher
from hlstats_py.storage import EventStorage
from hlx_core.bootstrap import database_config_from_proxy_config
from hlx_core.db import SyncDatabaseAdapter
from hlx_core.log import LoggerConfig, ProxyLogger
from hlx_core.transport import ProxyUdpServer

from hlstats_ftp_py.core import (
    LogFileEntry,
    entries_to_download,
    filter_log_names,
    read_last_mtime,
    without_newest_log,
    write_last_mtime,
)

VERSION = "0.1.0"
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_SCANNED_RECORDS_RE = re.compile(r"Scanned (\d+) log records")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m hlstats_ftp_py",
        description="Fetch HLstats game logs over FTP and import via hlstats_py.runtime --stdin.",
        epilog=f"Report version with: python -m hlstats_ftp_py --version (prints hlstats_ftp_py {VERSION}).",
    )
    p.add_argument("--gs-ip", required=True, help="Game server IP (passed to worker as --server-ip)")
    p.add_argument("--gs-port", type=int, required=True, help="Game server port (--server-port)")
    p.add_argument("--ftp-ip", help="FTP host (default: same as --gs-ip)")
    p.add_argument(
        "--ftp-port",
        type=int,
        default=21,
        help="FTP control port (default: 21; use e.g. 2121 for docker-mapped dev FTP)",
    )
    p.add_argument(
        "--ftp-active",
        action="store_true",
        help="Use FTP active (PORT) mode instead of passive (PASV). Useful for FTP server in Docker when PASV_ADDRESS targets the host.",
    )
    p.add_argument("--ftp-usr", required=True, help="FTP username")
    p.add_argument(
        "--ftp-pwd",
        help="FTP password (optional if HLSTATS_FTP_PASSWORD is set; --ftp-pwd overrides env when set)",
    )
    p.add_argument("--ftp-dir", required=True, help="Remote directory containing logs")
    p.add_argument("--configfile", type=Path, required=True, help="Path to hlstats.conf for the Python worker")
    p.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    p.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for .last / .tmp files (default: current directory)",
    )
    p.add_argument(
        "--max-import-files",
        type=int,
        default=None,
        metavar="N",
        help="Import at most N log files this run after mtime filtering (default: no cap). Use for huge FTP dirs.",
    )
    p.add_argument(
        "--ftp-probe-limit",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Dev/large-corpus: only consider the first N *.log names (sorted) for MDTM/listing. "
            "Skips scanning tens of thousands of MDTM calls. Omit for full remote set."
        ),
    )
    p.add_argument(
        "--legacy-per-file-runtime",
        action="store_true",
        help=(
            "Use legacy behavior: launch `python -m hlstats_py.runtime --stdin` "
            "for each downloaded log file instead of batch importing in one runtime process."
        ),
    )
    p.add_argument(
        "--disable-mlsd",
        action="store_true",
        help="Disable MLSD listing optimization and force NLST+MDTM probing.",
    )
    p.add_argument(
        "--order-by-name",
        action="store_true",
        help=(
            "Replay/parity mode: import eligible logs by filename "
            "instead of FTP modification time. Requires a fresh .last state."
        ),
    )
    p.add_argument(
        "--stdin-verbose-events",
        action="store_true",
        help="Enable per-event logs during Python stdin parsing (slower).",
    )
    p.add_argument(
        "--parser-backend",
        choices=("python", "native"),
        default="native",
        help="Parser backend for stdin import (default: native).",
    )
    p.add_argument(
        "--stdin-transaction-batch-size",
        type=int,
        default=1000,
        help="Commit DB transaction every N stdin records (default: 1000; 0 disables batching).",
    )
    return p


def _log(quiet: bool, msg: str) -> None:
    if not quiet:
        print(msg, flush=True)


def _pythonpath_for_worker() -> str:
    return os.environ.get("PYTHONPATH", "")


def _parse_mdtm_response(ts: str) -> float | None:
    stamp = ts[4:].strip()
    try:
        if "." in stamp:
            main, frac = stamp.split(".", 1)
            dt = datetime.strptime(main, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            micro = int((frac + "000000")[:6])
            dt = dt.replace(microsecond=micro)
        else:
            dt = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _parse_modify_fact(stamp: str) -> float | None:
    """Parse MLSD `modify=YYYYMMDDHHMMSS[.sss]` into a UTC timestamp."""
    try:
        if "." in stamp:
            main, frac = stamp.split(".", 1)
            dt = datetime.strptime(main, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            micro = int((frac + "000000")[:6])
            dt = dt.replace(microsecond=micro)
        else:
            dt = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _collect_log_entries(
    ftp: FTP,
    ftp_dir: str,
    *,
    name_cap: int | None = None,
    prefer_mlsd: bool = True,
) -> list[LogFileEntry]:
    ftp.cwd(ftp_dir)
    if prefer_mlsd:
        try:
            entries: list[LogFileEntry] = []
            for name, facts in ftp.mlsd():
                if not name.lower().endswith(".log"):
                    continue
                modify = (facts.get("modify") or "").strip()
                mtime = _parse_modify_fact(modify)
                if mtime is None:
                    continue
                entries.append(LogFileEntry(name=Path(name).name, mtime=mtime))
            entries.sort(key=lambda item: item.name)
            if name_cap is not None and name_cap > 0:
                entries = entries[:name_cap]
            if entries:
                return entries
        except (AttributeError, error_perm, OSError):
            pass

    try:
        raw_names = ftp.nlst()
    except error_perm:
        raw_names = []
    names = filter_log_names(raw_names)
    names.sort()
    if name_cap is not None and name_cap > 0:
        names = names[:name_cap]
    entries: list[LogFileEntry] = []
    for name in names:
        try:
            resp = ftp.sendcmd(f"MDTM {name}")
        except error_perm:
            continue
        if not resp.startswith("213 "):
            continue
        mtime = _parse_mdtm_response(resp)
        if mtime is None:
            continue
        entries.append(LogFileEntry(name=name, mtime=mtime))
    return entries


def _ftp_download(ftp: FTP, remote_name: str, local_path: Path) -> None:
    with local_path.open("wb") as out:

        def write_chunk(block: bytes) -> None:
            out.write(block)

        ftp.retrbinary(f"RETR {remote_name}", write_chunk)


def _build_runtime_settings(args: argparse.Namespace) -> RuntimeSettings:
    cli_args = [
        "--configfile",
        str(args.configfile),
        "--stdin",
        "--server-ip",
        str(args.gs_ip),
        "--server-port",
        str(args.gs_port),
        "--parser-backend",
        str(args.parser_backend),
        "--stdin-transaction-batch-size",
        str(args.stdin_transaction_batch_size),
    ]
    if args.stdin_verbose_events:
        cli_args.append("--stdin-verbose-events")
    return load_settings(cli_args)


def _import_logs_batch(
    todo: list[LogFileEntry],
    tmp_dir: Path,
    *,
    args: argparse.Namespace,
    settings: RuntimeSettings,
    last_path: Path,
) -> int:
    adapter = SyncDatabaseAdapter(
        database_config_from_proxy_config(settings.config),
        import_mode=True,
        enable_multi_statements=True,
    )
    logger = ProxyLogger(LoggerConfig(level=settings.log_level))
    transport = ProxyUdpServer(logger)
    dispatcher = build_dispatcher()
    storage = EventStorage(
        adapter,
        use_event_timestamps_for_processing=True,
    )
    runtime = HlstatsRuntime(
        adapter,
        transport,
        logger,
        dispatcher,
        storage,
        parser_backend=settings.parser_backend,
        stdin_verbose_events=settings.stdin_verbose_events,
    )

    server_address = f"{args.gs_ip}:{args.gs_port}".strip().lower()
    imported_records = 0
    progress_every = 20000
    runtime._adapter.connect()
    try:
        runtime._reload_state()
        storage.begin_stdin_batch(transaction_batch_size=settings.stdin_transaction_batch_size)
        for index, entry in enumerate(todo, start=1):
            _log(
                not args.quiet,
                f'    - "{entry.name}" ({index}/{len(todo)}): batch parsing... ',
            )
            local_file = tmp_dir / entry.name
            file_records = 0
            with local_file.open("rb") as stdin_f:
                for merged in iter_merged_goldsrc_physical_lines(stdin_f):
                    line = merged.decode("utf-8", errors="replace")
                    if not line:
                        continue
                    runtime.process_stdin_line(line, server_address)
                    imported_records += 1
                    file_records += 1
                    if not args.quiet and file_records % progress_every == 0:
                        print(
                            f"      progress: {entry.name} -> {file_records} records",
                            flush=True,
                        )
            write_last_mtime(last_path, entry.mtime)
            _log(not args.quiet, f"done ({file_records} records).")
        runtime.finalize_stdin_import()
        storage.end_stdin_batch()
    finally:
        with contextlib.suppress(Exception):
            storage.end_stdin_batch()
        with contextlib.suppress(Exception):
            runtime._adapter.close()
    return imported_records


def run(argv: list[str] | None = None) -> int:
    argv_eff = list(sys.argv[1:] if argv is None else argv)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--version", action="store_true")
    pre_ns, remaining = pre.parse_known_args(argv_eff)
    if pre_ns.version:
        print(f"hlstats_ftp_py {VERSION}")
        return 0

    parser = _build_parser()
    args = parser.parse_args(remaining)

    explicit_pwd = args.ftp_pwd is not None
    ftp_pwd = args.ftp_pwd if explicit_pwd else os.environ.get("HLSTATS_FTP_PASSWORD")
    if ftp_pwd is None:
        print(
            "error: FTP password not set (use --ftp-pwd or HLSTATS_FTP_PASSWORD)",
            file=sys.stderr,
        )
        return 1

    gs_ip = args.gs_ip
    gs_port = args.gs_port
    ftp_ip = args.ftp_ip or gs_ip
    work_cwd = args.cwd if args.cwd is not None else Path.cwd()
    last_path = work_cwd / f"hlstats-ftp-{gs_ip}-{gs_port}.last"
    tmp_dir = work_cwd / f"hlstats-ftp-{gs_ip}-{gs_port}.tmp"

    _log(not args.quiet, f"\nStarting hlstats_ftp_py for IP {gs_ip}, Port {gs_port}...\n")
    _log(not args.quiet, " - creating tmp directory... ")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _log(not args.quiet, "OK.")

    last_mtime = read_last_mtime(last_path)
    if args.order_by_name and last_mtime:
        print(
            f"error: --order-by-name requires a fresh FTP state; remove {last_path}",
            file=sys.stderr,
        )
        return 1
    if last_mtime:
        _log(not args.quiet, f"\n - getting last mtime info... OK: last mtime {last_mtime}.\n")
    else:
        _log(not args.quiet, "\n - getting last mtime info... none: using default 0.\n")

    _log(not args.quiet, " - establishing FTP connection... ")
    ftp = FTP()
    ftp.connect(ftp_ip, port=args.ftp_port, timeout=60)
    ftp.login(args.ftp_usr, ftp_pwd)
    ftp.voidcmd("TYPE I")
    ftp.set_pasv(not args.ftp_active)
    _log(not args.quiet, "OK.")

    listing_started = time.perf_counter()
    _log(not args.quiet, " - getting complete list of log files... ")
    entries = _collect_log_entries(
        ftp,
        args.ftp_dir,
        name_cap=args.ftp_probe_limit,
        prefer_mlsd=not args.disable_mlsd,
    )
    stable = without_newest_log(entries)
    order_by = "name" if args.order_by_name else "mtime"
    todo = entries_to_download(stable, last_mtime, order_by=order_by)
    if args.max_import_files is not None and args.max_import_files > 0:
        cap = args.max_import_files
        if len(todo) > cap:
            todo = todo[:cap]
            _log(not args.quiet, f"OK. (capped import queue to {cap} oldest-eligible files)\n")
        else:
            _log(not args.quiet, "OK.\n")
    else:
        _log(not args.quiet, "OK.\n")

    listing_elapsed = time.perf_counter() - listing_started
    _log(not args.quiet, " + transfering log files, if todo:\n")
    download_started = time.perf_counter()
    try:
        for entry in todo:
            _log(not args.quiet, f'    - "{entry.name}" (mtime {entry.mtime}): transferring... ')
            local_file = tmp_dir / entry.name
            _ftp_download(ftp, entry.name, local_file)
            _log(not args.quiet, "OK.\n")
    finally:
        _log(not args.quiet, " - closing FTP connection... ")
        with contextlib.suppress(Exception):
            ftp.quit()
        _log(not args.quiet, "OK.\n")
    download_elapsed = time.perf_counter() - download_started

    env = dict(os.environ)
    pythonpath = _pythonpath_for_worker()
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    else:
        env.pop("PYTHONPATH", None)
    worker_base = [
        sys.executable,
        "-m",
        "hlstats_py.runtime",
        "--configfile",
        str(args.configfile),
        "--stdin",
        "--server-ip",
        gs_ip,
        "--server-port",
        str(gs_port),
        "--parser-backend",
        str(args.parser_backend),
        "--stdin-transaction-batch-size",
        str(args.stdin_transaction_batch_size),
    ]
    if args.stdin_verbose_events:
        worker_base.append("--stdin-verbose-events")

    parse_started = time.perf_counter()
    _log(not args.quiet, " + parsing log files:\n")
    imported_records = 0
    if args.legacy_per_file_runtime:
        for i, entry in enumerate(todo):
            progress = f"({i + 1}/{len(todo)})"
            local_file = tmp_dir / entry.name
            _log(not args.quiet, f'    - "{entry.name}" {progress}: parsing... ')
            with local_file.open("rb") as stdin_f:
                result = subprocess.run(
                    worker_base,
                    stdin=stdin_f,
                    cwd=str(work_cwd),
                    env=env,
                    capture_output=True,
                )
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
                out = (result.stdout or b"").decode("utf-8", errors="replace").strip()
                print(
                    f"error: worker exited {result.returncode} for {entry.name}\n{err}\n{out}",
                    file=sys.stderr,
                )
                return result.returncode or 2
            out = (result.stdout or b"").decode("utf-8", errors="replace")
            err = (result.stderr or b"").decode("utf-8", errors="replace")
            for stream in (out, err):
                for match in _SCANNED_RECORDS_RE.finditer(stream):
                    imported_records += int(match.group(1))
            _log(not args.quiet, "updating last mtime... ")
            write_last_mtime(last_path, entry.mtime)
            _log(not args.quiet, "OK.\n")
    else:
        _log(not args.quiet, "    - batch mode: single runtime process for all queued logs")
        settings = _build_runtime_settings(args)
        try:
            imported_records = _import_logs_batch(todo, tmp_dir, args=args, settings=settings, last_path=last_path)
        except Exception as exc:
            print(f"error: batch import failed: {exc}", file=sys.stderr)
            return 2
    parse_elapsed = time.perf_counter() - parse_started

    _log(not args.quiet, " - delete tmp log files and directory... ")
    for child in tmp_dir.glob("*"):
        with contextlib.suppress(OSError):
            child.unlink()
    with contextlib.suppress(OSError):
        tmp_dir.rmdir()
    _log(not args.quiet, "OK.\n")
    total_elapsed = listing_elapsed + download_elapsed + parse_elapsed
    files_per_sec = (len(todo) / parse_elapsed) if parse_elapsed > 0 else 0.0
    lines_per_sec = (imported_records / parse_elapsed) if parse_elapsed > 0 else 0.0
    _log(
        not args.quiet,
        (
            " - timing summary: "
            f"listing={listing_elapsed:.2f}s, download={download_elapsed:.2f}s, "
            f"parse={parse_elapsed:.2f}s, total={total_elapsed:.2f}s\n"
            f" - throughput: {files_per_sec:.2f} files/sec, {lines_per_sec:.2f} lines/sec\n"
            f" - imported: files={len(todo)}, records={imported_records}, "
            f"mode={'legacy-per-file' if args.legacy_per_file_runtime else 'batch-stdin'}\n"
        ),
    )
    _log(not args.quiet, "\nSo Long, and Thanks for all the Fish.\n\n")
    return 0
