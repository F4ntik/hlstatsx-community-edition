#!/usr/bin/env python3
"""Replay raw HLstats log files through the legacy Perl daemon in stdin mode."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


DEFAULT_DATABASE = "hlstatsxce"
DEFAULT_DB_CONTAINER = "hlstatsx-legacy-db"
DEFAULT_DAEMON_IMAGE = "startersclan/hlstatsx-community-edition:1.11.4-daemon"
DEFAULT_DOCKER_NETWORK = "legacy_hlstatsx_legacy_net"
DEFAULT_SERVER_IDENTITY = "37.230.137.48:27015"
DEFAULT_DB_HOST = "db:3306"
DEFAULT_DB_USERNAME = "hlstatsxce"
DEFAULT_DB_PASSWORD = "hlx123"


@dataclass(frozen=True)
class ReplaySummary:
    processed: int
    skipped: int
    errors: int
    lines: int
    dropped_lines: int
    elapsed_seconds: float


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a raw legacy HLstats log file or sorted directory corpus "
            "through the legacy Perl daemon without buffering the corpus."
        ),
    )
    parser.add_argument(
        "input_path",
        help="Path to a raw legacy HLstats log file or directory containing *.log files.",
    )
    parser.add_argument(
        "--db-container",
        default=DEFAULT_DB_CONTAINER,
        help=f"MariaDB container used to verify hlstats_Servers (default: {DEFAULT_DB_CONTAINER})",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"Database name to query and replay into (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--daemon-image",
        default=DEFAULT_DAEMON_IMAGE,
        help=f"Legacy daemon image to run for stdin replay (default: {DEFAULT_DAEMON_IMAGE})",
    )
    parser.add_argument(
        "--docker-network",
        default=DEFAULT_DOCKER_NETWORK,
        help=f"Docker network where the comparison DB is reachable as db (default: {DEFAULT_DOCKER_NETWORK})",
    )
    parser.add_argument(
        "--db-host",
        default=DEFAULT_DB_HOST,
        help=f"Database host passed to the legacy daemon (default: {DEFAULT_DB_HOST})",
    )
    parser.add_argument(
        "--db-username",
        default=DEFAULT_DB_USERNAME,
        help=f"Database username passed to the legacy daemon (default: {DEFAULT_DB_USERNAME})",
    )
    parser.add_argument(
        "--db-password",
        default=DEFAULT_DB_PASSWORD,
        help="Database password passed to the legacy daemon.",
    )
    parser.add_argument(
        "--server-identity",
        default=DEFAULT_SERVER_IDENTITY,
        help=f"Logical source server identity stored in hlstats_Servers (default: {DEFAULT_SERVER_IDENTITY})",
    )
    parser.add_argument(
        "--daemon-output",
        choices=("inherit", "quiet"),
        default="quiet",
        help="Use 'inherit' to show daemon stdout/stderr during smoke debugging (default: quiet).",
    )
    parser.add_argument(
        "--files-per-daemon",
        type=int,
        default=0,
        help=(
            "Restart the legacy daemon after this many input files. "
            "Use 0 to stream the whole input through one daemon process (default: 0)."
        ),
    )
    parser.add_argument(
        "--event-queue-size",
        type=int,
        default=0,
        help=(
            "Legacy daemon event queue size. The daemon recommends setting this "
            "for stdin imports, but the pinned legacy image rejects the argument "
            "in CLI mode; use 0 to omit the option (default: 0)."
        ),
    )
    parser.add_argument(
        "--exclude-log-list",
        default="",
        help="Optional newline-delimited list of log filenames to exclude from replay.",
    )
    parser.add_argument(
        "--input-manifest",
        default="",
        help="Optional path to write the newline-delimited filenames actually sent to the daemon.",
    )
    parser.add_argument(
        "--excluded-manifest",
        default="",
        help="Optional path to write the newline-delimited filenames excluded before replay.",
    )
    parser.add_argument(
        "--drop-empty-team-enter-events",
        action="store_true",
        help=(
            "Drop legacy-crashing 'entered the game' lines whose player team field is empty. "
            "Use the same option for Python replay to keep runtime inputs aligned."
        ),
    )
    parser.add_argument(
        "--dropped-lines-manifest",
        default="",
        help="Optional path to write dropped line locations when line filters are enabled.",
    )
    return parser.parse_args(argv)


def resolve_log_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(
            (path for path in input_path.iterdir() if path.is_file() and path.suffix.lower() == ".log"),
            key=lambda item: item.name,
        )
    raise FileNotFoundError(f"path not found: {input_path}")


def read_excluded_names(path_text: str) -> set[str]:
    if not path_text:
        return set()
    path = Path(path_text)
    names: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            names.add(Path(name).name)
    return names


def filter_excluded_logs(
    log_paths: list[Path],
    excluded_names: set[str],
) -> tuple[list[Path], list[Path]]:
    if not excluded_names:
        return log_paths, []
    included: list[Path] = []
    excluded: list[Path] = []
    for path in log_paths:
        if path.name in excluded_names:
            excluded.append(path)
        else:
            included.append(path)
    return included, excluded


def write_manifest(path_text: str, log_paths: list[Path]) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{log_path.name}\n" for log_path in log_paths),
        encoding="utf-8",
    )


EMPTY_TEAM_ENTER_EVENT_RE = re.compile(
    rb'"[^"\r\n]*<\d+><[^>\r\n]*><>" entered the game'
)


def should_drop_line(args: argparse.Namespace, raw_line: bytes) -> bool:
    return bool(
        getattr(args, "drop_empty_team_enter_events", False)
        and EMPTY_TEAM_ENTER_EVENT_RE.search(raw_line)
    )


def open_dropped_lines_manifest(path_text: str) -> TextIO | None:
    if not path_text:
        return None
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def mysql_scalar(container: str, database: str, sql: str) -> str:
    command = [
        "docker",
        "exec",
        container,
        "mysql",
        "-uroot",
        "-proot123",
        "-D",
        database,
        "--batch",
        "--raw",
        "--skip-column-names",
        "-e",
        sql,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    value = result.stdout.strip()
    if not value:
        raise RuntimeError(f"Empty result for query: {sql}")
    return value.splitlines()[0]


def split_server_identity(server_identity: str) -> tuple[str, int]:
    try:
        address, port_text = server_identity.rsplit(":", 1)
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(
            f"--server-identity must look like HOST:PORT, got {server_identity!r}"
        ) from exc
    if not address:
        raise ValueError("--server-identity host must not be empty")
    return address, port


def build_daemon_command(args: argparse.Namespace, address: str, port: int) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        args.docker_network,
        args.daemon_image,
        "--stdin",
        f"--server-ip={address}",
        f"--server-port={port}",
        f"--db-host={args.db_host}",
        f"--db-name={args.database}",
        f"--db-username={args.db_username}",
        f"--db-password={args.db_password}",
        "--nodns-resolveip",
    ]
    if args.event_queue_size < 0:
        raise ValueError("--event-queue-size must be greater than or equal to 0")
    if args.event_queue_size > 0:
        command.append(f"--event-queue-size={args.event_queue_size}")
    return command


def batched_log_paths(log_paths: list[Path], batch_size: int) -> list[list[Path]]:
    if batch_size <= 0:
        return [log_paths]
    return [
        log_paths[index : index + batch_size]
        for index in range(0, len(log_paths), batch_size)
    ]


def stream_logs(
    args: argparse.Namespace,
    process: subprocess.Popen[bytes],
    log_paths: list[Path],
    dropped_lines_manifest: TextIO | None,
) -> tuple[int, int, int, int, int]:
    assert process.stdin is not None
    processed = 0
    skipped = 0
    errors = 0
    lines = 0
    dropped_lines = 0
    previous_ended_with_newline = True

    for log_path in log_paths:
        file_lines = 0
        file_dropped_lines = 0
        try:
            handle = log_path.open("rb")
        except OSError as exc:
            errors += 1
            print(f"error: failed to open {log_path}: {exc}", file=sys.stderr)
            continue

        try:
            with handle:
                for line_number, raw_line in enumerate(handle, start=1):
                    if not raw_line.strip():
                        continue
                    if should_drop_line(args, raw_line):
                        dropped_lines += 1
                        file_dropped_lines += 1
                        if dropped_lines_manifest:
                            dropped_lines_manifest.write(
                                f"{log_path.name}:{line_number}:empty-team-enter-event\n"
                            )
                        continue

                    if not previous_ended_with_newline:
                        try:
                            process.stdin.write(b"\n")
                        except OSError as exc:
                            raise RuntimeError(
                                f"legacy daemon stdin closed before {log_path.name}: {exc}"
                            ) from exc
                        previous_ended_with_newline = True

                    try:
                        process.stdin.write(raw_line)
                    except OSError as exc:
                        raise RuntimeError(
                            f"legacy daemon stdin closed while streaming {log_path.name}: {exc}"
                        ) from exc

                    previous_ended_with_newline = raw_line.endswith((b"\n", b"\r"))
                    file_lines += 1
                    lines += 1
        except OSError as exc:
            errors += 1
            print(f"error: failed to read {log_path}: {exc}", file=sys.stderr)
            continue

        if file_lines:
            processed += 1
            drop_note = f", dropped={file_dropped_lines}" if file_dropped_lines else ""
            print(f"Queued {log_path.name}: {file_lines} lines{drop_note}")
            sys.stdout.flush()
        else:
            skipped += 1
            drop_note = f" after dropping {file_dropped_lines} lines" if file_dropped_lines else ""
            print(f"Skipped empty log {log_path.name}{drop_note}")
            sys.stdout.flush()

        daemon_status = process.poll()
        if daemon_status is not None:
            raise RuntimeError(
                f"legacy daemon exited with status {daemon_status} after {log_path.name}"
            )

    return processed, skipped, errors, lines, dropped_lines


def close_daemon_stdin(process: subprocess.Popen[bytes], context: str) -> None:
    if not process.stdin or process.stdin.closed:
        return
    try:
        process.stdin.close()
    except OSError as exc:
        raise RuntimeError(f"failed to close legacy daemon stdin {context}: {exc}") from exc


def run_daemon_batch(
    args: argparse.Namespace,
    address: str,
    port: int,
    log_paths: list[Path],
    dropped_lines_manifest: TextIO | None,
) -> ReplaySummary:
    command = build_daemon_command(args, address, port)
    output_target = None if args.daemon_output == "inherit" else subprocess.DEVNULL
    started_at = time.perf_counter()
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=output_target,
        stderr=output_target,
    )

    try:
        processed, skipped, errors, lines, dropped_lines = stream_logs(
            args,
            process,
            log_paths,
            dropped_lines_manifest,
        )
        close_daemon_stdin(process, "after streaming all logs")
    except BaseException:
        try:
            close_daemon_stdin(process, "after replay failure")
        except RuntimeError as close_exc:
            print(f"warning: {close_exc}", file=sys.stderr)
        raise

    result = process.wait()
    elapsed = time.perf_counter() - started_at
    if result != 0:
        raise RuntimeError(f"legacy daemon replay exited with status {result}")

    return ReplaySummary(
        processed=processed,
        skipped=skipped,
        errors=errors,
        lines=lines,
        dropped_lines=dropped_lines,
        elapsed_seconds=elapsed,
    )


def run_replay(args: argparse.Namespace, log_paths: list[Path]) -> ReplaySummary:
    address, port = split_server_identity(args.server_identity)
    server_exists = mysql_scalar(
        args.db_container,
        args.database,
        "SELECT COUNT(*) "
        "FROM hlstats_Servers "
        f"WHERE address = '{address}' AND port = {port}",
    )
    if server_exists != "1":
        raise RuntimeError(
            f"hlstats_Servers does not contain exactly one row for {args.server_identity}"
        )

    if args.files_per_daemon < 0:
        raise ValueError("--files-per-daemon must be greater than or equal to 0")

    started_at = time.perf_counter()
    processed = 0
    skipped = 0
    errors = 0
    lines = 0
    dropped_lines = 0
    batches = batched_log_paths(log_paths, args.files_per_daemon)

    with open_dropped_lines_manifest(args.dropped_lines_manifest) as dropped_lines_manifest:
        for batch_index, batch_paths in enumerate(batches, start=1):
            if args.files_per_daemon > 0:
                print(
                    "Starting daemon batch "
                    f"{batch_index}/{len(batches)}: {batch_paths[0].name}..{batch_paths[-1].name} "
                    f"({len(batch_paths)} files)"
                )
                sys.stdout.flush()
            summary = run_daemon_batch(args, address, port, batch_paths, dropped_lines_manifest)
            processed += summary.processed
            skipped += summary.skipped
            errors += summary.errors
            lines += summary.lines
            dropped_lines += summary.dropped_lines

    return ReplaySummary(
        processed=processed,
        skipped=skipped,
        errors=errors,
        lines=lines,
        dropped_lines=dropped_lines,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def print_summary(summary: ReplaySummary) -> None:
    files_per_second = summary.processed / summary.elapsed_seconds if summary.elapsed_seconds else 0.0
    lines_per_second = summary.lines / summary.elapsed_seconds if summary.elapsed_seconds else 0.0
    print(
        "Replay summary: "
        f"processed={summary.processed}, skipped={summary.skipped}, errors={summary.errors}, "
        f"lines={summary.lines}, dropped_lines={summary.dropped_lines}, "
        f"elapsed={summary.elapsed_seconds:.3f}s, "
        f"throughput={files_per_second:.2f} files/sec, {lines_per_second:.2f} lines/sec"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_path = Path(args.input_path)

    try:
        log_paths = resolve_log_paths(input_path)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        excluded_names = read_excluded_names(args.exclude_log_list)
    except OSError as exc:
        print(f"error: failed to read --exclude-log-list: {exc}", file=sys.stderr)
        return 2
    log_paths, excluded_paths = filter_excluded_logs(log_paths, excluded_names)
    try:
        write_manifest(args.input_manifest, log_paths)
        write_manifest(args.excluded_manifest, excluded_paths)
    except OSError as exc:
        print(f"error: failed to write replay manifest: {exc}", file=sys.stderr)
        return 2
    for excluded_path in excluded_paths:
        print(f"Excluded {excluded_path.name} via --exclude-log-list")
    if not log_paths:
        print(f"error: no .log files found under {input_path}", file=sys.stderr)
        return 2

    try:
        summary = run_replay(args, log_paths)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if input_path.is_file():
        print(
            f"Replayed {input_path.name} through the legacy daemon "
            f"with logical source server {args.server_identity}."
        )
    else:
        print(
            f"Replayed {summary.processed} log files from {input_path} through "
            f"the legacy daemon with logical source server {args.server_identity}."
        )
    if excluded_paths:
        summary = ReplaySummary(
            processed=summary.processed,
            skipped=summary.skipped + len(excluded_paths),
            errors=summary.errors,
            lines=summary.lines,
            dropped_lines=summary.dropped_lines,
            elapsed_seconds=summary.elapsed_seconds,
        )
    print_summary(summary)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
