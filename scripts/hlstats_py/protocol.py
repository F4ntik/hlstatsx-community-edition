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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import re
from types import MappingProxyType
from typing import List, Literal, Mapping, MutableMapping, Optional

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
_KILL_WEAPON_RE = re.compile(r'^"(?P<weapon>[^"]*)"(?P<properties>.*)$')
_TRIGGER_RE = re.compile(
    r'^"(?P<action>[^"]+)"(?: against (?P<target_token>"[^"]+"))?(?P<properties>.*)$'
)
_CHAT_RE = re.compile(r'^"(?P<message>.*)"(?:\s+\(dead\))?$')
_TEAM_RE = re.compile(r'^"(?P<team>[^"]+)"(?:\s+\(.*\))?$')
_NAME_CHANGE_RE = re.compile(r'^"(?P<new>[^"]+)"$')
_ADDRESS_RE = re.compile(r'address "(?P<address>[^"]+)"')
_SUICIDE_WEAPON_RE = re.compile(r'^"(?P<weapon>[^"]+)"(?P<properties>.*)$')
_WORLD_TRIGGER_RE = re.compile(r'^World triggered "(?P<action>[^"]+)"(?P<properties>.*)$')
_TEAM_TRIGGER_RE = re.compile(
    r'^Team "(?P<team>[^"]+)" triggered "(?P<action>[^"]+)"(?P<properties>.*)$'
)
_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_MAX_POSITION_TOKEN_LENGTH = 64
_INLINE_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+|nan|inf(?:inity)?)"
_INLINE_SETPOSE_RE = re.compile(
    rf"\bsetpos_exact\b\s*(?:[:=]\s*)?"
    rf"(?P<vector>\[[^\]]*\]|\([^\)]*\)|[^()[\]]*)",
    re.IGNORECASE,
)
_INLINE_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")
_INLINE_NUMBER_RE = re.compile(rf"^{_INLINE_NUMBER}$", re.IGNORECASE)
_MEDIUMINT_MIN = -(1 << 23)
_MEDIUMINT_MAX = (1 << 23) - 1

Position = tuple[int, int, int]


def _is_exact_entry_remainder(remainder: str) -> bool:
    return remainder.strip() == "entered the game"


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

    separator_index = datagram.find(_PROXY_SEPARATOR, len(_PROXY_PREFIX))
    if separator_index < 0:
        raise ValueError("Malformed proxy datagram: missing separator")
    prefix = datagram[:separator_index]
    payload = datagram[separator_index + len(_PROXY_SEPARATOR) :]

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


ParserBackend = Literal["python", "native"]


def parse_log_event(
    payload: str,
    *,
    backend: ParserBackend = "python",
    server_address: str | None = None,
) -> LogEvent:
    """Parse a log event payload from the proxy daemon."""
    if backend == "native":
        return _parse_log_event_native(payload, server_address=server_address)
    return _parse_log_event_python(payload, server_address=server_address)


def _parse_log_event_python(payload: str, *, server_address: str | None = None) -> LogEvent:
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

    actor, remainder = _consume_player(body, server_address=server_address)
    if actor is None:
        # Some events do not include a quoted actor (e.g. "Server cvar").
        return _parse_generic_event(body, timestamp, payload)

    remainder = remainder.lstrip()

    if remainder.startswith("killed "):
        return _parse_kill_event(body, actor, remainder[7:], timestamp, payload, server_address=server_address)
    if remainder.startswith("triggered "):
        return _parse_trigger_event(body, actor, remainder[10:], timestamp, payload, server_address=server_address)
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
    if _is_exact_entry_remainder(remainder):
        return _parse_entry_event(body, actor, remainder[16:], timestamp, payload)
    if remainder.startswith("disconnected"):
        return _parse_disconnect_event(body, actor, remainder[12:], timestamp, payload)
    if remainder.startswith("committed suicide with "):
        offset = len("committed suicide with ")
        return _parse_suicide_event(body, actor, remainder[offset:], timestamp, payload)

    return _parse_generic_event(body, timestamp, payload, actor=actor)


def _parse_log_event_native(payload: str, *, server_address: str | None = None) -> LogEvent:
    stripped = payload.strip()
    marker = stripped.find("L ")
    if marker < 0:
        raise ValueError(f"Payload does not contain a log line: {payload!r}")
    line = stripped[marker:]
    if len(line) < 25:
        raise ValueError(f"Payload does not contain a full log header: {payload!r}")

    try:
        month = int(line[2:4])
        day = int(line[5:7])
        year = int(line[8:12])
        hour = int(line[15:17])
        minute = int(line[18:20])
        second = int(line[21:23])
    except ValueError as exc:
        raise ValueError(f"Payload does not contain a log line: {payload!r}") from exc
    if line[12:15] != " - " or line[23] != ":":
        raise ValueError(f"Payload does not contain a log line: {payload!r}")
    body = line[24:].lstrip()
    timestamp = datetime(year, month, day, hour, minute, second)

    if body.startswith("World "):
        return _parse_world_event(body, timestamp, payload)
    if body.startswith("Team "):
        return _parse_team_trigger_event(body, timestamp, payload)

    actor, remainder = _consume_player(body, server_address=server_address)
    if actor is None:
        return _parse_generic_event(body, timestamp, payload)
    remainder = remainder.lstrip()

    if remainder.startswith("killed "):
        return _parse_kill_event(body, actor, remainder[7:], timestamp, payload, server_address=server_address)
    if remainder.startswith("triggered "):
        return _parse_trigger_event(body, actor, remainder[10:], timestamp, payload, server_address=server_address)
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
    if _is_exact_entry_remainder(remainder):
        return _parse_entry_event(body, actor, remainder[16:], timestamp, payload)
    if remainder.startswith("disconnected"):
        return _parse_disconnect_event(body, actor, remainder[12:], timestamp, payload)
    if remainder.startswith("committed suicide with "):
        offset = len("committed suicide with ")
        return _parse_suicide_event(body, actor, remainder[offset:], timestamp, payload)

    return _parse_generic_event(body, timestamp, payload, actor=actor)


def _consume_player(body: str, *, server_address: str | None = None) -> tuple[PlayerDescriptor | None, str]:
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
        unique_id=_stabilize_bot_unique_id(
            unique_id,
            player_name=name,
            user_id=user_id,
            server_address=server_address,
        ),
        team=team,
        additional_tokens=tuple(extras),
    )
    return descriptor, remainder


_IPV4_WITH_PORT_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}:\d+$")


def _normalize_unique_id(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("STEAM_0:"):
        return normalized[len("STEAM_0:") :]
    return normalized


def _stabilize_bot_unique_id(
    unique_id: Optional[str],
    *,
    player_name: str,
    user_id: Optional[int],
    server_address: str | None = None,
) -> Optional[str]:
    if unique_id != "BOT":
        return unique_id
    del user_id
    basis = f"{player_name}{server_address or ''}"
    return f"BOT:{hashlib.md5(basis.encode('utf-8', errors='replace')).hexdigest()}"


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
    properties: MutableMapping[str, str | bool] = {}
    for match in _PROPERTIES_RE.finditer(text):
        key = match.group("key")
        if match.group("quoted") is not None:
            value: str | bool = match.group("quoted")
        elif match.group("bare") is not None:
            value = match.group("bare").strip()
        else:
            value = True
        # Legacy getProperties semantics are destructive for duplicate keys:
        # the last occurrence wins.
        properties[key] = value

    return MappingProxyType(dict(properties))


def _parse_position_triplet(value: object) -> Position | None:
    """Parse a strict integer XYZ triplet within MySQL signed MEDIUMINT."""

    if isinstance(value, str):
        parts: list[object] = value.split()
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return None
    if len(parts) != 3:
        return None

    coordinates: list[int] = []
    for part in parts:
        if isinstance(part, bool):
            return None
        if isinstance(part, int):
            coordinate = part
        elif isinstance(part, str):
            token = part.strip()
            if len(token) > _MAX_POSITION_TOKEN_LENGTH or _INTEGER_RE.fullmatch(token) is None:
                return None
            try:
                coordinate = int(token)
            except ValueError:
                return None
        else:
            return None
        if not _MEDIUMINT_MIN <= coordinate <= _MEDIUMINT_MAX:
            return None
        coordinates.append(coordinate)
    return coordinates[0], coordinates[1], coordinates[2]


def _parse_inline_coordinate(value: str, *, allow_fraction: bool) -> int | None:
    if len(value.strip()) > _MAX_POSITION_TOKEN_LENGTH:
        return None
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    if not allow_fraction and decimal_value != decimal_value.to_integral_value():
        return None
    rounded = decimal_value.to_integral_value(rounding=ROUND_HALF_UP)
    try:
        coordinate = int(rounded)
    except ValueError:
        return None
    if not _MEDIUMINT_MIN <= coordinate <= _MEDIUMINT_MAX:
        return None
    return coordinate


def _parse_inline_vector(value: str, *, allow_fraction: bool) -> Position | None:
    """Parse one fully delimited inline XYZ vector."""

    text = value.strip()
    if len(text) > _MAX_POSITION_TOKEN_LENGTH * 3:
        return None
    while len(text) >= 2 and ((text[0], text[-1]) in {
        ("[", "]"),
        ("(", ")"),
        ('"', '"'),
        ("'", "'"),
    }):
        text = text[1:-1].strip()
    parts = [part for part in re.split(r"[\s,]+", text) if part]
    if len(parts) != 3 or any(_INLINE_NUMBER_RE.fullmatch(part) is None for part in parts):
        return None
    coordinates = [
        _parse_inline_coordinate(part, allow_fraction=allow_fraction) for part in parts
    ]
    if any(coordinate is None for coordinate in coordinates):
        return None
    return coordinates[0], coordinates[1], coordinates[2]  # type: ignore[return-value]


_InlinePositionSlot = tuple[Position | None, str | None]


def _extract_inline_kill_position_slots(metadata: str) -> tuple[_InlinePositionSlot, _InlinePositionSlot]:
    """Extract inline attacker/victim slots, retaining invalid entries."""

    matches: list[tuple[int, int, Position | None, str]] = []
    for match in _INLINE_SETPOSE_RE.finditer(metadata):
        raw = match.group("vector").strip()
        matches.append(
            (match.start(), match.end(), _parse_inline_vector(raw, allow_fraction=True), raw)
        )
    for match in _INLINE_BRACKET_RE.finditer(metadata):
        if any(start < match.end() and match.start() < end for start, end, _position, _raw in matches):
            continue
        raw = match.group(0).strip()
        matches.append(
            (match.start(), match.end(), _parse_inline_vector(raw, allow_fraction=False), raw)
        )
    slots = [
        (position, raw)
        for _start, _end, position, raw in sorted(matches, key=lambda item: item[0])
    ][:2]
    slots.extend([(None, None)] * (2 - len(slots)))
    return slots[0], slots[1]


def _extract_inline_kill_positions(metadata: str) -> tuple[Position | None, Position | None]:
    """Extract supported inline attacker/victim coordinates in source order."""

    attacker, victim = _extract_inline_kill_position_slots(metadata)
    return attacker[0], victim[0]


def _format_position(position: Position) -> str:
    return f"{position[0]} {position[1]} {position[2]}"


def _normalize_position_properties(
    properties: Mapping[str, tuple[str, ...] | str | bool],
    *,
    metadata: str,
) -> Mapping[str, tuple[str, ...] | str | bool]:
    """Canonicalize supported position properties while retaining invalid input."""

    normalized: dict[str, tuple[str, ...] | str | bool] = dict(properties)
    inline_attacker, inline_victim = _extract_inline_kill_position_slots(metadata)
    for canonical, alias, inline in (
        ("attacker_position", "killerpos", inline_attacker),
        ("victim_position", "victimpos", inline_victim),
    ):
        if canonical in normalized:
            position = _parse_position_triplet(normalized[canonical])
            if position is not None:
                normalized[canonical] = _format_position(position)
            continue
        if alias in normalized:
            position = _parse_position_triplet(normalized[alias])
            if position is not None:
                normalized[alias] = _format_position(position)
                normalized[canonical] = _format_position(position)
            continue
        position, raw = inline
        if raw is not None:
            normalized[canonical] = _format_position(position) if position is not None else raw
    return MappingProxyType(normalized)


def _parse_kill_event(
    body: str,
    actor: PlayerDescriptor,
    remainder: str,
    timestamp: datetime,
    raw: str,
    *,
    server_address: str | None = None,
) -> LogEvent:
    victim_desc, after_victim = _consume_player(remainder.lstrip(), server_address=server_address)
    if victim_desc is None or not after_victim.lstrip().startswith("with "):
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    after_victim = after_victim.lstrip()[5:]

    weapon_match = _KILL_WEAPON_RE.match(after_victim.strip())
    if not weapon_match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    weapon = weapon_match.group("weapon")
    properties = _normalize_position_properties(
        _parse_properties(weapon_match.group("properties")),
        metadata=weapon_match.group("properties"),
    )

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
    *,
    server_address: str | None = None,
) -> LogEvent:
    match = _TRIGGER_RE.match(remainder.strip())
    if not match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    action = match.group("action")
    properties = _parse_properties(match.group("properties"))
    target: Optional[PlayerDescriptor] = None
    target_token = match.group("target_token")
    if target_token:
        target, _ = _consume_player(
            target_token + match.group("properties"),
            server_address=server_address,
        )

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
    match = _CHAT_RE.match(remainder.strip())
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
    match = _TEAM_RE.match(remainder.strip())
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
    match = _NAME_CHANGE_RE.match(remainder.strip())
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
    address_match = _ADDRESS_RE.search(remainder)
    address: Optional[str] = None
    if address_match:
        raw_address = address_match.group("address")
        if _IPV4_WITH_PORT_RE.match(raw_address):
            address = raw_address.split(":", 1)[0]
        else:
            address = raw_address
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
    weapon_match = _SUICIDE_WEAPON_RE.match(remainder.strip())
    if not weapon_match:
        return _parse_generic_event(body, timestamp, raw, actor=actor)

    properties = _normalize_position_properties(
        _parse_properties(weapon_match.group("properties")),
        metadata=weapon_match.group("properties"),
    )
    return LogEvent(
        event_type=LogEventType.KILL,
        timestamp=timestamp,
        raw=raw,
        actor=actor,
        weapon=weapon_match.group("weapon"),
        properties=properties,
    )


def _parse_world_event(body: str, timestamp: datetime, raw: str) -> LogEvent:
    match = _WORLD_TRIGGER_RE.match(body)
    if not match:
        return _parse_generic_event(body, timestamp, raw)

    properties = _normalize_position_properties(
        _parse_properties(match.group("properties")),
        metadata=match.group("properties"),
    )
    return LogEvent(
        event_type=LogEventType.WORLD_TRIGGER,
        timestamp=timestamp,
        raw=raw,
        action=match.group("action"),
        properties=properties,
    )


def _parse_team_trigger_event(body: str, timestamp: datetime, raw: str) -> LogEvent:
    match = _TEAM_TRIGGER_RE.match(body)
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
