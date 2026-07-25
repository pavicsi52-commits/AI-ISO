"""Tests for the remaining pure-function helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from shared_core.helpers import (
    Stopwatch,
    chunk,
    days_between,
    deduplicate,
    first,
    flatten,
    from_iso8601,
    from_json,
    get_env,
    get_env_bool,
    get_env_int,
    get_extension,
    gzip_compress,
    gzip_decompress,
    human_readable_size,
    is_expired,
    is_running_in_container,
    is_safe_filename,
    mask_string,
    measure_ms,
    retry_async,
    safe_from_json,
    sha256_hex,
    slugify,
    stable_hash,
    to_iso8601,
    to_json,
    to_snake_case,
    truncate,
    zlib_compress,
    zlib_decompress,
)


def test_chunk_splits_into_fixed_size_groups() -> None:
    assert list(chunk([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunk_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError, match="positive"):
        list(chunk([1, 2, 3], 0))


def test_deduplicate_preserves_order() -> None:
    assert deduplicate([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_flatten_merges_one_level() -> None:
    assert flatten([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]


def test_first_returns_first_or_default() -> None:
    assert first([1, 2, 3]) == 1
    assert first([], default="none") == "none"


def test_gzip_round_trip() -> None:
    data = b"hello world" * 100
    assert gzip_decompress(gzip_compress(data)) == data


def test_zlib_round_trip() -> None:
    data = b"hello world" * 100
    assert zlib_decompress(zlib_compress(data)) == data


def test_date_helpers_round_trip() -> None:
    now = datetime.now(UTC)
    assert from_iso8601(to_iso8601(now)) == now


def test_is_expired() -> None:
    past = datetime(2020, 1, 1, tzinfo=UTC)
    future = datetime(2999, 1, 1, tzinfo=UTC)
    assert is_expired(past) is True
    assert is_expired(future) is False


def test_days_between() -> None:
    assert days_between(date(2026, 1, 1), date(2026, 1, 11)) == 10


def test_environment_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR", "hello")
    monkeypatch.setenv("TEST_BOOL", "true")
    monkeypatch.setenv("TEST_INT", "42")

    assert get_env("TEST_VAR") == "hello"
    assert get_env("MISSING_VAR", "default") == "default"
    assert get_env_bool("TEST_BOOL") is True
    assert get_env_bool("MISSING_BOOL", True) is True
    assert get_env_int("TEST_INT") == 42
    assert get_env_int("MISSING_INT", 7) == 7


def test_get_env_int_returns_default_on_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAD_INT", "not-a-number")
    assert get_env_int("BAD_INT", 5) == 5


def test_is_running_in_container_returns_bool() -> None:
    assert isinstance(is_running_in_container(), bool)


def test_file_helpers() -> None:
    assert get_extension("report.PDF") == "pdf"
    assert get_extension("no_extension") == ""
    assert is_safe_filename("report.pdf") is True
    assert is_safe_filename("../etc/passwd") is False
    assert is_safe_filename(".hidden") is False
    assert is_safe_filename("") is False


def test_human_readable_size() -> None:
    assert human_readable_size(512) == "512 B"
    assert human_readable_size(2048) == "2.0 KB"
    assert human_readable_size(5 * 1024 * 1024) == "5.0 MB"


def test_hash_helpers_are_deterministic() -> None:
    assert sha256_hex("hello") == sha256_hex("hello")
    assert sha256_hex("hello") != sha256_hex("world")
    assert stable_hash("a", "b") == stable_hash("a", "b")
    assert stable_hash("a", "b") != stable_hash("b", "a")


def test_json_helpers_round_trip_with_uuid_and_datetime() -> None:
    payload = {"id": uuid4(), "when": datetime.now(UTC)}
    serialized = to_json(payload)
    deserialized = from_json(serialized)

    assert deserialized["id"] == str(payload["id"])


def test_safe_from_json_returns_default_on_invalid_input() -> None:
    assert safe_from_json("not json", default={}) == {}
    assert safe_from_json('{"a": 1}') == {"a": 1}


def test_string_helpers() -> None:
    assert slugify("Hello, World!") == "hello-world"
    assert truncate("hello world", 5) == "he..."
    assert truncate("hi", 5) == "hi"
    assert to_snake_case("SimpleCase") == "simple_case"
    assert to_snake_case("already_snake") == "already_snake"
    assert mask_string("1234567890", visible_chars=4) == "******7890"
    assert mask_string("ab", visible_chars=4) == "**"


def test_stopwatch_measures_elapsed_time() -> None:
    stopwatch = Stopwatch()
    assert stopwatch.elapsed_ms() >= 0
    stopwatch.reset()
    assert stopwatch.elapsed_ms() >= 0


def test_measure_ms_context_manager() -> None:
    with measure_ms() as stopwatch:
        pass
    assert stopwatch.elapsed_ms() >= 0


async def test_retry_async_succeeds_on_first_attempt() -> None:
    async def succeed() -> str:
        return "ok"

    assert await retry_async(succeed) == "ok"


async def test_retry_async_retries_then_succeeds() -> None:
    attempts = {"count": 0}

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("not yet")
        return "ok"

    result = await retry_async(flaky, max_attempts=5, initial_delay_seconds=0.001)

    assert result == "ok"
    assert attempts["count"] == 3


async def test_retry_async_raises_after_exhausting_attempts() -> None:
    async def always_fails() -> str:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await retry_async(always_fails, max_attempts=2, initial_delay_seconds=0.001)


async def test_retry_async_rejects_non_positive_max_attempts() -> None:
    async def succeed() -> str:
        return "ok"

    with pytest.raises(ValueError, match="max_attempts"):
        await retry_async(succeed, max_attempts=0)


async def test_retry_async_only_retries_declared_exceptions() -> None:
    async def raises_type_error() -> str:
        raise TypeError("wrong type")

    with pytest.raises(TypeError):
        await retry_async(
            raises_type_error,
            max_attempts=3,
            initial_delay_seconds=0.001,
            retryable_exceptions=(ValueError,),
        )
