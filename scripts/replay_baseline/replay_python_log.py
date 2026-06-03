#!/usr/bin/env python3
"""Replay a raw legacy HLstats log into the Python worker with a fixed server identity.

The worker expects proxied envelopes. This helper wraps each raw log line in the
same `PROXY Key=... <server>PROXY ...` format that the Python worker consumes
at runtime, while preserving the logical source server identity from the
baseline DB (`172.19.0.1:27015` by default).

Physical log lines that continue a prior ``L mm/dd/yyyy`` record without their
own timestamp prefix (common when quotes span newlines, e.g. multi-line Rcon)
are merged before send. Records are length-framed on stdin to the in-container
sender so embedded newlines do not split one logical datagram across UDP sends.
"""

from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, TextIO

_replay_dir = Path(__file__).resolve().parent
if str(_replay_dir) not in sys.path:
    sys.path.insert(0, str(_replay_dir))
from goldsrc_log_merge import line_starts_new_goldsrc_record

DEFAULT_DATABASE = "hlstatsxce"
DEFAULT_DB_CONTAINER = "hlstatsx-python-db"
DEFAULT_WORKER_CONTAINER = "hlstatsx-python-worker"
DEFAULT_SERVER_IDENTITY = "172.19.0.1:27015"
DEFAULT_WORKER_PORT = 28000
DEFAULT_SEND_DELAY = 0.005
DEFAULT_DRAIN_DELAY = 1.0
# UDP payload ceiling minus PROXY prefix headroom (see in-container sendto).
_MAX_REPLAY_LINE_BYTES = 65000

ZERO_SEND_DELAY_UDP_WARNING = (
    "replay_python_log: --send-delay 0 disables throttling between UDP datagrams. "
    "On the parity path (host stdin -> docker exec -> 127.0.0.1:UDP inside the worker), "
    "this routinely drops most traffic; helper 'Sent N replay datagrams' does not imply "
    "the worker received or recorded N events. Do not use --send-delay 0 for legacy-vs-Python "
    f"DB parity; use a positive delay (default {DEFAULT_SEND_DELAY}) and spot-check worker logs "
    "(Received/Recorded) on a sample log."
)


def warn_if_unthrottled_udp_replay(send_delay: float) -> None:
    if send_delay == 0:
        print(ZERO_SEND_DELAY_UDP_WARNING, file=sys.stderr)


class ReplaySummary(NamedTuple):
    processed: int
    skipped: int
    errors: int
    dropped_lines: int


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a raw production HLstats log into the Python worker.",
    )
    parser.add_argument(
        "input_path",
        help="Path to a raw legacy HLstats log file or a directory containing *.log files.",
    )
    parser.add_argument(
        "--db-container",
        default=DEFAULT_DB_CONTAINER,
        help=f"MariaDB container used to fetch Proxy_Key and verify hlstats_Servers (default: {DEFAULT_DB_CONTAINER})",
    )
    parser.add_argument(
        "--worker-container",
        default=DEFAULT_WORKER_CONTAINER,
        help=f"Worker container that receives replay envelopes (default: {DEFAULT_WORKER_CONTAINER})",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"Database name to query (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--server-identity",
        default=DEFAULT_SERVER_IDENTITY,
        help=f"Logical source server identity stored in hlstats_Servers (default: {DEFAULT_SERVER_IDENTITY})",
    )
    parser.add_argument(
        "--worker-port",
        type=int,
        default=DEFAULT_WORKER_PORT,
        help=f"UDP port exposed by hlstats_py.runtime inside the worker container (default: {DEFAULT_WORKER_PORT})",
    )
    parser.add_argument(
        "--send-delay",
        type=float,
        default=DEFAULT_SEND_DELAY,
        help=(
            f"Delay in seconds between replay datagrams after each send (default: {DEFAULT_SEND_DELAY}). "
            "Use 0 only for quick experiments; parity runs against the worker must stay throttled "
            "or UDP loss will dominate."
        ),
    )
    parser.add_argument(
        "--drain-delay",
        type=float,
        default=DEFAULT_DRAIN_DELAY,
        help=f"Delay in seconds after the last datagram so the worker drains its queue (default: {DEFAULT_DRAIN_DELAY})",
    )
    parser.add_argument(
        "--skip-reload",
        action="store_true",
        help="Do not send the initial C;RELOAD; control command before replay.",
    )
    parser.add_argument(
        "--exclude-log-list",
        default="",
        help="Optional newline-delimited list of log filenames to exclude from replay.",
    )
    parser.add_argument(
        "--input-manifest",
        default="",
        help="Optional path to write the newline-delimited filenames actually sent to the worker.",
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
            "Use the same option for legacy replay to keep runtime inputs aligned."
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


def build_sender_script() -> str:
    return (
        "import socket, struct, sys, time\n"
        "proxy_key = sys.argv[1]\n"
        "server_identity = sys.argv[2]\n"
        "worker_port = int(sys.argv[3])\n"
        "should_reload = sys.argv[4] == '1'\n"
        "send_delay = float(sys.argv[5])\n"
        "drain_delay = float(sys.argv[6])\n"
        "sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
        "sock.settimeout(1.0)\n"
        "destination = ('127.0.0.1', worker_port)\n"
        "if should_reload:\n"
        "    sock.sendto(b'C;RELOAD;', destination)\n"
        "    try:\n"
        "        response = sock.recv(4096).decode('utf-8', errors='replace').strip()\n"
        "        print(f'RELOAD -> {response}')\n"
        "    except Exception as exc:\n"
        "        print(f'RELOAD -> <no response: {exc}>')\n"
        "sock.sendto(b'C;SERVERLIST;', destination)\n"
        "try:\n"
        "    response = sock.recv(4096).decode('utf-8', errors='replace').strip()\n"
        "    print('SERVERLIST ->')\n"
        "    print(response)\n"
        "except Exception as exc:\n"
        "    print(f'SERVERLIST -> <no response: {exc}>')\n"
        "prefix = f'PROXY Key={proxy_key} {server_identity}PROXY '.encode('utf-8')\n"
        "count = 0\n"
        "while True:\n"
        "    hdr = sys.stdin.buffer.read(4)\n"
        "    if not hdr:\n"
        "        break\n"
        "    if len(hdr) != 4:\n"
        "        break\n"
        "    (n,) = struct.unpack('>I', hdr)\n"
        "    if n == 0 or n > 16777216:\n"
        "        break\n"
        "    payload = b''\n"
        "    while len(payload) < n:\n"
        "        chunk = sys.stdin.buffer.read(n - len(payload))\n"
        "        if not chunk:\n"
        "            payload = b''\n"
        "            break\n"
        "        payload += chunk\n"
        "    if len(payload) != n:\n"
        "        break\n"
        "    sock.sendto(prefix + payload, destination)\n"
        "    count += 1\n"
        "    if send_delay > 0:\n"
        "        time.sleep(send_delay)\n"
        "if drain_delay > 0:\n"
        "    time.sleep(drain_delay)\n"
        "print(f'Sent {count} replay datagrams to {destination[0]}:{destination[1]}')\n"
    )


def print_summary(summary: ReplaySummary) -> None:
    print(
        "Replay summary: "
        f"processed={summary.processed}, skipped={summary.skipped}, "
        f"errors={summary.errors}, dropped_lines={summary.dropped_lines}"
    )


def run_sender(
    *,
    args: argparse.Namespace,
    proxy_key: str,
    log_paths: list[Path],
) -> ReplaySummary:
    sender_script = build_sender_script()
    command = [
        "docker",
        "exec",
        "-i",
        args.worker_container,
        "python",
        "-c",
        sender_script,
        proxy_key,
        args.server_identity,
        str(args.worker_port),
        "0" if args.skip_reload else "1",
        str(args.send_delay),
        str(args.drain_delay),
    ]

    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None

    processed = 0
    skipped = 0
    errors = 0
    dropped_lines = 0

    try:
        dropped_lines_manifest = open_dropped_lines_manifest(
            getattr(args, "dropped_lines_manifest", "")
        )
        try:
            for log_path in log_paths:
                try:
                    handle = log_path.open("rb")
                except OSError as exc:
                    errors += 1
                    print(f"error: failed to open {log_path}: {exc}", file=sys.stderr)
                    continue

                file_lines = 0
                file_dropped_lines = 0
                pending: bytes | None = None

                def write_framed(payload: bytes) -> None:
                    nonlocal file_lines
                    if not payload:
                        return
                    if len(payload) > _MAX_REPLAY_LINE_BYTES:
                        raise RuntimeError(
                            f"replay payload exceeds UDP safe size ({len(payload)} > {_MAX_REPLAY_LINE_BYTES}) "
                            f"while streaming {log_path.name}"
                        )
                    process.stdin.write(struct.pack(">I", len(payload)))
                    process.stdin.write(payload)
                    file_lines += 1

                with handle:
                    for line_number, raw_line in enumerate(handle, start=1):
                        if not raw_line.strip():
                            continue
                        if should_drop_line(args, raw_line):
                            if pending is not None:
                                write_framed(pending)
                                pending = None
                            dropped_lines += 1
                            file_dropped_lines += 1
                            if dropped_lines_manifest:
                                dropped_lines_manifest.write(
                                    f"{log_path.name}:{line_number}:empty-team-enter-event\n"
                                )
                            continue

                        body = raw_line.rstrip(b"\r\n")
                        starts_new = line_starts_new_goldsrc_record(body)
                        if starts_new:
                            if pending is not None:
                                write_framed(pending)
                            pending = body
                        else:
                            if pending is None:
                                write_framed(body)
                            else:
                                pending += b"\n" + body

                    if pending is not None:
                        write_framed(pending)
                        pending = None

                if file_lines:
                    processed += 1
                    drop_note = f", dropped={file_dropped_lines}" if file_dropped_lines else ""
                    print(f"Queued {log_path.name}{drop_note}")
                else:
                    skipped += 1
                    drop_note = f" after dropping {file_dropped_lines} lines" if file_dropped_lines else ""
                    print(f"Skipped empty log {log_path.name}{drop_note}")
        finally:
            if dropped_lines_manifest:
                dropped_lines_manifest.close()
    finally:
        process.stdin.close()

    result = process.wait()
    if result != 0:
        raise RuntimeError(f"docker exec returned {result}")

    return ReplaySummary(
        processed=processed,
        skipped=skipped,
        errors=errors,
        dropped_lines=dropped_lines,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    warn_if_unthrottled_udp_replay(args.send_delay)

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
        address, port_text = args.server_identity.rsplit(":", 1)
        port = int(port_text)
    except ValueError:
        print(
            f"error: --server-identity must look like HOST:PORT, got {args.server_identity!r}",
            file=sys.stderr,
        )
        return 2

    try:
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

        proxy_key = mysql_scalar(
            args.db_container,
            args.database,
            "SELECT value FROM hlstats_Options WHERE keyname = 'Proxy_Key'",
        )
        summary = run_sender(args=args, proxy_key=proxy_key, log_paths=log_paths)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if input_path.is_file():
        print(
            f"Replayed {input_path.name} into {args.worker_container} "
            f"with logical source server {args.server_identity}."
        )
    else:
        print(
            f"Replayed {summary.processed} log files from {input_path} into "
            f"{args.worker_container} with logical source server {args.server_identity}."
        )
    if excluded_paths:
        summary = ReplaySummary(
            processed=summary.processed,
            skipped=summary.skipped + len(excluded_paths),
            errors=summary.errors,
            dropped_lines=summary.dropped_lines,
        )
    print_summary(summary)
    if summary.errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
