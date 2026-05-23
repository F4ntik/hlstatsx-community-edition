"""Extract a small context window from a GoldSrc log file."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

try:
    from scripts.replay_baseline.locate_residual_logs import goldsrc_timestamp
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.replay_baseline.locate_residual_logs import goldsrc_timestamp


@dataclass(frozen=True)
class WindowResult:
    source: Path
    output: Path
    anchor_line: int
    start_line: int
    end_line: int


def find_anchor_line(
    log_file: Path,
    *,
    event_time: str = "",
    pattern: str = "",
    line_number: int | None = None,
) -> int:
    if line_number is not None:
        if line_number <= 0:
            raise ValueError("--line-number must be positive")
        return line_number

    if event_time:
        try:
            pattern = goldsrc_timestamp(event_time)
        except ValueError:
            pattern = event_time
    if not pattern:
        raise ValueError("one of --line-number, --event-time, or --pattern is required")

    with log_file.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle, start=1):
            if pattern in line:
                return index
    raise ValueError(f"pattern not found in {log_file}: {pattern}")


def extract_window(
    log_file: Path,
    output: Path,
    *,
    line_number: int | None = None,
    event_time: str = "",
    pattern: str = "",
    before: int = 200,
    after: int = 100,
) -> WindowResult:
    anchor = find_anchor_line(
        log_file,
        event_time=event_time,
        pattern=pattern,
        line_number=line_number,
    )
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    start = max(1, anchor - before)
    end = min(len(lines), anchor + after)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(lines[start - 1 : end]), encoding="utf-8")
    return WindowResult(
        source=log_file,
        output=output,
        anchor_line=anchor,
        start_line=start,
        end_line=end,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract a line/time/pattern-centered log window.")
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--line-number", type=int)
    parser.add_argument("--event-time", default="")
    parser.add_argument("--pattern", default="")
    parser.add_argument("--before", type=int, default=200)
    parser.add_argument("--after", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = extract_window(
        args.log_file,
        args.output,
        line_number=args.line_number,
        event_time=args.event_time,
        pattern=args.pattern,
        before=args.before,
        after=args.after,
    )
    print(
        f"extracted {result.source.name}:{result.start_line}-{result.end_line} "
        f"(anchor {result.anchor_line}) -> {result.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
