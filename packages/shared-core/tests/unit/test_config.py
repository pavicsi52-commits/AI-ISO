"""Tests for the Configuration Framework."""

from __future__ import annotations

import time

import pytest
from shared_core.config import (
    AISettings,
    ApplicationSettings,
    AuthSettings,
    AutomationSettings,
    DatabaseSettings,
    EmailSettings,
    Environment,
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
    Settings,
    StorageSettings,
    TelemetrySettings,
    ValidationSettings,
    clear_settings_cache,
    configure_cache_ttl,
    detect_environment,
    env_files_for,
    exists,
    get,
    get_bool,
    get_dict,
    get_float,
    get_int,
    get_list,
    get_profile,
    get_settings,
    get_string,
    load_settings,
    parse_environment,
    reload,
    reload_settings,
    resolve_secret,
    validate_settings,
)
from shared_core.config.defaults import DEFAULTS
from shared_core.config.exceptions import (
    CircularConfigurationError,
    InvalidConfigurationError,
    InvalidTypeError,
    MissingSecretError,
    MissingVariableError,
    UnknownEnvironmentError,
)
from shared_core.config.helpers import (
    coerce_bool,
    coerce_dict,
    coerce_float,
    coerce_int,
    coerce_list,
    interpolate,
    mask_config_value,
)
from shared_core.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_settings_cache()
    configure_cache_ttl(None)
    yield
    clear_settings_cache()
    configure_cache_ttl(None)


# --- environment ---


def test_detect_environment_defaults_to_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIIOS_ENVIRONMENT", raising=False)

    assert detect_environment() == Environment.DEVELOPMENT


def test_detect_environment_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_ENVIRONMENT", "production")

    assert detect_environment() == Environment.PRODUCTION


def test_detect_environment_falls_back_on_unrecognized_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIIOS_ENVIRONMENT", "not-a-real-environment")

    assert detect_environment() == Environment.DEVELOPMENT


def test_environment_is_production_property() -> None:
    assert Environment.PRODUCTION.is_production is True
    assert Environment.DEVELOPMENT.is_production is False


def test_environment_allows_hot_reload_in_local_and_development_only() -> None:
    assert Environment.DEVELOPMENT.allows_hot_reload is True
    assert Environment.LOCAL.allows_hot_reload is True
    assert Environment.PRODUCTION.allows_hot_reload is False
    assert Environment.TESTING.allows_hot_reload is False
    assert Environment.CI.allows_hot_reload is False
    assert Environment.STAGING.allows_hot_reload is False


def test_parse_environment_accepts_every_supported_name() -> None:
    for name in ("local", "development", "testing", "ci", "staging", "production"):
        assert parse_environment(name).value == name


def test_parse_environment_raises_for_unknown_name() -> None:
    with pytest.raises(UnknownEnvironmentError):
        parse_environment("not-a-real-environment")


# --- settings sections ---


def test_database_settings_builds_dsn() -> None:
    settings = DatabaseSettings(
        database_host="db.local",
        database_port=5432,
        database_name="aiios",
        database_user="aiios",
        database_password="secret",
        _env_file=None,
    )

    assert settings.dsn == "postgresql+asyncpg://aiios:secret@db.local:5432/aiios"


def test_redis_settings_builds_url_without_password() -> None:
    settings = RedisSettings(redis_host="redis.local", redis_port=6379, _env_file=None)

    assert settings.url == "redis://redis.local:6379/0"


def test_redis_settings_builds_url_with_password() -> None:
    settings = RedisSettings(redis_host="redis.local", redis_password="pw", _env_file=None)

    assert settings.url == "redis://:pw@redis.local:6379/0"


def test_rabbitmq_settings_builds_url_with_percent_encoded_vhost() -> None:
    settings = RabbitMQSettings(
        rabbitmq_host="mq.local", rabbitmq_user="u", rabbitmq_password="p", _env_file=None
    )

    assert settings.url == "amqp://u:p@mq.local:5672/%2Faiios"


def test_rabbitmq_settings_builds_url_for_a_plain_vhost_name() -> None:
    settings = RabbitMQSettings(
        rabbitmq_host="mq.local",
        rabbitmq_user="u",
        rabbitmq_password="p",
        rabbitmq_vhost="myvhost",
        _env_file=None,
    )

    assert settings.url == "amqp://u:p@mq.local:5672/myvhost"


def test_neo4j_settings_builds_uri() -> None:
    settings = Neo4jSettings(neo4j_host="graph.local", _env_file=None)

    assert settings.uri == "bolt://graph.local:7687"


def test_minio_settings_builds_endpoint() -> None:
    settings = MinioSettings(minio_host="s3.local", minio_port=9000, _env_file=None)

    assert settings.endpoint == "s3.local:9000"


def test_notification_settings_parses_channels() -> None:
    settings = NotificationSettings(notification_channels="email, slack ,webhook", _env_file=None)

    assert settings.channels == ["email", "slack", "webhook"]


def test_notification_settings_default_channel_is_email() -> None:
    settings = NotificationSettings(_env_file=None)

    assert settings.channels == ["email"]


def test_logging_settings_parses_outputs() -> None:
    settings = LoggingSettings(log_outputs="console, file ,otel", _env_file=None)

    assert settings.outputs == ["console", "file", "otel"]


def test_logging_settings_default_output_is_console() -> None:
    settings = LoggingSettings(_env_file=None)

    assert settings.outputs == ["console"]


# --- loader ---


def test_env_files_for_only_returns_existing_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AIIOS_APP_NAME=base\n", encoding="utf-8")

    files = env_files_for(Environment.DEVELOPMENT)

    assert files == (".env",)


def test_env_files_for_layers_base_environment_and_local(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")
    (tmp_path / ".env.development").write_text("", encoding="utf-8")
    (tmp_path / ".env.local").write_text("", encoding="utf-8")

    files = env_files_for(Environment.DEVELOPMENT)

    assert files == (".env", ".env.development", ".env.local")


def test_load_settings_aggregates_every_section() -> None:
    settings = load_settings()

    assert isinstance(settings, Settings)
    assert isinstance(settings.application, ApplicationSettings)
    assert isinstance(settings.database, DatabaseSettings)
    assert isinstance(settings.redis, RedisSettings)
    assert isinstance(settings.rabbitmq, RabbitMQSettings)
    assert isinstance(settings.neo4j, Neo4jSettings)
    assert isinstance(settings.minio, MinioSettings)
    assert isinstance(settings.opensearch, OpenSearchSettings)
    assert isinstance(settings.auth, AuthSettings)
    assert isinstance(settings.logging, LoggingSettings)
    assert isinstance(settings.monitoring, MonitoringSettings)
    assert isinstance(settings.telemetry, TelemetrySettings)
    assert isinstance(settings.storage, StorageSettings)
    assert isinstance(settings.email, EmailSettings)
    assert isinstance(settings.notifications, NotificationSettings)
    assert isinstance(settings.scheduler, SchedulerSettings)
    assert isinstance(settings.ai, AISettings)
    assert isinstance(settings.automation, AutomationSettings)
    assert isinstance(settings.inventory, InventorySettings)
    assert isinstance(settings.validation, ValidationSettings)
    assert isinstance(settings.secrets, SecretsSettings)


def test_load_settings_applies_runtime_overrides() -> None:
    settings = load_settings(database_password="from-override")

    assert settings.database.database_password == "from-override"


def test_load_settings_rejects_unknown_runtime_override() -> None:
    with pytest.raises(TypeError, match="unexpected keyword"):
        load_settings(not_a_real_field="x")


def test_load_settings_raises_invalid_configuration_for_bad_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIIOS_DATABASE_PORT", "not-a-number")

    with pytest.raises(InvalidConfigurationError):
        load_settings()


def test_load_settings_overlays_secret_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    secret_file = tmp_path / "db_password"
    secret_file.write_text("from-secret-file", encoding="utf-8")
    monkeypatch.setenv("AIIOS_DATABASE_PASSWORD_FILE", str(secret_file))

    settings = load_settings()

    assert settings.database.database_password == "from-secret-file"


def test_load_settings_runtime_override_wins_over_secret_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    secret_file = tmp_path / "db_password"
    secret_file.write_text("from-secret-file", encoding="utf-8")
    monkeypatch.setenv("AIIOS_DATABASE_PASSWORD_FILE", str(secret_file))

    settings = load_settings(database_password="explicit-override")

    assert settings.database.database_password == "explicit-override"


# --- cache ---


def test_get_settings_returns_same_cached_instance() -> None:
    first = get_settings()
    second = get_settings()

    assert first is second


def test_reload_settings_returns_a_new_instance() -> None:
    first = get_settings()
    second = reload_settings()

    assert first is not second


def test_clear_settings_cache_forces_reload_on_next_access() -> None:
    first = get_settings()
    clear_settings_cache()
    second = get_settings()

    assert first is not second


def test_configure_cache_ttl_expires_the_cached_instance() -> None:
    configure_cache_ttl(0.01)
    first = get_settings()
    time.sleep(0.02)
    second = get_settings()

    assert first is not second


def test_configure_cache_ttl_none_disables_expiry() -> None:
    configure_cache_ttl(None)
    first = get_settings()
    time.sleep(0.02)
    second = get_settings()

    assert first is second


# --- configuration API ---


def test_get_returns_a_value_from_a_settings_section() -> None:
    assert get("database_host") == "localhost"


def test_get_falls_back_to_raw_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_CUSTOM_FLAG", "yes")

    assert get("custom_flag") == "yes"


def test_get_returns_default_when_nothing_resolves() -> None:
    assert get("totally_unknown_key", "fallback") == "fallback"


def test_exists_true_for_a_known_field() -> None:
    assert exists("database_host") is True


def test_exists_false_for_an_unknown_key() -> None:
    assert exists("totally_unknown_key") is False


def test_get_string_returns_the_value() -> None:
    assert get_string("database_host") == "localhost"


def test_get_string_raises_missing_variable_without_default() -> None:
    with pytest.raises(MissingVariableError):
        get_string("totally_unknown_key")


def test_get_string_returns_default_when_missing() -> None:
    assert get_string("totally_unknown_key", "fallback") == "fallback"


def test_get_bool_coerces_section_value() -> None:
    assert get_bool("debug") is False


def test_get_int_coerces_section_value() -> None:
    assert get_int("database_port") == 5432


def test_get_int_raises_invalid_type_for_non_numeric_value() -> None:
    with pytest.raises(InvalidTypeError):
        get_int("app_name")


def test_get_float_coerces_section_value() -> None:
    assert get_float("telemetry_sample_ratio") == 1.0


def test_get_list_splits_a_raw_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_TAGS", "a,b,c")

    assert get_list("tags") == ["a", "b", "c"]


def test_get_list_returns_default_when_missing() -> None:
    assert get_list("totally_unknown_key", ["x"]) == ["x"]


def test_get_dict_parses_a_json_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_META", '{"a": 1}')

    assert get_dict("meta") == {"a": 1}


def test_get_dict_raises_invalid_type_for_non_json_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_META", "not-json")

    with pytest.raises(InvalidTypeError):
        get_dict("meta")


def test_reload_alias_returns_a_new_instance() -> None:
    first = get_settings()
    second = reload()

    assert first is not second


# --- validator ---


def test_validate_settings_passes_for_non_production() -> None:
    settings = load_settings()

    validate_settings(settings)  # should not raise


def test_validate_settings_raises_for_production_missing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIIOS_ENVIRONMENT", "production")
    settings = load_settings()

    with pytest.raises(ConfigurationError) as exc_info:
        validate_settings(settings)

    assert "database.database_password" in exc_info.value.details


def test_validate_settings_raises_missing_secret_error_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIIOS_ENVIRONMENT", "production")
    settings = load_settings()

    with pytest.raises(MissingSecretError):
        validate_settings(settings)


def _production_settings(**overrides: object) -> Settings:
    base = {
        "application": ApplicationSettings(environment=Environment.PRODUCTION, _env_file=None),
        "database": DatabaseSettings(database_password="x", _env_file=None),
        "redis": RedisSettings(_env_file=None),
        "rabbitmq": RabbitMQSettings(rabbitmq_password="x", _env_file=None),
        "neo4j": Neo4jSettings(neo4j_password="x", _env_file=None),
        "minio": MinioSettings(minio_access_key="x", minio_secret_key="x", _env_file=None),
        "opensearch": OpenSearchSettings(_env_file=None),
        "auth": AuthSettings(_env_file=None),
        "logging": LoggingSettings(_env_file=None),
        "monitoring": MonitoringSettings(_env_file=None),
        "telemetry": TelemetrySettings(_env_file=None),
        "storage": StorageSettings(_env_file=None),
        "email": EmailSettings(_env_file=None),
        "notifications": NotificationSettings(_env_file=None),
        "scheduler": SchedulerSettings(_env_file=None),
        "ai": AISettings(_env_file=None),
        "automation": AutomationSettings(_env_file=None),
        "inventory": InventorySettings(_env_file=None),
        "validation": ValidationSettings(_env_file=None),
        "secrets": SecretsSettings(_env_file=None),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_validate_settings_passes_for_production_with_secrets_set() -> None:
    validate_settings(_production_settings())  # should not raise


def test_validate_settings_requires_smtp_password_when_email_enabled() -> None:
    settings = _production_settings(email=EmailSettings(email_enabled=True, _env_file=None))

    with pytest.raises(MissingSecretError) as exc_info:
        validate_settings(settings)

    assert "email.smtp_password" in exc_info.value.details


def test_validate_settings_requires_ai_api_key_when_provider_set() -> None:
    settings = _production_settings(ai=AISettings(ai_provider="openai", _env_file=None))

    with pytest.raises(MissingSecretError) as exc_info:
        validate_settings(settings)

    assert "ai.ai_api_key" in exc_info.value.details


# --- secrets ---


def test_resolve_secret_reads_plain_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_TEST_SECRET", "plain-value")
    monkeypatch.delenv("AIIOS_TEST_SECRET_FILE", raising=False)

    assert resolve_secret("AIIOS_TEST_SECRET") == "plain-value"


def test_resolve_secret_prefers_file_over_plain_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-value\n", encoding="utf-8")
    monkeypatch.setenv("AIIOS_TEST_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("AIIOS_TEST_SECRET", "plain-value")

    assert resolve_secret("AIIOS_TEST_SECRET") == "file-value"


def test_resolve_secret_returns_none_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIIOS_MISSING_SECRET", raising=False)
    monkeypatch.delenv("AIIOS_MISSING_SECRET_FILE", raising=False)

    assert resolve_secret("AIIOS_MISSING_SECRET") is None


def test_resolve_secret_handles_missing_file_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIIOS_TEST_SECRET_FILE", "/nonexistent/path/secret.txt")
    monkeypatch.setenv("AIIOS_TEST_SECRET", "fallback-value")

    assert resolve_secret("AIIOS_TEST_SECRET") == "fallback-value"


# --- exceptions ---


@pytest.mark.parametrize(
    "exc",
    [
        InvalidConfigurationError("database", "bad value"),
        MissingVariableError("database_host"),
        InvalidTypeError("database_port", "int", "abc"),
        MissingSecretError(["database.database_password"]),
        UnknownEnvironmentError("bogus"),
        CircularConfigurationError("A"),
    ],
)
def test_config_exceptions_are_configuration_errors(exc: ConfigurationError) -> None:
    assert isinstance(exc, ConfigurationError)
    assert exc.error_code.startswith("AIIOS-CONFIG-")


# --- helpers ---


@pytest.mark.parametrize("value", ["1", "true", "Yes", "on", True])
def test_coerce_bool_true_values(value: object) -> None:
    assert coerce_bool("k", value) is True


@pytest.mark.parametrize("value", ["0", "false", "No", "off", False])
def test_coerce_bool_false_values(value: object) -> None:
    assert coerce_bool("k", value) is False


def test_coerce_bool_raises_for_unrecognized_value() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_bool("k", "maybe")


def test_coerce_int_passes_through_int() -> None:
    assert coerce_int("k", 5) == 5


def test_coerce_int_parses_numeric_string() -> None:
    assert coerce_int("k", "42") == 42


def test_coerce_int_rejects_bool() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_int("k", True)


def test_coerce_int_raises_for_non_numeric_string() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_int("k", "abc")


def test_coerce_float_parses_numeric_string() -> None:
    assert coerce_float("k", "1.5") == 1.5


def test_coerce_float_rejects_bool() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_float("k", False)


def test_coerce_float_raises_for_non_numeric_string() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_float("k", "abc")


def test_coerce_list_splits_on_separator() -> None:
    assert coerce_list("k", "a, b ,c") == ["a", "b", "c"]


def test_coerce_list_passes_through_list() -> None:
    assert coerce_list("k", ["a", "b"]) == ["a", "b"]


def test_coerce_list_empty_string_is_empty_list() -> None:
    assert coerce_list("k", "") == []


def test_coerce_dict_parses_json_object() -> None:
    assert coerce_dict("k", '{"a": 1}') == {"a": 1}


def test_coerce_dict_passes_through_dict() -> None:
    assert coerce_dict("k", {"a": 1}) == {"a": 1}


def test_coerce_dict_raises_for_invalid_json() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_dict("k", "not-json")


def test_coerce_dict_raises_when_json_is_not_an_object() -> None:
    with pytest.raises(InvalidTypeError):
        coerce_dict("k", "[1, 2, 3]")


def test_mask_config_value_masks_secret_like_keys() -> None:
    assert mask_config_value("database_password", "supersecretvalue") != "supersecretvalue"


def test_mask_config_value_passes_through_non_secret_keys() -> None:
    assert mask_config_value("database_host", "localhost") == "localhost"


def test_interpolate_resolves_a_reference() -> None:
    names = {"NAME": "value"}
    result = interpolate("prefix-${NAME}-suffix", names.get)

    assert result == "prefix-value-suffix"


def test_interpolate_resolves_nested_references() -> None:
    values = {"A": "${B}", "B": "final"}

    result = interpolate("${A}", values.get)

    assert result == "final"


def test_interpolate_raises_missing_variable_for_unresolved_reference() -> None:
    with pytest.raises(MissingVariableError):
        interpolate("${MISSING}", lambda name: None)


def test_interpolate_raises_circular_configuration_error() -> None:
    values = {"A": "${B}", "B": "${A}"}

    with pytest.raises(CircularConfigurationError):
        interpolate("${A}", values.get)


# --- profiles ---


def test_get_profile_development_allows_hot_reload() -> None:
    profile = get_profile(Environment.DEVELOPMENT)

    assert profile.hot_reload_enabled is True
    assert profile.debug is True


def test_get_profile_production_disallows_hot_reload() -> None:
    profile = get_profile(Environment.PRODUCTION)

    assert profile.hot_reload_enabled is False
    assert profile.debug is False
    assert profile.cache_ttl_seconds == 300.0


# --- defaults ---


def test_defaults_contains_known_field_defaults() -> None:
    assert DEFAULTS["AIIOS_DATABASE_HOST"] == "localhost"
    assert DEFAULTS["AIIOS_DATABASE_PORT"] == "5432"


def test_defaults_covers_every_section() -> None:
    assert DEFAULTS["AIIOS_TELEMETRY_SERVICE_NAME"] == "ai-ios"
    assert DEFAULTS["AIIOS_SECRETS_BACKEND"] == "env"
