#!/usr/bin/env python3
"""Replay a raw legacy HLstats log into the Python worker with a fixed server identity.

The worker expects proxied envelopes. This helper wraps each raw log line in the
same `PROXY Key=... <server>PROXY ...` format that the Python worker consumes
at runtime, while preserving the logical source server identity from the
baseline DB (`172.19.0.1:27015` by default).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_DATABASE = "hlstatsxce"
DEFAULT_DB_CONTAINER = "hlstatsx-python-db"
DEFAULT_WORKER_CONTAINER = "hlstatsx-python-worker"
DEFAULT_SERVER_IDENTITY = "172.19.0.1:27015"
DEFAULT_WORKER_PORT = 28000
DEFAULT_SEND_DELAY = 0.005
DEFAULT_DRAIN_DELAY = 1.0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a raw production HLstats log into the Python worker.",
    )
    parser.add_argument("log_file", help="Path to the raw legacy HLstats log file.")
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
        help=f"Delay in seconds between replay datagrams (default: {DEFAULT_SEND_DELAY})",
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
    return parser.parse_args(argv)


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
        "import socket, sys, time\n"
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
        "for raw_line in sys.stdin.buffer.read().splitlines():\n"
        "    if not raw_line:\n"
        "        continue\n"
        "    sock.sendto(prefix + raw_line, destination)\n"
        "    count += 1\n"
        "    if send_delay > 0:\n"
        "        time.sleep(send_delay)\n"
        "if drain_delay > 0:\n"
        "    time.sleep(drain_delay)\n"
        "print(f'Sent {count} replay datagrams to {destination[0]}:{destination[1]}')\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    log_path = Path(args.log_file)
    if not log_path.is_file():
        print(f"error: log file not found: {log_path}", file=sys.stderr)
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

        log_data = log_path.read_bytes()
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
        result = subprocess.run(command, input=log_data)
        if result.returncode != 0:
            raise RuntimeError(f"docker exec returned {result.returncode}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Replayed {log_path.name} into {args.worker_container} "
        f"with logical source server {args.server_identity}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
