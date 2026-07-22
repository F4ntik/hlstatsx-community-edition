"""Pure helpers for HLStats FTP import (testable without network)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hlstats_ftp_py.checkpoint import FtpCheckpoint, mtime_to_us


@dataclass(frozen=True, slots=True)
class LogFileEntry:
    """Remote ``*.log`` with modification time from ``MDTM``."""

    name: str
    mtime: float


def read_last_mtime(path: Path) -> float:
    """Read stored ``MDTM`` epoch from a ``hlstats-ftp-*.last`` file (Perl-compatible)."""

    if not path.is_file():
        return 0.0
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def write_last_mtime(path: Path, mtime: float) -> None:
    """Write epoch seconds as decimal text (Perl ``hlstats-ftp-*.last`` compatible)."""

    path.write_text(str(int(mtime)), encoding="ascii")


def without_newest_log(entries: list[LogFileEntry]) -> list[LogFileEntry]:
    """Drop the single newest file (same idea as Perl ``ls -t`` then chop last when times sort oldest-first)."""

    if len(entries) <= 1:
        return []
    by_time = sorted(entries, key=lambda e: (e.mtime, e.name))
    return by_time[:-1]


def entries_to_download(
    stable_entries: list[LogFileEntry],
    last_mtime: float,
    *,
    order_by: Literal["mtime", "name"] = "mtime",
) -> list[LogFileEntry]:
    """Return entries strictly newer than *last_mtime*, oldest first."""

    sort_key = (
        (lambda e: (e.name, e.mtime))
        if order_by == "name"
        else (lambda e: (e.mtime, e.name))
    )
    return sorted(
        [e for e in stable_entries if e.mtime > last_mtime],
        key=sort_key,
    )


def entries_after_checkpoint(
    stable_entries: list[LogFileEntry],
    checkpoint: FtpCheckpoint | None,
    *,
    order_by: Literal["mtime", "name"] = "mtime",
) -> list[LogFileEntry]:
    """Return logs after the durable cursor, oldest first.

    A bootstrapped legacy marker has no filename, so it deliberately keeps the
    historical strict-mtime cutoff.  Once a durable cursor has committed a
    file, the filename makes equal-mtime ordering deterministic.
    """

    if checkpoint is None:
        eligible = list(stable_entries)
    elif checkpoint.name is None:
        eligible = [entry for entry in stable_entries if mtime_to_us(entry.mtime) > checkpoint.mtime_us]
    else:
        cursor = (checkpoint.mtime_us, checkpoint.name)
        eligible = [
            entry
            for entry in stable_entries
            if (mtime_to_us(entry.mtime), entry.name) > cursor
        ]
    sort_key = (
        (lambda entry: (entry.name, entry.mtime))
        if order_by == "name"
        else (lambda entry: (mtime_to_us(entry.mtime), entry.name))
    )
    return sorted(eligible, key=sort_key)


def filter_log_names(names: list[str]) -> list[str]:
    """Keep only ``*.log`` basenames (case-insensitive)."""

    basenames = {Path(n).name for n in names if Path(n).name.lower().endswith(".log")}
    return sorted(basenames)
