"""Benchmark parser throughput on a real HLstats log corpus."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from hlstats_py.goldsrc_physical_lines import iter_merged_goldsrc_physical_lines
from hlstats_py.protocol import parse_log_event


def _iter_log_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() == ".log")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark hlstats_py parser backends.")
    parser.add_argument("input_path", type=Path, help="Log file or directory with .log files")
    parser.add_argument("--backend", choices=("python", "native"), default="python")
    parser.add_argument("--max-files", type=int, default=0, help="Limit number of log files (0 = all)")
    args = parser.parse_args()

    files = _iter_log_files(args.input_path)
    if args.max_files > 0:
        files = files[: args.max_files]
    if not files:
        raise SystemExit("No .log files found")

    started = time.perf_counter()
    records = 0
    parsed = 0
    for log_path in files:
        with log_path.open("rb") as handle:
            for merged in iter_merged_goldsrc_physical_lines(handle):
                records += 1
                payload = merged.decode("utf-8", errors="replace")
                try:
                    parse_log_event(payload, backend=args.backend)
                    parsed += 1
                except ValueError:
                    # Keep scan going to compare throughput on noisy datasets.
                    continue

    elapsed = time.perf_counter() - started
    rec_per_sec = records / elapsed if elapsed else 0.0
    parsed_per_sec = parsed / elapsed if elapsed else 0.0
    print(
        f"backend={args.backend} files={len(files)} records={records} parsed={parsed} "
        f"elapsed={elapsed:.3f}s records_per_sec={rec_per_sec:.1f} parsed_per_sec={parsed_per_sec:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
