"""Tests for automatic exception mapping."""

from __future__ import annotations

from aio_pika.exceptions import AMQPError
from jwt.exceptions import PyJWTError
from minio.error import MinioException
from redis.exceptions import RedisError
from shared_core.exceptions import (
    AIIOSTimeoutError,
    AuthenticationError,
    AuthorizationError,
    CacheError,
    DatabaseError,
    NetworkError,
    NotFoundError,
    QueueError,
    StorageError,
    UnknownError,
    ValidationError,
    map_exception,
)
from shared_core.exceptions.base import AIIOSException
from shared_core.exceptions.mapper import map_exception as map_exception_direct
from sqlalchemy.exc import SQLAlchemyError


def test_map_exception_returns_aiios_exceptions_unchanged() -> None:
    original = ValidationError("bad input")

    mapped = map_exception(original)

    assert mapped is original


def test_map_exception_maps_value_error_to_validation_error() -> None:
    mapped = map_exception(ValueError("not a number"))

    assert isinstance(mapped, ValidationError)
    assert "not a number" in mapped.message


def test_map_exception_maps_type_error_to_validation_error() -> None:
    mapped = map_exception(TypeError("wrong type"))

    assert isinstance(mapped, ValidationError)


def test_map_exception_maps_key_error_to_not_found_error() -> None:
    mapped = map_exception(KeyError("missing_key"))

    assert isinstance(mapped, NotFoundError)


def test_map_exception_maps_timeout_error() -> None:
    mapped = map_exception(TimeoutError("took too long"))

    assert isinstance(mapped, AIIOSTimeoutError)


def test_map_exception_maps_permission_error_to_authorization_error() -> None:
    mapped = map_exception(PermissionError("denied"))

    assert isinstance(mapped, AuthorizationError)


def test_map_exception_maps_connection_error_to_network_error() -> None:
    mapped = map_exception(ConnectionError("refused"))

    assert isinstance(mapped, NetworkError)


def test_map_exception_maps_sqlalchemy_error_to_database_error() -> None:
    mapped = map_exception(SQLAlchemyError("connection lost"))

    assert isinstance(mapped, DatabaseError)


def test_map_exception_maps_redis_error_to_cache_error() -> None:
    mapped = map_exception(RedisError("timeout"))

    assert isinstance(mapped, CacheError)


def test_map_exception_maps_amqp_error_to_queue_error() -> None:
    mapped = map_exception(AMQPError("channel closed"))

    assert isinstance(mapped, QueueError)


def test_map_exception_maps_minio_exception_to_storage_error() -> None:
    mapped = map_exception(MinioException("bucket not found"))

    assert isinstance(mapped, StorageError)


def test_map_exception_maps_pyjwt_error_to_authentication_error() -> None:
    mapped = map_exception(PyJWTError("bad token"))

    assert isinstance(mapped, AuthenticationError)


def test_map_exception_falls_back_to_unknown_error_for_unrecognized_exceptions() -> None:
    class _SomeWeirdError(Exception):
        pass

    mapped = map_exception(_SomeWeirdError("mystery failure"))

    assert isinstance(mapped, UnknownError)
    assert "mystery failure" in mapped.message


def test_map_exception_uses_class_name_when_message_is_empty() -> None:
    class _SomeWeirdError(Exception):
        pass

    mapped = map_exception(_SomeWeirdError())

    assert "_SomeWeirdError" in mapped.message


def test_map_exception_is_reexported_identically_from_package_root() -> None:
    assert map_exception is map_exception_direct


def test_map_exception_always_returns_an_aiios_exception() -> None:
    assert isinstance(map_exception(Exception("anything")), AIIOSException)
