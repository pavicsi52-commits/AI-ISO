"""Centralized settings.

Basic configuration sections covering the infrastructure every service
connects to. This is the Prompt 012 baseline;
docs/013_Configuration_Framework.md.txt expands it with hot reload,
per-environment file layering, and additional business-domain sections.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared_core.config.environment import Environment

_ENV_PREFIX = "AIIOS_"


class _Section(BaseSettings):
    """Base class for a configuration section: shared env-loading behavior."""

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ApplicationSettings(_Section):
    """Application identity and runtime settings."""

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = Field(default="ai-ios")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")


class DatabaseSettings(_Section):
    """PostgreSQL connection settings."""

    database_host: str = Field(default="localhost")
    database_port: int = Field(default=5432, ge=1, le=65_535)
    database_name: str = Field(default="aiios")
    database_user: str = Field(default="aiios")
    database_password: str = Field(default="")
    database_pool_min: int = Field(default=5, ge=1)
    database_pool_max: int = Field(default=20, ge=1)

    @property
    def dsn(self) -> str:
        """Async SQLAlchemy DSN for this database connection."""
        return (
            f"postgresql+asyncpg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


class RedisSettings(_Section):
    """Redis connection settings."""

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379, ge=1, le=65_535)
    redis_password: str = Field(default="")
    redis_db: int = Field(default=0, ge=0)

    @property
    def url(self) -> str:
        """Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


class RabbitMQSettings(_Section):
    """RabbitMQ connection settings."""

    rabbitmq_host: str = Field(default="localhost")
    rabbitmq_port: int = Field(default=5672, ge=1, le=65_535)
    rabbitmq_user: str = Field(default="aiios")
    rabbitmq_password: str = Field(default="")
    rabbitmq_vhost: str = Field(default="/aiios")
    rabbitmq_tls_enabled: bool = Field(default=False)
    rabbitmq_heartbeat_seconds: int = Field(default=60, ge=0)

    @property
    def url(self) -> str:
        """AMQP connection URL.

        The vhost is percent-encoded because AI-IOS's default vhost value
        (``/aiios``) itself contains a literal ``/``, which must not be
        confused with the URL's host/path separator. Uses ``amqps://``
        when ``rabbitmq_tls_enabled`` is set, ``amqp://`` otherwise.
        """
        encoded_vhost = quote(self.rabbitmq_vhost, safe="")
        scheme = "amqps" if self.rabbitmq_tls_enabled else "amqp"
        return (
            f"{scheme}://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{encoded_vhost}"
        )


class Neo4jSettings(_Section):
    """Neo4j connection settings."""

    neo4j_host: str = Field(default="localhost")
    neo4j_bolt_port: int = Field(default=7687, ge=1, le=65_535)
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="")

    @property
    def uri(self) -> str:
        """Bolt connection URI."""
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"


class MinioSettings(_Section):
    """MinIO / S3-compatible object storage settings."""

    minio_host: str = Field(default="localhost")
    minio_port: int = Field(default=9000, ge=1, le=65_535)
    minio_access_key: str = Field(default="")
    minio_secret_key: str = Field(default="")
    minio_use_ssl: bool = Field(default=False)

    @property
    def endpoint(self) -> str:
        """Host:port endpoint string."""
        return f"{self.minio_host}:{self.minio_port}"


class OpenSearchSettings(_Section):
    """OpenSearch connection settings."""

    opensearch_host: str = Field(default="localhost")
    opensearch_port: int = Field(default=9200, ge=1, le=65_535)
    opensearch_user: str = Field(default="")
    opensearch_password: str = Field(default="")


class AuthSettings(_Section):
    """JWT authentication settings."""

    jwt_algorithm: str = Field(default="RS256")
    jwt_access_token_ttl_seconds: int = Field(default=900, ge=1)
    jwt_refresh_token_ttl_seconds: int = Field(default=604_800, ge=1)


class LoggingSettings(_Section):
    """Enterprise Logging Framework settings (docs/014_Enterprise_Logging_Framework.md.txt).

    ``ApplicationSettings.log_level`` remains the simple, always-available
    level knob every service reads; this section is for the richer
    output/rotation/retention/masking configuration the logging framework
    itself needs.
    """

    log_level: str = Field(default="INFO")
    log_outputs: str = Field(default="console")
    log_file_path: str = Field(default="logs/app.log")
    log_file_max_bytes: int = Field(default=100_000_000, ge=1)
    log_rotation_when: str = Field(default="midnight")
    log_backup_count: int = Field(default=30, ge=0)
    log_compress_rotated: bool = Field(default=True)
    log_retention_days: int = Field(default=90, ge=1)
    log_mask_enabled: bool = Field(default=True)

    @property
    def outputs(self) -> list[str]:
        """Parsed list of enabled log output names (``console``, ``file``, ``otel``)."""
        return [item.strip() for item in self.log_outputs.split(",") if item.strip()]


class MonitoringSettings(_Section):
    """Monitoring and metrics settings."""

    prometheus_port: int = Field(default=9090, ge=1, le=65_535)


class TelemetrySettings(_Section):
    """OpenTelemetry tracing/metrics export settings."""

    telemetry_enabled: bool = Field(default=True)
    telemetry_service_name: str = Field(default="ai-ios")
    telemetry_exporter: str = Field(default="console")
    telemetry_otlp_endpoint: str = Field(default="")
    telemetry_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)


class StorageSettings(_Section):
    """Object storage abstraction settings.

    Backend-agnostic (which backend, which bucket, upload limits); the
    connection details for the MinIO backend itself live in
    :class:`MinioSettings`.
    """

    storage_backend: str = Field(default="minio")
    storage_bucket: str = Field(default="aiios")
    storage_max_upload_mb: int = Field(default=100, ge=1)


class EmailSettings(_Section):
    """Outbound email (SMTP) settings."""

    email_enabled: bool = Field(default=False)
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_use_tls: bool = Field(default=True)
    email_from_address: str = Field(default="noreply@aiios.local")


class NotificationSettings(_Section):
    """Notification dispatch settings."""

    notifications_enabled: bool = Field(default=True)
    notification_channels: str = Field(default="email")
    notification_retry_attempts: int = Field(default=3, ge=0)

    @property
    def channels(self) -> list[str]:
        """Parsed list of enabled notification channel names."""
        return [item.strip() for item in self.notification_channels.split(",") if item.strip()]


class SchedulerSettings(_Section):
    """Background job scheduler settings."""

    scheduler_enabled: bool = Field(default=True)
    scheduler_timezone: str = Field(default="UTC")
    scheduler_max_concurrent_jobs: int = Field(default=10, ge=1)


class AISettings(_Section):
    """AI provider integration settings."""

    ai_provider: str = Field(default="none")
    ai_api_key: str = Field(default="")
    ai_default_model: str = Field(default="")
    ai_request_timeout_seconds: int = Field(default=30, ge=1)


class AutomationSettings(_Section):
    """Automation/playbook execution settings."""

    automation_enabled: bool = Field(default=True)
    automation_max_concurrent_playbooks: int = Field(default=5, ge=1)
    automation_default_timeout_seconds: int = Field(default=3_600, ge=1)


class InventorySettings(_Section):
    """Asset inventory scanning settings."""

    inventory_scan_enabled: bool = Field(default=True)
    inventory_scan_interval_seconds: int = Field(default=3_600, ge=60)


class ValidationSettings(_Section):
    """Validation framework behavior settings."""

    validation_strict_mode: bool = Field(default=True)
    validation_max_errors: int = Field(default=50, ge=1)


class SecretsSettings(_Section):
    """Secret-backend selection.

    Per docs/013_Configuration_Framework.md.txt "SECRET MANAGEMENT": today
    only ``env`` (plain/Docker/Kubernetes secret files, see
    :mod:`shared_core.config.secrets`) is implemented; Vault/AWS/Azure are
    future backends this field is reserved to select.
    """

    secrets_backend: str = Field(default="env")
    secrets_vault_addr: str = Field(default="")
