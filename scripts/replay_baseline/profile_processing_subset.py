#!/usr/bin/env python3
"""Profile parser processing on a bounded, preserved HLstats log subset.

This helper only reads ``*.log`` inputs.  It neither opens a database nor
starts a runtime/replay process.  Use ``direct_import_artifacts.py --profile``
against an explicitly disposable database when SQL-write measurements are
needed.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import pstats
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from hlstats_py.goldsrc_physical_lines import iter_merged_goldsrc_physical_lines
from hlstats_py.protocol import ParserBackend, parse_log_event


@dataclass(frozen=True)
class BackendResult:
    backend: str
    files: int
    records: int
    parsed: int
    parse_errors: int
    elapsed_seconds: float
    profile_elapsed_seconds: float
    records_per_second: float
    parsed_per_second: float


def _input_files(input_path: Path, max_files: int) -> list[Path]:
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(path for path in input_path.iterdir() if path.is_file() and path.suffix.lower() == ".log")
    else:
        raise SystemExit(f"Input path does not exist: {input_path}")
    if max_files < 1:
        raise SystemExit("--max-files must be >= 1")
    files = files[:max_files]
    if not files:
        raise SystemExit(f"No .log files found under {input_path}")
    return files


def _scan(files: list[Path], backend: ParserBackend) -> tuple[int, int, int]:
    records = parsed = parse_errors = 0
    for log_path in files:
        with log_path.open("rb") as handle:
            for merged in iter_merged_goldsrc_physical_lines(handle):
                records += 1
                try:
                    parse_log_event(merged.decode("utf-8", errors="replace"), backend=backend)
                    parsed += 1
                except ValueError:
                    parse_errors += 1
    return records, parsed, parse_errors


def _profile_backend(files: list[Path], backend: ParserBackend, output_dir: Path, top: int) -> BackendResult:
    started = perf_counter()
    records, parsed, parse_errors = _scan(files, backend)
    elapsed = perf_counter() - started

    profiler = cProfile.Profile()
    profile_started = perf_counter()
    profiler.runcall(_scan, files, backend)
    profile_elapsed = perf_counter() - profile_started
    stats_path = output_dir / f"processing-{backend}.pstats"
    report_path = output_dir / f"processing-{backend}-top-{top}.txt"
    profiler.dump_stats(str(stats_path))
    with report_path.open("w", encoding="utf-8") as report:
        report.write(f"# cProfile top-{top} cumulative time; backend={backend}\n")
        pstats.Stats(profiler, stream=report).sort_stats("cumtime").print_stats(top)

    return BackendResult(
        backend=backend,
        files=len(files),
        records=records,
        parsed=parsed,
        parse_errors=parse_errors,
        elapsed_seconds=elapsed,
        profile_elapsed_seconds=profile_elapsed,
        records_per_second=(records / elapsed) if elapsed else 0.0,
        parsed_per_second=(parsed / elapsed) if elapsed else 0.0,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path, help="Preserved .log file or directory containing .log files.")
    parser.add_argument("--max-files", type=int, default=1, help="Bound the representative subset (default: 1).")
    parser.add_argument("--backends", nargs="+", choices=("python", "native"), default=("python", "native"))
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory for JSON, pstats, and top-function reports.")
    parser.add_argument("--top", type=int, default=30, help="Number of cProfile rows to emit per backend (default: 30).")
    parser.add_argument("--overwrite", action="store_true", help="Allow writing into an existing empty/non-empty output directory.")
    args = parser.parse_args(argv)
    if args.top < 1:
        parser.error("--top must be >= 1")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    files = _input_files(args.input_path, args.max_files)
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        raise SystemExit(f"Output directory is not empty (use --overwrite): {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    results = [_profile_backend(files, backend, args.output_dir, args.top) for backend in args.backends]
    summary_path = args.output_dir / "processing-profile.json"
    summary_path.write_text(
        json.dumps(
            {
                "input_files": [str(path) for path in files],
                "results": [asdict(result) for result in results],
                "db_touched": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(
            f"backend={result.backend} files={result.files} records={result.records} parsed={result.parsed} "
            f"parse_errors={result.parse_errors} elapsed_seconds={result.elapsed_seconds:.3f} "
            f"records_per_second={result.records_per_second:.1f}"
        )
    print(f"processing profile written: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
