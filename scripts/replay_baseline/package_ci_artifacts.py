#!/usr/bin/env python3
"""Create the only replay artifact that CI is permitted to publish.

Raw replay logs, database snapshots, traces, local configuration, and compare
output can contain credentials, player data, or host-specific details.  This
helper deliberately accepts only bounded execution metadata and writes one
new summary; it never copies or reads replay output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final, Sequence


SUMMARY_FILENAME: Final = "nightly-parity-summary.json"
_ALLOWED_OUTCOMES: Final = frozenset({"success", "failure", "cancelled", "skipped"})


def _outcome(value: str) -> str:
    if value not in _ALLOWED_OUTCOMES:
        choices = ", ".join(sorted(_ALLOWED_OUTCOMES))
        raise argparse.ArgumentTypeError(f"outcome must be one of: {choices}")
    return value


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max import files must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("max import files must be positive")
    return parsed


def package_summary(
    output_directory: Path,
    *,
    max_import_files: int,
    dual_replay_outcome: str,
) -> Path:
    """Write a fixed-name, metadata-only summary and return its path."""
    outcomes = {"dual_replay": dual_replay_outcome}
    invalid_outcomes = sorted(set(outcomes.values()) - _ALLOWED_OUTCOMES)
    if invalid_outcomes:
        raise ValueError(f"unsupported step outcome(s): {', '.join(invalid_outcomes)}")
    if max_import_files <= 0:
        raise ValueError("max_import_files must be positive")

    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / SUMMARY_FILENAME
    payload = {
        "schema_version": 2,
        "publication": "sanitized-nightly-parity-summary",
        "max_import_files": max_import_files,
        "steps": outcomes,
        "dual_replay_integrated_gates": [
            "historical_maintenance",
            "database_compare",
            "web_smoke",
        ],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--max-import-files", type=_positive_int, required=True)
    parser.add_argument("--dual-replay-outcome", type=_outcome, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = package_summary(
        args.output_directory,
        max_import_files=args.max_import_files,
        dual_replay_outcome=args.dual_replay_outcome,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
