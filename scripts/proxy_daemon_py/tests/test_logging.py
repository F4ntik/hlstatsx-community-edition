"""Tests for the logging helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

from proxy_daemon_py.log import (
    LoggerConfig,
    LogLevel,
    ProxyLogger,
    level_from_debug,
)


def test_log_includes_timestamp_level_and_message() -> None:
    buffer = StringIO()
    config = LoggerConfig(stream=buffer, timezone=timezone.utc)
    logger = ProxyLogger(config)
    fixed_time = datetime(2024, 3, 2, 12, 34, 56, tzinfo=timezone.utc)

    logger.log(LogLevel.CONTROL, "daemon started", when=fixed_time)

    assert buffer.getvalue() == "2024-03-02 12:34:56 [CONTROL] daemon started\n"


def test_log_respects_threshold() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(level=LogLevel.E403, stream=buffer))

    logger.balance("will be skipped")
    logger.e403("permission denied")

    assert buffer.getvalue().endswith("[E403] permission denied\n")


def test_level_from_debug_prefers_cli_flag() -> None:
    assert level_from_debug(True, 0) is LogLevel.NOTICE
    assert level_from_debug(False, 0) is LogLevel.BALANCE
    assert level_from_debug(False, 1) is LogLevel.CONTROL
    assert level_from_debug(False, 3) is LogLevel.NOTICE
