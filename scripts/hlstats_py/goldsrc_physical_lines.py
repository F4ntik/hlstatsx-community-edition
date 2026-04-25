"""Detect GoldSrc log physical line boundaries for stdin/replay merging."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import BinaryIO

_GOLDSRC_PHYSICAL_LINE_START_RE = re.compile(
    rb"^\s*L \d{2}/\d{2}/\d{4} - \d{2}:\d{2}:\d{2}:",
)


def line_starts_new_goldsrc_record(body: bytes) -> bool:
    """True when *body* begins a new ``L mm/dd/yyyy - hh:mm:ss:`` log record."""

    stripped = body.lstrip(b" \t")
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:]
    return bool(_GOLDSRC_PHYSICAL_LINE_START_RE.match(stripped))


def iter_merged_goldsrc_physical_lines(buffer: BinaryIO) -> Iterator[bytes]:
    """Yield complete log records, joining physical lines that continue a prior record."""

    pending: bytearray | None = None
    while True:
        raw_line = buffer.readline()
        if not raw_line:
            break
        if not raw_line.strip():
            continue
        body = raw_line.rstrip(b"\r\n")
        if line_starts_new_goldsrc_record(body):
            if pending is not None:
                yield bytes(pending)
            pending = bytearray(body)
        elif pending is None:
            yield body
        else:
            pending.extend(b"\n")
            pending.extend(body)
    if pending is not None:
        yield bytes(pending)
