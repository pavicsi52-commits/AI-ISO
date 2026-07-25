"""Central default values for every configuration field.

Built by introspecting each settings section's Pydantic field defaults, so
the same default a section quietly falls back to is also what
:func:`shared_core.config.get` falls back to when a key isn't present as an
environment variable or resolved secret -- one source of truth, not two
lists to keep in sync by hand.
"""

from __future__ import annotations

from pydantic_core import PydanticUndefined

from shared_core.config.constants import ConfigConstants
from shared_core.config.settings import (
    AISettings,
    ApplicationSettings,
    AuthSettings,
    AutomationSettings,
    DatabaseSettings,
    EmailSettings,
    InventorySettings,
    LoggingSettings,
    MinioSettings,
    MonitoringSettings,
    Neo4jSettings,
    NotificationSettings,
    OpenSearchSettings,
    RabbitMQSettings,
    RedisSettings,
    SchedulerSettings,
    SecretsSettings,
    StorageSettings,
    TelemetrySettings,
    ValidationSettings,
)

_ALL_SECTION_CLASSES = (
    ApplicationSettings,
    DatabaseSettings,
    RedisSettings,
    RabbitMQSettings,
    Neo4jSettings,
    MinioSettings,
    OpenSearchSettings,
    AuthSettings,
    LoggingSettings,
    MonitoringSettings,
    TelemetrySettings,
    StorageSettings,
    EmailSettings,
    NotificationSettings,
    SchedulerSettings,
    AISettings,
    AutomationSettings,
    InventorySettings,
    ValidationSettings,
    SecretsSettings,
)


def _collect_defaults() -> dict[str, str]:
    values: dict[str, str] = {}
    for section_cls in _ALL_SECTION_CLASSES:
        for field_name, field_info in section_cls.model_fields.items():
            if field_info.default is PydanticUndefined:
                continue
            values[f"{ConfigConstants.ENV_PREFIX}{field_name.upper()}"] = str(field_info.default)
    return values


DEFAULTS: dict[str, str] = _collect_defaults()
