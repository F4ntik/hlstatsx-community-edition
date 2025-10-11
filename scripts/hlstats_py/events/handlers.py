"""Concrete event handlers that translate log entries into model updates."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from ..protocol import LogEvent, LogEventType
from .base import (
    ActionDefinition,
    EventCategory,
    EventContext,
    EventHandler,
    EventUpdate,
    GameSchema,
    WeaponDefinition,
    freeze_mapping,
)


class _HandlerBase(EventHandler):
    supported_types: tuple[LogEventType, ...] = ()

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:  # pragma: no cover - abstract
        raise NotImplementedError


def _resolve_weapon(schema: GameSchema | None, name: str | None) -> tuple[str, WeaponDefinition | None]:
    if not name:
        return "unknown", None
    if schema is None:
        return name, None
    definition = schema.resolve_weapon(name)
    if definition is None:
        return name, None
    return definition.code, definition


def _resolve_action(schema: GameSchema | None, name: str | None) -> tuple[str, ActionDefinition | None]:
    if not name:
        return "unknown", None
    if schema is None:
        return name, None
    definition = schema.resolve_action(name)
    if definition is None:
        return name, None
    return definition.code, definition


def _build_message(
    context: EventContext,
    key: str,
    *,
    actor: str | None,
    target: str | None = None,
    weapon: str | None = None,
    action: str | None = None,
    message: str | None = None,
    team: str | None = None,
    reason: str | None = None,
    event_code: str,
) -> tuple[str, Optional[str]]:
    rendered = context.render_message(
        key,
        actor=actor or "",
        target=target or "",
        weapon=weapon or "",
        action=action or "",
        message=message or "",
        team=team or "",
        reason=reason or "",
        event_code=event_code,
    )
    return key, rendered


class KillEventHandler(_HandlerBase):
    supported_types = (LogEventType.KILL,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor:
            return None

        event_code, weapon_def = _resolve_weapon(context.schema, event.weapon)
        attributes: dict[str, Any] = {
            "weapon_code": event_code,
            "raw_weapon": event.weapon,
            "headshot": bool(event.properties.get("headshot")),
            "properties": event.properties,
            "is_suicide": event.target is None,
        }
        if weapon_def is not None:
            attributes["weapon_name"] = weapon_def.name
            if weapon_def.points is not None:
                attributes["points"] = weapon_def.points
            if weapon_def.headshot_bonus is not None:
                attributes["headshot_bonus"] = weapon_def.headshot_bonus

        message_key = f"kill.{event_code}"
        message_key, rendered_message = _build_message(
            context,
            message_key,
            actor=event.actor.name,
            target=event.target.name if event.target else event.actor.name,
            weapon=(weapon_def.name if weapon_def else event.weapon) or event_code,
            event_code=event_code,
        )
        if rendered_message is None:
            message_key, rendered_message = _build_message(
                context,
                "kill",
                actor=event.actor.name,
                target=event.target.name if event.target else event.actor.name,
                weapon=(weapon_def.name if weapon_def else event.weapon) or event_code,
                event_code=event_code,
            )

        return EventUpdate(
            category=EventCategory.FRAG,
            event_code=event_code,
            actor=event.actor,
            target=event.target,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class TriggerEventHandler(_HandlerBase):
    supported_types = (LogEventType.TRIGGER,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor or not event.action:
            return None

        event_code, action_def = _resolve_action(context.schema, event.action)
        attributes: dict[str, Any] = {
            "action_code": event_code,
            "raw_action": event.action,
            "properties": event.properties,
            "target": event.target,
        }
        if action_def is not None:
            attributes["description"] = action_def.description
            if action_def.points is not None:
                attributes["points"] = action_def.points
            attributes["team_award"] = action_def.team_award

        message_key = f"trigger.{event_code}"
        message_key, rendered_message = _build_message(
            context,
            message_key,
            actor=event.actor.name,
            target=event.target.name if event.target else None,
            action=action_def.description if action_def else event.action,
            event_code=event_code,
        )
        if rendered_message is None:
            message_key, rendered_message = _build_message(
                context,
                "trigger",
                actor=event.actor.name,
                target=event.target.name if event.target else None,
                action=action_def.description if action_def else event.action,
                event_code=event_code,
            )

        return EventUpdate(
            category=EventCategory.ACTION,
            event_code=event_code,
            actor=event.actor,
            target=event.target,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class ChatEventHandler(_HandlerBase):
    supported_types = (LogEventType.CHAT,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor:
            return None

        attributes: dict[str, Any] = {
            "team_only": bool(event.properties.get("team_only")),
            "message": event.message or "",
        }
        message_key = "chat.team" if attributes["team_only"] else "chat"
        message_key, rendered_message = _build_message(
            context,
            message_key,
            actor=event.actor.name,
            message=event.message,
            team=event.actor.team,
            event_code=message_key,
        )

        return EventUpdate(
            category=EventCategory.CHAT,
            event_code="team" if attributes["team_only"] else "public",
            actor=event.actor,
            target=None,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class TeamEventHandler(_HandlerBase):
    supported_types = (LogEventType.TEAM_CHANGE,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor or not event.team:
            return None

        attributes: dict[str, Any] = {"team": event.team}
        message_key, rendered_message = _build_message(
            context,
            "team_change",
            actor=event.actor.name,
            team=event.team,
            event_code="team_change",
        )
        return EventUpdate(
            category=EventCategory.TEAM,
            event_code=event.team,
            actor=event.actor,
            target=None,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class ConnectEventHandler(_HandlerBase):
    supported_types = (LogEventType.CONNECT,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor:
            return None

        address = None
        if isinstance(event.properties, Mapping):
            value = event.properties.get("address")
            if isinstance(value, str):
                address = value
        attributes: dict[str, Any] = {
            "address": address,
            "properties": event.properties,
        }
        message_key, rendered_message = _build_message(
            context,
            "connect",
            actor=event.actor.name,
            event_code="connect",
            message=address,
        )
        return EventUpdate(
            category=EventCategory.CONNECTION,
            event_code="connect",
            actor=event.actor,
            target=None,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class DisconnectEventHandler(_HandlerBase):
    supported_types = (LogEventType.DISCONNECT,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        if not event.actor:
            return None

        reason = None
        if isinstance(event.properties, Mapping):
            value = event.properties.get("reason")
            if isinstance(value, str):
                reason = value
        attributes: dict[str, Any] = {
            "reason": reason,
            "properties": event.properties,
        }
        message_key, rendered_message = _build_message(
            context,
            "disconnect",
            actor=event.actor.name,
            reason=reason,
            event_code="disconnect",
        )
        return EventUpdate(
            category=EventCategory.CONNECTION,
            event_code="disconnect",
            actor=event.actor,
            target=None,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class WorldEventHandler(_HandlerBase):
    supported_types = (LogEventType.WORLD_TRIGGER,)

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        event_code, action_def = _resolve_action(context.schema, event.action)
        attributes: dict[str, Any] = {
            "action_code": event_code,
            "raw_action": event.action,
            "properties": event.properties,
        }
        if action_def is not None:
            attributes["description"] = action_def.description
            if action_def.points is not None:
                attributes["points"] = action_def.points
            attributes["team_award"] = action_def.team_award

        message_key = f"world.{event_code}"
        message_key, rendered_message = _build_message(
            context,
            message_key,
            actor="World",
            action=action_def.description if action_def else event.action,
            event_code=event_code,
        )
        if rendered_message is None:
            message_key, rendered_message = _build_message(
                context,
                "world",
                actor="World",
                action=action_def.description if action_def else event.action,
                event_code=event_code,
            )

        return EventUpdate(
            category=EventCategory.WORLD,
            event_code=event_code,
            actor=None,
            target=None,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )


class GenericEventHandler(_HandlerBase):
    supported_types = (
        LogEventType.GENERIC,
        LogEventType.NAME_CHANGE,
        LogEventType.CVAR,
    )

    def handle(self, event: LogEvent, context: EventContext) -> Optional[EventUpdate]:
        message_key, rendered_message = _build_message(
            context,
            "generic",
            actor=event.actor.name if event.actor else None,
            message=event.message or event.raw,
            event_code="generic",
        )
        attributes: dict[str, Any] = {
            "raw": event.raw,
            "message": event.message or event.raw,
            "properties": event.properties,
        }
        return EventUpdate(
            category=EventCategory.GENERIC,
            event_code="generic",
            actor=event.actor,
            target=event.target,
            timestamp=event.timestamp,
            attributes=freeze_mapping(attributes),
            message_key=message_key,
            message=rendered_message,
        )
