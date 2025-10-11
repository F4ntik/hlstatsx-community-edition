"""Tests for the logging helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

    assert buffer.getvalue() == "[2024-03-02 12:34:56] [CONTROL] daemon started\n"


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


def test_log_converts_timestamp_to_requested_timezone() -> None:
    buffer = StringIO()
    tz = timezone(timedelta(hours=2))
    config = LoggerConfig(stream=buffer, timezone=tz, time_format="%H:%M")
    logger = ProxyLogger(config)
    fixed_time = datetime(2024, 3, 2, 12, 34, tzinfo=timezone.utc)

    logger.notice("converted", when=fixed_time)

    assert buffer.getvalue().startswith("14:34")


def test_logger_wrapped_levels_delegate_to_log() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer, level=LogLevel.NOTICE))
    logger.notice('notice message')
    logger.control('control message')
    logger.balance('balance message')
    logger.daemon('daemon message')
    logger.e403('error message')
    output = buffer.getvalue().splitlines()
    assert any('[NOTICE]' in line for line in output)
    assert any('[CONTROL]' in line for line in output)
    assert any('[BALANCE]' in line for line in output)
    assert any('[DAEMON]' in line for line in output)
    assert output[-1].endswith('[E403] error message')

def test_logger_normalises_naive_timestamp_without_timezone() -> None:
    buffer = StringIO()
    logger = ProxyLogger(LoggerConfig(stream=buffer, timezone=None, level=LogLevel.BALANCE))
    naive = datetime(2024, 5, 1, 12, 30, 45)
    logger.balance('naive timestamp', when=naive)
    assert '[BALANCE] naive timestamp' in buffer.getvalue()
