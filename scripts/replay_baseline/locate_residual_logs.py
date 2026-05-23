"""Find likely source log files for a replay residual example."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class ResidualNeedle:
    event_time: str = ""
    player: str = ""
    unique_id: str = ""
    action: str = ""
    map_name: str = ""
    message: str = ""


@dataclass(frozen=True)
class CandidateLog:
    path: Path
    score: int
    matched_fields: tuple[str, ...]


def goldsrc_timestamp(value: str) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    return parsed.strftime("%m/%d/%Y - %H:%M:%S")


def steam_search_terms(unique_id: str) -> tuple[str, ...]:
    unique_id = unique_id.strip()
    if not unique_id:
        return ()
    terms = [unique_id]
    parts = unique_id.split(":")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        auth, account = parts
        terms.extend([f"STEAM_0:{auth}:{account}", f"STEAM_1:{auth}:{account}"])
    return tuple(dict.fromkeys(terms))


def find_candidate_logs(
    artifacts_dir: Path, needle: ResidualNeedle, *, limit: int = 10
) -> list[CandidateLog]:
    candidates: list[CandidateLog] = []
    for path in sorted(artifacts_dir.glob("*.log")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        score, fields = _score_text(text, needle)
        if score > 0:
            candidates.append(CandidateLog(path=path, score=score, matched_fields=tuple(fields)))
    candidates.sort(key=lambda item: (-item.score, item.path.name))
    return candidates[:limit]


def _score_text(text: str, needle: ResidualNeedle) -> tuple[int, list[str]]:
    score = 0
    fields: list[str] = []

    if needle.event_time:
        try:
            timestamp = goldsrc_timestamp(needle.event_time)
        except ValueError:
            timestamp = needle.event_time
        if timestamp in text:
            score += 5
            fields.append("event_time")

    if needle.unique_id:
        if any(term in text for term in steam_search_terms(needle.unique_id)):
            score += 4
            fields.append("unique_id")

    for field_name, weight, value in (
        ("player", 3, needle.player),
        ("action", 2, needle.action),
        ("map", 2, needle.map_name),
        ("message", 1, needle.message),
    ):
        if value and value in text:
            score += weight
            fields.append(field_name)

    return score, fields


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank log files that likely produced a residual.")
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--event-time", default="")
    parser.add_argument("--player", default="")
    parser.add_argument("--unique-id", default="")
    parser.add_argument("--action", default="")
    parser.add_argument("--map", dest="map_name", default="")
    parser.add_argument("--message", default="")
    parser.add_argument("--limit", type=int, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    needle = ResidualNeedle(
        event_time=args.event_time,
        player=args.player,
        unique_id=args.unique_id,
        action=args.action,
        map_name=args.map_name,
        message=args.message,
    )
    results = find_candidate_logs(args.artifacts_dir, needle, limit=args.limit)
    for candidate in results:
        fields = ",".join(candidate.matched_fields)
        print(f"score={candidate.score}\tfields={fields}\t{candidate.path}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
