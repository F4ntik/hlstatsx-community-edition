"""Parsers and dataclasses for HLstats log and control protocol.

This module documents the payloads that arrive from the proxy daemon and
exposes helpers to parse them into structured Python objects.  The
implementation focuses on the canonical message classes required by the
existing Perl implementation and covers the most common sequences that drive
statistics updates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
import re
from types import MappingProxyType
from typing import List, Mapping, MutableMapping, Optional

_PROXY_PREFIX = "PROXY Key="
_PROXY_SEPARATOR = "PROXY "

_LOG_LINE_RE = re.compile(
    r"^(?:.*?)?L (?P<month>\d{2})/(?P<day>\d{2})/(?P<year>\d{4}) - "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}):\s*(?P<body>.*)$",
    re.DOTALL,
)

_PROPERTIES_RE = re.compile(
    r"\((?P<key>[\w-]+)(?: (?:(?:\"(?P<quoted>[^\"]*)\")|(?P<bare>[^()]+)))?\)"
)

_PLAYER_TOKEN_RE = re.compile(
    r'^"(?P<name>(?:[^"\\]|\\.)*?)(?P<meta>(?:<[^>]*>)*)"$'
)


class ControlCommandType(Enum):
    """Enumerates supported control commands sent via the proxy channel."""

    HEARTBEAT = auto()
    SERVERLIST = auto()
    RELOAD = auto()
    KILL = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class ControlCommand:
    """Representation of a control command initiated from the frontend."""

    command_type: ControlCommandType
    raw: str


@dataclass(frozen=True)
class ProxyEnvelope:
    """Metadata extracted from a proxied datagram."""

    proxy_key: str
    server_address: str | None
    payload: str


class LogEventType(Enum):
    """High level categories for parsed log events."""

    KILL = auto()
    TRIGGER = auto()
    CHAT = auto()
    TEAM_CHANGE = auto()
    CONNECT = auto()
    ENTRY = auto()
    DISCONNECT = auto()
    NAME_CHANGE = auto()
    CVAR = auto()
    TEAM_TRIGGER = auto()
    WORLD_TRIGGER = auto()
    GENERIC = auto()


@dataclass(frozen=True)
class PlayerDescriptor:
    """Normalized representation of a player descriptor taken from the logs."""

    name: str
    user_id: Optional[int]
    unique_id: Optional[str]
    team: Optional[str]
    additional_tokens: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LogEvent:
    """Structured description of a log entry."""

    event_type: LogEventType
    timestamp: datetime
    raw: str
    actor: Optional[PlayerDescriptor] = None
    target: Optional[PlayerDescriptor] = None
    action: Optional[str] = None
    weapon: Optional[str] = None
    team: Optional[str] = None
    message: Optional[str] = None
    properties: Mapping[str, tuple[str, ...] | str | bool] = field(
        default_factory=lambda: MappingProxyType({})
    )


def parse_proxy_envelope(datagram: str) -> ProxyEnvelope:
    """Parse a UDP datagram received from the proxy daemon.

    Parameters
    ----------
    datagram:
        Raw text as sent by :mod:`proxy-daemon.pl` (or the Python port).

    Returns
    -------
    :class:`ProxyEnvelope`
        Parsed envelope information with optional server address and the
        payload to be interpreted by :func:`parse_log_event` or
        :func:`parse_control_command`.

    Raises
    ------
    ValueError
        If the datagram does not conform to the proxy framing rules.
    """

    if not datagram.startswith(_PROXY_PREFIX):
        raise ValueError("Datagram is not a proxied payload: missing prefix")

    try:
        prefix, payload = datagram.rsplit(_PROXY_SEPARATOR, 1)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("Malformed proxy datagram: missing separator") from exc

    prefix = prefix[len(_PROXY_PREFIX) :]
    if " " in prefix:
        proxy_key, server_address = prefix.split(" ", 1)
        server_address = server_address or None
    else:
        proxy_key = prefix
        server_address = None

    return ProxyEnvelope(proxy_key=proxy_key, server_address=server_address, payload=payload)


def parse_control_command(payload: str) -> ControlCommand | None:
    """Attempt to parse a control command payload."""

    if not payload.startswith("C;"):
        return None

    command = payload[2:].strip(";")
    normalized = command.upper()
    if normalized == "HEARTBEAT":
        command_type = ControlCommandType.HEARTBEAT
    elif normalized == "SERVERLIST":
        command_type = ControlCommandType.SERVERLIST
    elif normalized == "RELOAD":
        command_type = ControlCommandType.RELOAD
    elif normalized == "KILL":
        command_type = ControlCommandType.KILL
    else:
        command_type = ControlCommandType.UNKNOWN

    return ControlCommand(command_type=command_type, raw=command)


def parse_log_event(payload: str) -> LogEvent:
    """Parse a log event payload from the proxy daemon."""

    match = _LOG_LINE_RE.match(payload.strip())
    if not match:
        raise ValueError(f"Payload does not contain a log line: {payload!r}")

    month = int(match.group("month"))
    day = int(match.group("day"))
    year = int(match.group("year"))
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))
    body = match.group("body").strip()

    timestamp = datetime(year, month, day, hour, minute, second)

    if body.startswith("World "):
        return _parse_world_event(body, timestamp, payload)
    if body.startswith("Team "):
        return _parse_team_trigger_event(body, timestamp, payload)

    actor, remainder = _consume_player(body)
    if actor is None:
        # Some events do not include a quoted actor (e.g. "Server cvar").
        return _parse_generic_event(body, timestamp, payload)

    remainder = remainder.lstrip()

    if remainder.startswith("killed "):
        return _parse_kill_event(body, actor, remainder[7:], timestamp, payload)
    if remainder.startswith("triggered "):
        return _parse_trigger_event(body, actor, remainder[10:], timestamp, payload)
    if remainder.startswith("say "):
        return _parse_chat_event(body, actor, remainder[4:], False, timestamp, payload)
    if remainder.startswith("say_team "):
        return _parse_chat_event(body, actor, remainder[9:], True, timestamp, payload)
    if remainder.startswith("joined team "):
        return _parse_team_event(body, actor, remainder[12:], timestamp, payload)
    if remainder.startswith("changed name to "):
        return _parse_name_change_event(body, actor, remainder[16:], timestamp, payload)
    if remainder.startswith("connected"):
        return _parse_connect_event(body, actor, remainder[9:], timestamp, payload)
    if remainder.startswith("entered the game"):
        return _parse_entry_event(body, actor, remainder[16:], timestamp, payload)
    if remainder.startswith("disconnected"):
        return _parse_disconnect_event(body, actor, remainder[12:], timestamp, payload)
    if remainder.startswith("committed suicide with "):
        offset = len("committed suicide with ")
        return _parse_suicide_event(body, actor, remainder[offset:], timestamp, payload)

    return _parse_generic_event(body, timestamp, payload, actor=actor)


def _consume_player(body: str) -> tuple[PlayerDescriptor | None, str]:
    body = body.lstrip()
    if not body.startswith('"'):
        return None, body

    # Extract the player token respecting nested <...> metadata.
    closing = _find_closing_quote(body)
    if closing is None:
        return None, body

    player_token = body[: closing + 1]
    remainder = body[closing + 1 :]

    match = _PLAYER_TOKEN_RE.match(player_token)
    if not match:
        return None, body

    name = match.group("name").replace("\\\"", "\"")
    metadata = match.group("meta")
    tokens: List[str] = []
    if metadata:
        tokens = [token[:-1] for token in metadata.split("<") if token]

    user_id: Optional[int] = None
    unique_id: Optional[str] = None
    team: Optional[str] = None
    extras: List[str] = []

    if tokens:
        potential_user = tokens[0]
        try:
            user_id = int(potential_user)
        except ValueError:
            extras.append(potential_user)
        else:
            tokens = tokens[1:]
    if tokens:
        unique_id = _normalize_unique_id(tokens[0])
        tokens = tokens[1:]
    if tokens:
        team = tokens[0]
        tokens = tokens[1:]
    extras.extend(tokens)

    descriptor = PlayerDescriptor(
        name=name,
        user_id=user_id,
        unique_id=unique_id,
        team=team,
        additional_tokens=tuple(extras),
    )
    return descriptor, remainder


def _normalize_unique_id(value: str) -> str:
    if value.startswith("STEAM_0:"):
        return value[len("STEAM_0:") :]
    return value


def _find_closing_quote(text: str) -> Optional[int]:
    escaped = False
    for index, char in enumerate(text[1:], start=1):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            return index
    return None


def _parse_properties(text: str) -> Mapping[str, tuple[str, ...] | str | bool]:
    properties: MutableMapping[str, List[str] | str | bool] = {}
    for match in _PROPERTIES_RE.finditer(text):
        key = match.group("key")
        if match.group("quoted") is not None:
            value: str | bool = match.group("quoted")
        elif match.group("bare") is not None:
            value = match.group("bare").strip()
        else:
            value = True

        existing = properties.get(key)
        if existing is None:
            properties[key] = value
        else:
            if isinstance(existing, list):
                existing.append(value if isinstance(value, str) else str(value))
            elif isinstance(existing, str):
                properties[key] = [existing, value if isinstance(value, str) else str(value)]
            else:
                properties[key] = [str(existing), value if isinstance(value, str) else str(value)]

    def _freeze(value: List[str] | str | bool) -> tuple[str, ...] | str | bool:
        if isinstance(value, list):
            return tuple(value)
        return value

    frozen = {key: _freeze(value) for key, value in properties.items()}
    return MappingProxyType(frozen)


def _parse_kill_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    victim_desc, after_victim = _consume_player(remainder.lstrip())
    if victim_desc is None or not after_victim.lstrip().startswith("with "):
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    after_victim = after_victim.lstrip()[5:]

    weapon_match = re.match(r'^"(?P<weapon>[^"]*)"(?P<properties>.*)$', after_victim.strip())
    if not weapon_match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    weapon = weapon_match.group("weapon")
    properties = _parse_properties(weapon_match.group("properties"))

    return LogEvent(
        event_type=LogEventType.KILL,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        target=victim_desc,
        weapon=weapon,
        properties=properties,
    )


def _parse_trigger_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    match = re.match(
        r'^"(?P<action>[^"]+)"(?: against (?P<target_token>"[^"]+"))?(?P<properties>.*)$',
        remainder.strip(),
    )
    if not match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    action = match.group("action")
    properties = _parse_properties(match.group("properties"))
    target: Optional[PlayerDescriptor] = None
    target_token = match.group("target_token")
    if target_token:
        target, _ = _consume_player(target_token + match.group("properties"))

    return LogEvent(
        event_type=LogEventType.TRIGGER,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        target=target,
        action=action,
        properties=properties,
    )


def _parse_chat_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    is_team: bool,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    match = re.match(r'^"(?P<message>.*)"(?:\s+\(dead\))?$', remainder.strip())
    if not match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    message = match.group("message")
    properties = MappingProxyType({"team_only": is_team}) if is_team else MappingProxyType({})

    return LogEvent(
        event_type=LogEventType.CHAT,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        message=message,
        properties=properties,
    )


def _parse_team_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    match = re.match(r'^"(?P<team>[^"]+)"(?:\s+\(.*\))?$', remainder.strip())
    if not match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    team = match.group("team")
    return LogEvent(
        event_type=LogEventType.TEAM_CHANGE,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        team=team,
    )


def _parse_name_change_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    match = re.match(r'^"(?P<new>[^"]+)"$', remainder.strip())
    if not match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    return LogEvent(
        event_type=LogEventType.NAME_CHANGE,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        message=match.group("new"),
    )


def _parse_connect_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    properties_dict: dict[str, tuple[str, ...] | str | bool] = {}
    address_match = re.search(r'address "(?P<address>[^"]+)"', remainder)
    address: Optional[str] = None
    if address_match:
        address = address_match.group("address").split(":", 1)[0]
        properties_dict["address"] = address

    paren_properties = dict(_parse_properties(remainder))
    if paren_properties:
        properties_dict.update(paren_properties)

    properties = MappingProxyType(properties_dict) if properties_dict else MappingProxyType({})

    return LogEvent(
        event_type=LogEventType.CONNECT,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        properties=properties,
        message=address,
    )


def _parse_entry_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    return LogEvent(
        event_type=LogEventType.ENTRY,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        message="entered the game",
    )


def _parse_disconnect_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    properties = _parse_properties(remainder)
    reason = properties.get("reason")
    return LogEvent(
        event_type=LogEventType.DISCONNECT,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        properties=properties,
        message=reason if isinstance(reason, str) else None,
    )


def _parse_suicide_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
) -> LogEvent:
    weapon_match = re.match(r'^"(?P<weapon>[^"]+)"(?P<properties>.*)$', remainder.strip())
    if not weapon_match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    properties = _parse_properties(weapon_match.group("properties"))
    return LogEvent(
        event_type=LogEventType.KILL,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        weapon=weapon_match.group("weapon"),
        properties=properties,
    )


def _parse_world_event(body: str, timestamp: datetime, raw: str) -> LogEvent:
    match = re.match(r'^World triggered "(?P<action>[^"]+)"(?P<properties>.*)$', body)
    if not match:
        return _parse_generic_event(body, timestamp, raw)

    properties = _parse_properties(match.group("properties"))
    return LogEvent(
        event_type=LogEventType.WORLD_TRIGGER,
        timestamp=timestamp,
        raw=raw,
        action=match.group("action"),
        properties=properties,
    )


def _parse_team_trigger_event(body: str, timestamp: datetime, raw: str) -> LogEvent:
    match = re.match(r'^Team "(?P<team>[^"]+)" triggered "(?P<action>[^"]+)"(?P<properties>.*)$', body)
    if not match:
        return _parse_generic_event(body, timestamp, raw)

    properties_dict = dict(_parse_properties(match.group("properties")))
    properties_dict["team"] = match.group("team")
    return LogEvent(
        event_type=LogEventType.TEAM_TRIGGER,
        timestamp=timestamp,
        raw=raw,
        action=match.group("action"),
        team=match.group("team"),
        properties=MappingProxyType(properties_dict),
    )


def _parse_generic_event(
    body: str,
    timestamp: datetime,
    raw: str,
    *,
    actor: Optional[PlayerDescriptor] = None,
) -> LogEvent:
    return LogEvent(
        event_type=LogEventType.GENERIC,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        message=body,
    )
