"""Event processing primitives for the Python hlstats migration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Protocol, Sequence

from ..protocol import LogEvent, LogEventType, PlayerDescriptor


class EventCategory(Enum):
    """High level buckets that mirror the MySQL event tables."""

    FRAG = "frags"
    ACTION = "actions"
    CHAT = "chat"
    TEAM = "team"
    CONNECTION = "connection"
    WORLD = "world"
    GENERIC = "generic"


@dataclass(frozen=True)
class EventUpdate:
    """Result of translating a :class:`~hlstats_py.protocol.LogEvent`."""

    category: EventCategory
    event_code: str
    actor: Optional[PlayerDescriptor]
    target: Optional[PlayerDescriptor]
    timestamp: datetime
    attributes: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    message_key: Optional[str] = None
    message: Optional[str] = None


class EventProcessingError(RuntimeError):
    """Raised when a log entry cannot be mapped to a structured event."""

    def __init__(self, event: LogEvent) -> None:
        super().__init__(f"Unhandled log event: {event.raw}")
        self.event = event


class EventHandler(Protocol):
    """Interface implemented by concrete log event handlers."""

    supported_types: Sequence[LogEventType]

    def handle(self, event: LogEvent, context: "EventContext") -> Optional[EventUpdate]:
        """Attempt to translate *event* into an :class:`EventUpdate`."""


@dataclass(frozen=True)
class WeaponDefinition:
    """Metadata about a weapon configured for a game."""

    code: str
    name: str
    aliases: tuple[str, ...] = ()
    points: Optional[int] = None
    headshot_bonus: Optional[int] = None


@dataclass(frozen=True)
class ActionDefinition:
    """Metadata about a non-frag action (trigger/world event)."""

    code: str
    description: str
    aliases: tuple[str, ...] = ()
    points: Optional[int] = None
    team_award: bool = False


@dataclass(frozen=True)
class LocalizationCatalog:
    """Simple localization wrapper used for formatting broadcast messages."""

    templates: Mapping[str, str]
    default_template: str = "{actor} {event_code}"

    def render(self, key: str, **kwargs: Any) -> str:
        template = self._resolve_template(key)
        base_kwargs = dict(kwargs)
        base_kwargs.setdefault("event_code", key)
        base_kwargs.setdefault("actor", "")
        try:
            return template.format(**base_kwargs)
        except KeyError:
            # Fall back to a predictable representation by ensuring common tokens
            # exist before formatting the default template.
            fallback_kwargs = {
                "actor": base_kwargs.get("actor", ""),
                "event_code": base_kwargs.get("event_code", key),
            }
            return self.default_template.format(**fallback_kwargs)

    def _resolve_template(self, key: str) -> str:
        search_keys: list[str] = [key]
        if "." in key:
            parts = key.split(".")
            while parts:
                parts.pop()
                if not parts:
                    break
                search_keys.append(".".join(parts))
        search_keys.append("__default__")

        lower_templates = {k.lower(): v for k, v in self.templates.items()}
        for candidate in search_keys:
            template = lower_templates.get(candidate.lower())
            if template:
                return template
        return self.default_template


@dataclass(frozen=True)
class GameSchema:
    """Container with per-game definitions used to normalise events."""

    game: str
    weapons: Mapping[str, WeaponDefinition] = field(default_factory=dict)
    actions: Mapping[str, ActionDefinition] = field(default_factory=dict)

    _weapon_aliases: Mapping[str, str] = field(init=False, repr=False)
    _action_aliases: Mapping[str, str] = field(init=False, repr=False)

    def __post_init__(self) -> None:  # pragma: no cover - trivial setup
        object.__setattr__(self, "_weapon_aliases", _build_alias_index(self.weapons))
        object.__setattr__(self, "_action_aliases", _build_alias_index(self.actions))

    def resolve_weapon(self, name: str | None) -> Optional[WeaponDefinition]:
        if not name:
            return None
        key = name.lower()
        alias = self._weapon_aliases.get(key)
        if alias is None:
            return None
        return self.weapons.get(alias)

    def resolve_action(self, name: str | None) -> Optional[ActionDefinition]:
        if not name:
            return None
        key = name.lower()
        alias = self._action_aliases.get(key)
        if alias is None:
            return None
        return self.actions.get(alias)


def _build_alias_index(definitions: Mapping[str, WeaponDefinition | ActionDefinition]) -> Mapping[str, str]:
    aliases: MutableMapping[str, str] = {}
    for code, definition in definitions.items():
        aliases[code.lower()] = code
        if isinstance(definition, WeaponDefinition):
            names = (definition.name,)
        else:
            names = (definition.description,)
        for name in names:
            aliases[name.lower()] = code
        for alias in definition.aliases:
            aliases[alias.lower()] = code
    return MappingProxyType(dict(aliases))


@dataclass(frozen=True)
class EventContext:
    """Runtime data required by handlers to produce updates."""

    server_id: int
    game: str
    schema: Optional[GameSchema] = None
    localization: Optional[LocalizationCatalog] = None
    extras: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def render_message(self, key: str, **kwargs: Any) -> Optional[str]:
        if not self.localization:
            return None
        return self.localization.render(key, **kwargs)


def freeze_mapping(data: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
    """Return an immutable view of *data*."""

    if not data:
        return MappingProxyType({})
    if isinstance(data, MappingProxyType):
        return data
    return MappingProxyType(dict(data))


class EventDispatcher:
    """Routes :class:`LogEvent` objects to registered handlers."""

    def __init__(self, handlers: Iterable[EventHandler], fallback: EventHandler | None = None) -> None:
        self._handlers_by_type: dict[LogEventType, list[EventHandler]] = {}
        for handler in handlers:
            for event_type in handler.supported_types:
                self._handlers_by_type.setdefault(event_type, []).append(handler)
        self._fallback = fallback

    def dispatch(self, event: LogEvent, context: EventContext) -> EventUpdate:
        for handler in self._handlers_by_type.get(event.event_type, []):
            update = handler.handle(event, context)
            if update is not None:
                return update
        if self._fallback is not None:
            update = self._fallback.handle(event, context)
            if update is not None:
                return update
        raise EventProcessingError(event)
