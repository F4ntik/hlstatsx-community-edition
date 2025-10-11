"""Event handling subsystem for the Python port of hlstats.pl."""
from .base import (
    ActionDefinition,
    EventCategory,
    EventContext,
    EventDispatcher,
    EventProcessingError,
    EventUpdate,
    GameSchema,
    LocalizationCatalog,
    WeaponDefinition,
    freeze_mapping,
)
from .handlers import (
    ChatEventHandler,
    ConnectEventHandler,
    DisconnectEventHandler,
    GenericEventHandler,
    KillEventHandler,
    TeamEventHandler,
    TriggerEventHandler,
    WorldEventHandler,
)

__all__ = [
    "ActionDefinition",
    "EventCategory",
    "EventContext",
    "EventDispatcher",
    "EventProcessingError",
    "EventUpdate",
    "GameSchema",
    "LocalizationCatalog",
    "WeaponDefinition",
    "freeze_mapping",
    "ChatEventHandler",
    "ConnectEventHandler",
    "DisconnectEventHandler",
    "GenericEventHandler",
    "KillEventHandler",
    "TeamEventHandler",
    "TriggerEventHandler",
    "WorldEventHandler",
]
