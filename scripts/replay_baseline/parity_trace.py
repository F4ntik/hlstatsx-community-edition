"""Normalize and compare replay DB write traces.

This module is intentionally independent from the live replay runners. It gives
both sides of a parity investigation a shared, small format:

    {"event_ref": "L0001:42", "sql": "...", "params": [...]}

Python can emit that shape from its DB adapter/query capture. Perl can be fed
through the same shape after DBI trace or MySQL general-log extraction.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


_WRITE_OPERATION_RE = re.compile(
    r"^\s*(insert\s+into|replace\s+into|update|delete\s+from)\s+`?([a-zA-Z0-9_]+)`?",
    re.IGNORECASE,
)
_SQL_STRING_RE = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"")
_SQL_NUMBER_RE = re.compile(r"(?<![a-zA-Z0-9_])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_])")
_SQL_LITERAL_RE = re.compile(
    r"(?P<string>'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")|"
    r"(?P<number>(?<![a-zA-Z0-9_])-?\d+(?:\.\d+)?(?![a-zA-Z0-9_]))"
)
_SQL_WHITESPACE_RE = re.compile(r"\s+")
_SQL_ON_DUPLICATE_RE = re.compile(r"\s+on\s+duplicate\s+key\s+update\b.*$", re.IGNORECASE)
_MYSQL_GENERAL_QUERY_RE = re.compile(r"\bQuery\t(?P<sql>.+)$")


@dataclass(frozen=True)
class TraceEvent:
    source: str
    index: int
    event_ref: str
    operation: str
    table: str
    fingerprint: str
    params: tuple[str, ...]

    def comparable(self) -> tuple[str, str, str, tuple[str, ...]]:
        return (self.operation, self.table.lower(), self.fingerprint, self.params)


@dataclass(frozen=True)
class TraceDivergence:
    position: int
    reason: str
    legacy: TraceEvent | None
    python: TraceEvent | None


@dataclass(frozen=True)
class TraceUnmatched:
    legacy_only: list[TraceEvent]
    python_only: list[TraceEvent]


@dataclass(frozen=True)
class TraceFilter:
    include_prefixes: tuple[str, ...] = ()
    include_tables: tuple[str, ...] = ()
    ignore_tables: tuple[str, ...] = ()
    param_contains: tuple[str, ...] = ()

    def accepts(self, event: TraceEvent) -> bool:
        table = event.table.lower()
        if self.include_prefixes and not any(
            table.startswith(prefix.lower()) for prefix in self.include_prefixes
        ):
            return False
        if self.include_tables and table not in {name.lower() for name in self.include_tables}:
            return False
        if self.param_contains:
            haystack = "\n".join((event.fingerprint, *event.params)).lower()
            if not all(term.lower() in haystack for term in self.param_contains):
                return False
        return table not in {name.lower() for name in self.ignore_tables}


def normalize_sql_event(
    *, source: str, index: int, payload: Mapping[str, object]
) -> TraceEvent | None:
    sql_value = payload.get("sql") or payload.get("query")
    if not isinstance(sql_value, str):
        return None

    match = _WRITE_OPERATION_RE.search(sql_value)
    if match is None:
        return None

    operation_token = match.group(1).lower()
    if operation_token.startswith("insert"):
        operation = "insert"
    elif operation_token.startswith("replace"):
        operation = "replace"
    elif operation_token == "update":
        operation = "update"
    else:
        operation = "delete"

    event_ref = payload.get("event_ref") or payload.get("line_ref") or ""
    params_value = payload.get("params")
    params = _normalize_params(params_value)
    if not params:
        params = _extract_literal_params(_insert_intent_sql(sql_value))

    return TraceEvent(
        source=source,
        index=index,
        event_ref=str(event_ref),
        operation=operation,
        table=match.group(2),
        fingerprint=_fingerprint_sql(_insert_intent_sql(sql_value)),
        params=params,
    )


def read_trace(
    path: Path, *, source: str, trace_filter: TraceFilter | None = None
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, record in enumerate(_iter_trace_records(handle), start=1):
            payload = _parse_trace_line(record)
            event = normalize_sql_event(source=source, index=index, payload=payload)
            if event is not None and (trace_filter is None or trace_filter.accepts(event)):
                events.append(event)
    return events


def first_divergence(
    legacy: Sequence[TraceEvent], python: Sequence[TraceEvent]
) -> TraceDivergence | None:
    max_common = min(len(legacy), len(python))
    for offset in range(max_common):
        legacy_event = legacy[offset]
        python_event = python[offset]
        if legacy_event.comparable() != python_event.comparable():
            return TraceDivergence(
                position=offset + 1,
                reason="write-intent mismatch",
                legacy=legacy_event,
                python=python_event,
            )

    if len(legacy) == len(python):
        return None

    position = max_common + 1
    return TraceDivergence(
        position=position,
        reason="trace length mismatch",
        legacy=legacy[max_common] if len(legacy) > max_common else None,
        python=python[max_common] if len(python) > max_common else None,
    )


def unmatched_writes(
    legacy: Sequence[TraceEvent], python: Sequence[TraceEvent]
) -> TraceUnmatched:
    legacy_counts = Counter(event.comparable() for event in legacy)
    python_counts = Counter(event.comparable() for event in python)

    legacy_remaining = legacy_counts - python_counts
    python_remaining = python_counts - legacy_counts

    legacy_only: list[TraceEvent] = []
    python_only: list[TraceEvent] = []
    for event in legacy:
        key = event.comparable()
        if legacy_remaining[key] > 0:
            legacy_only.append(event)
            legacy_remaining[key] -= 1
    for event in python:
        key = event.comparable()
        if python_remaining[key] > 0:
            python_only.append(event)
            python_remaining[key] -= 1

    return TraceUnmatched(legacy_only=legacy_only, python_only=python_only)


def format_divergence(divergence: TraceDivergence) -> str:
    lines = [f"First divergence at write #{divergence.position}: {divergence.reason}"]
    lines.extend(_format_side("legacy", divergence.legacy))
    lines.extend(_format_side("python", divergence.python))
    return "\n".join(lines)


def format_unmatched(unmatched: TraceUnmatched, *, max_examples: int = 5) -> str:
    lines = [
        "Unmatched write intents:",
        f"legacy-only: {len(unmatched.legacy_only)}",
        f"python-only: {len(unmatched.python_only)}",
    ]
    for label, events in (
        ("legacy-only", unmatched.legacy_only[:max_examples]),
        ("python-only", unmatched.python_only[:max_examples]),
    ):
        for event in events:
            lines.append(
                f"{label}: {event.operation.upper()} {event.table} "
                f"{event.fingerprint} params={list(event.params)}"
            )
    return "\n".join(lines)


def _format_side(label: str, event: TraceEvent | None) -> list[str]:
    if event is None:
        return [f"{label}: <missing>"]
    return [
        f"{label}: {event.operation.upper()} {event.table} at {event.event_ref or '<unknown>'}",
        f"{label} fingerprint: {event.fingerprint}",
        f"{label} params: {list(event.params)}",
    ]


def _fingerprint_sql(sql: str) -> str:
    normalized = sql.strip().lower().replace("`", "")
    normalized = _SQL_STRING_RE.sub("?", normalized)
    normalized = _SQL_NUMBER_RE.sub("?", normalized)
    normalized = normalized.replace("%s", "?")
    normalized = _SQL_WHITESPACE_RE.sub(" ", normalized)
    return normalized


def _insert_intent_sql(sql: str) -> str:
    return _SQL_ON_DUPLICATE_RE.sub("", sql.strip())


def _normalize_params(params: object) -> tuple[str, ...]:
    if params is None:
        return ()
    if isinstance(params, (str, bytes)):
        value = params.decode("utf-8", errors="replace") if isinstance(params, bytes) else params
        return (value,)
    if isinstance(params, Iterable):
        return tuple(_normalize_param(value) for value in params)
    return (_normalize_param(params),)


def _parse_trace_line(line: str) -> Mapping[str, object]:
    if line.startswith("{"):
        return json.loads(line)

    general_log_match = _MYSQL_GENERAL_QUERY_RE.search(line)
    if general_log_match is not None:
        return {"sql": general_log_match.group("sql")}

    return {"sql": line}


def _iter_trace_records(lines: Iterable[str]) -> Iterable[str]:
    buffered: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("{"):
            if buffered:
                yield " ".join(buffered)
                buffered = []
            yield stripped
            continue
        payload = _parse_general_log_sql(stripped)
        if _is_sql_record_start(payload):
            if buffered:
                yield " ".join(buffered)
            buffered = [payload]
        elif buffered:
            buffered.append(payload)
        else:
            yield payload
    if buffered:
        yield " ".join(buffered)


def _parse_general_log_sql(line: str) -> str:
    general_log_match = _MYSQL_GENERAL_QUERY_RE.search(line)
    if general_log_match is not None:
        return general_log_match.group("sql")
    return line


def _is_sql_record_start(sql: str) -> bool:
    return bool(
        re.match(
            r"^\s*(select|set|show|begin|commit|rollback|insert|replace|update|delete|truncate|create|drop|alter)\b",
            sql,
            re.IGNORECASE,
        )
    )


def _normalize_param(value: object) -> str:
    if value is None:
        return "<null>"
    return str(value)


def _extract_literal_params(sql: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _SQL_LITERAL_RE.finditer(sql):
        token = match.group(0)
        if match.group("string") is not None:
            values.append(_unquote_sql_string(token))
        else:
            values.append(token)
    return tuple(values)


def _unquote_sql_string(token: str) -> str:
    quote = token[0]
    value = token[1:-1]
    if quote == "'":
        return value.replace("''", "'")
    return value.replace('""', '"')


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare normalized DB write traces from legacy and Python replay runs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    diff_parser = subparsers.add_parser("diff", help="show the first write divergence")
    diff_parser.add_argument("--legacy", type=Path, required=True, help="legacy JSONL trace")
    diff_parser.add_argument("--python", type=Path, required=True, help="Python JSONL trace")
    diff_parser.add_argument(
        "--include-table-prefix",
        action="append",
        default=[],
        help="only compare tables with this prefix; can be repeated",
    )
    diff_parser.add_argument(
        "--table",
        action="append",
        default=[],
        help="only compare this exact table; can be repeated",
    )
    diff_parser.add_argument(
        "--ignore-table",
        action="append",
        default=[],
        help="ignore a table by exact name; can be repeated",
    )
    diff_parser.add_argument(
        "--param-contains",
        action="append",
        default=[],
        help="only compare writes whose fingerprint or params contain this text; can be repeated",
    )
    diff_parser.add_argument(
        "--unordered",
        action="store_true",
        help="compare traces as multisets of writes instead of sequence positions",
    )
    diff_parser.add_argument(
        "--max-examples",
        type=int,
        default=5,
        help="examples per side for unordered diff output",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "diff":
        trace_filter = TraceFilter(
            include_prefixes=tuple(args.include_table_prefix),
            include_tables=tuple(args.table),
            ignore_tables=tuple(args.ignore_table),
            param_contains=tuple(args.param_contains),
        )
        legacy = read_trace(args.legacy, source="legacy", trace_filter=trace_filter)
        python = read_trace(args.python, source="python", trace_filter=trace_filter)
        if args.unordered:
            unmatched = unmatched_writes(legacy, python)
            if not unmatched.legacy_only and not unmatched.python_only:
                print(f"No unordered write-intent differences found across {len(legacy)} write(s).")
                return 0
            print(format_unmatched(unmatched, max_examples=args.max_examples))
            return 1
        divergence = first_divergence(legacy, python)
        if divergence is None:
            print(f"No write-intent differences found across {len(legacy)} write(s).")
            return 0
        print(format_divergence(divergence))
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
