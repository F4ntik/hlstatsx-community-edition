"""Lightweight logging helpers for the proxy daemon."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import IntEnum
from typing import TextIO


class LogLevel(IntEnum):
    """Log severity levels used by the legacy Perl daemon."""

    NOTICE = 20
    CONTROL = 25
    BALANCE = 30
    DAEMON = 35
    E403 = 40

    @classmethod
    def from_name(cls, name: str) -> LogLevel:
        """Return the level matching *name* regardless of case."""

        normalised = name.strip().upper()
        try:
            return cls[normalised]
        except KeyError as exc:  # pragma: no cover - defensive guard
            valid = ", ".join(member.name for member in cls)
            raise ValueError(f"Unknown log level '{name}'. Expected one of: {valid}") from exc


@dataclass(slots=True)
class LoggerConfig:
    """Configuration for :class:`ProxyLogger`."""

    level: LogLevel = LogLevel.NOTICE
    time_format: str = "[%Y-%m-%d %H:%M:%S]"
    timezone: tzinfo | None = None
    stream: TextIO | None = None


class ProxyLogger:
    """Formatter and sink for daemon log messages."""

    __slots__ = ("_config", "_stream")

    def __init__(self, config: LoggerConfig | None = None) -> None:
        self._config = config or LoggerConfig()
        self._stream: TextIO = self._config.stream or self._default_stream

    @property
    def level(self) -> LogLevel:
        """Return the currently configured log level."""

        return self._config.level

    def log(self, level: LogLevel, message: str, *, when: datetime | None = None) -> None:
        """Emit *message* if *level* meets the configured threshold."""

        if level < self._config.level:
            return

        timestamp = self._normalise_timestamp(when)
        formatted_time = timestamp.strftime(self._config.time_format)
        self._stream.write(f"{formatted_time} [{level.name}] {message}\n")
        self._stream.flush()

    def notice(self, message: str, *, when: datetime | None = None) -> None:
        self.log(LogLevel.NOTICE, message, when=when)

    def control(self, message: str, *, when: datetime | None = None) -> None:
        self.log(LogLevel.CONTROL, message, when=when)

    def balance(self, message: str, *, when: datetime | None = None) -> None:
        self.log(LogLevel.BALANCE, message, when=when)

    def daemon(self, message: str, *, when: datetime | None = None) -> None:
        self.log(LogLevel.DAEMON, message, when=when)

    def e403(self, message: str, *, when: datetime | None = None) -> None:
        self.log(LogLevel.E403, message, when=when)

    @property
    def _default_stream(self) -> TextIO:
        from sys import stdout

        return stdout

    def _normalise_timestamp(self, when: datetime | None) -> datetime:
        tz = self._config.timezone
        if when is None:
            if tz is None:
                return datetime.now().astimezone()
            return datetime.now(tz)

        if tz is None:
            return when.astimezone() if when.tzinfo is not None else when

        if when.tzinfo is None:
            return when.replace(tzinfo=tz)
        return when.astimezone(tz)


def level_from_debug(debug_enabled: bool, configured_level: int) -> LogLevel:
    """Translate config debug levels to :class:`LogLevel` thresholds."""

    if debug_enabled:
        return LogLevel.NOTICE

    if configured_level <= 0:
        return LogLevel.BALANCE
    if configured_level == 1:
        return LogLevel.CONTROL
    if configured_level >= 2:
        return LogLevel.NOTICE
    return LogLevel.BALANCE
