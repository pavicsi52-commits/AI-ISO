"""Configuration loading.

Builds a fully-populated :class:`Settings` from field defaults,
environment-selected dotenv files, resolved secrets, and explicit runtime
overrides, in that precedence order
(docs/013_Configuration_Framework.md.txt "LOAD ORDER").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings

from shared_core.config.constants import ConfigConstants
from shared_core.config.environment import Environment, detect_environment
from shared_core.config.exceptions import InvalidConfigurationError
from shared_core.config.secrets import resolve_secret
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
from shared_core.logging import get_logger

logger = get_logger(__name__)

_SECRET_FIELD_PATTERN = re.compile(ConfigConstants.SECRET_FIELD_NAME_PATTERN, re.IGNORECASE)

_SECTIONS: tuple[tuple[str, type[BaseSettings]], ...] = (
    ("application", ApplicationSettings),
    ("database", DatabaseSettings),
    ("redis", RedisSettings),
    ("rabbitmq", RabbitMQSettings),
    ("neo4j", Neo4jSettings),
    ("minio", MinioSettings),
    ("opensearch", OpenSearchSettings),
    ("auth", AuthSettings),
    ("logging", LoggingSettings),
    ("monitoring", MonitoringSettings),
    ("telemetry", TelemetrySettings),
    ("storage", StorageSettings),
    ("email", EmailSettings),
    ("notifications", NotificationSettings),
    ("scheduler", SchedulerSettings),
    ("ai", AISettings),
    ("automation", AutomationSettings),
    ("inventory", InventorySettings),
    ("validation", ValidationSettings),
    ("secrets", SecretsSettings),
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Aggregate of every configuration section.

    Every AI-IOS service should depend on this class (via
    :func:`shared_core.config.get_settings`) rather than reading environment
    variables directly.
    """

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    neo4j: Neo4jSettings
    minio: MinioSettings
    opensearch: OpenSearchSettings
    auth: AuthSettings
    logging: LoggingSettings
    monitoring: MonitoringSettings
    telemetry: TelemetrySettings
    storage: StorageSettings
    email: EmailSettings
    notifications: NotificationSettings
    scheduler: SchedulerSettings
    ai: AISettings
    automation: AutomationSettings
    inventory: InventorySettings
    validation: ValidationSettings
    secrets: SecretsSettings


def env_files_for(environment: Environment) -> tuple[str, ...]:
    """Return the dotenv files that apply to *environment*, in load order.

    Later files take precedence over earlier ones. Files that don't exist
    on disk are skipped (pydantic-settings would silently ignore a missing
    ``env_file`` anyway, but being explicit here lets callers -- like the
    hot-reload watcher -- know exactly which files are actually in play).
    """
    candidates = (
        ConfigConstants.BASE_ENV_FILE,
        f".env.{environment.value}",
        ConfigConstants.LOCAL_ENV_FILE,
    )
    return tuple(name for name in candidates if Path(name).is_file())


def _instantiate_section(
    section_cls: type[BaseSettings],
    env_files: tuple[str, ...],
    explicit_overrides: dict[str, Any],
) -> BaseSettings:
    try:
        section = section_cls(_env_file=env_files or None)
    except PydanticValidationError as exc:
        raise InvalidConfigurationError(section_cls.__name__, str(exc)) from exc

    # Secrets override the dotenv/env-var value, but never a value the
    # caller explicitly asked for -- runtime overrides always win.
    secret_updates = {
        field_name: resolved
        for field_name in section_cls.model_fields
        if field_name not in explicit_overrides
        and _SECRET_FIELD_PATTERN.search(field_name)
        and (resolved := resolve_secret(f"{ConfigConstants.ENV_PREFIX}{field_name.upper()}"))
        is not None
    }
    if secret_updates:
        section = section.model_copy(update=secret_updates)

    if explicit_overrides:
        section = section.model_copy(update=explicit_overrides)

    return section


def load_settings(environment: Environment | None = None, **runtime_overrides: Any) -> Settings:
    """Load every configuration section.

    Load order: field defaults -> environment-selected dotenv files (OS
    environment variables already take precedence over dotenv files, per
    pydantic-settings) -> resolved secrets -> explicit *runtime_overrides*
    -- each stage overrides the one before it.

    Raises:
        InvalidConfigurationError: If a section fails to load or validate.
        TypeError: If *runtime_overrides* names a field no section declares.
    """
    env = environment or detect_environment()
    env_files = env_files_for(env)

    known_fields = {name for _, section_cls in _SECTIONS for name in section_cls.model_fields}
    unknown = set(runtime_overrides) - known_fields
    if unknown:
        raise TypeError(f"load_settings() got unexpected keyword arguments: {sorted(unknown)}")

    try:
        sections = {
            field_name: _instantiate_section(
                section_cls,
                env_files,
                {k: v for k, v in runtime_overrides.items() if k in section_cls.model_fields},
            )
            for field_name, section_cls in _SECTIONS
        }
    except InvalidConfigurationError:
        logger.error("config.load.failure", extra={"environment": env.value})
        raise

    logger.info(
        "config.load.success",
        extra={"environment": env.value, "files": list(env_files)},
    )
    # `sections` is built data-driven from `_SECTIONS`, so each value's
    # runtime type is guaranteed correct by construction even though mypy
    # can't verify that through a homogeneous dict[str, BaseSettings].
    return Settings(**sections)  # type: ignore[arg-type]
