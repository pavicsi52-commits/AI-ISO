"""Tests for the expanded CacheManager, serialization, compression,
encryption, TTL management, and cache key building.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis
from shared_core.cache.compression import CompressionAlgorithm, compress, decompress
from shared_core.cache.constants import MAX_TTL_SECONDS, MIN_TTL_SECONDS
from shared_core.cache.encryption import decrypt_value, encrypt_value, generate_encryption_key
from shared_core.cache.exceptions import (
    CacheEncryptionError,
    CacheTTLError,
    CompressionFailedError,
    InvalidCacheKeyError,
    SerializationFailedError,
)
from shared_core.cache.helpers import mask_sensitive_key
from shared_core.cache.keys import (
    asset_key,
    build_cache_key,
    build_pattern,
    execution_key,
    inventory_key,
    job_key,
    organization_key,
    playbook_key,
    project_key,
    user_key,
    validate_cache_key,
    validation_key,
    workflow_key,
)
from shared_core.cache.manager import CacheManager
from shared_core.cache.serializer import deserialize, serialize
from shared_core.cache.settings import CacheSettings, SerializationFormat
from shared_core.cache.statistics import CacheStatistics
from shared_core.cache.ttl import (
    NO_EXPIRATION,
    absolute_expiry,
    resolve_ttl,
    ttl_remaining_ratio,
    validate_ttl,
)


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeAsyncRedis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
def manager(redis_client: FakeAsyncRedis) -> CacheManager:
    return CacheManager(redis_client)


# --- serializer.py ---


@pytest.mark.parametrize(
    "fmt", [SerializationFormat.JSON, SerializationFormat.MSGPACK, SerializationFormat.PICKLE]
)
def test_serialize_deserialize_round_trips(fmt: SerializationFormat) -> None:
    value = {"a": 1, "b": [1, 2, 3], "c": "text"}
    data = serialize(value, fmt=fmt)
    assert deserialize(data, fmt=fmt) == value


def test_serialize_json_raises_serialization_failed_for_circular_reference() -> None:
    circular: dict[str, object] = {}
    circular["self"] = circular

    with pytest.raises(SerializationFailedError):
        serialize(circular, fmt=SerializationFormat.JSON)


def test_deserialize_raises_serialization_failed_for_corrupt_data() -> None:
    with pytest.raises(SerializationFailedError):
        deserialize(b"not valid json {{{", fmt=SerializationFormat.JSON)


# --- compression.py ---


@pytest.mark.parametrize("algorithm", [CompressionAlgorithm.GZIP, CompressionAlgorithm.ZSTD])
def test_compress_decompress_round_trips_above_threshold(algorithm: CompressionAlgorithm) -> None:
    data = b"x" * 2000
    compressed = compress(data, algorithm=algorithm, threshold_bytes=1024)
    assert len(compressed) < len(data)
    assert decompress(compressed) == data


def test_compress_below_threshold_stores_uncompressed() -> None:
    data = b"small"
    compressed = compress(data, algorithm=CompressionAlgorithm.ZSTD, threshold_bytes=1024)
    assert decompress(compressed) == data


def test_compress_none_algorithm_never_compresses() -> None:
    data = b"x" * 2000
    compressed = compress(data, algorithm=CompressionAlgorithm.NONE, threshold_bytes=1)
    assert decompress(compressed) == data


def test_decompress_raises_for_unknown_marker() -> None:
    with pytest.raises(CompressionFailedError):
        decompress(b"\xff not a real marker")


def test_decompress_raises_for_corrupt_compressed_payload() -> None:
    gzip_marker = b"\x01"
    with pytest.raises(CompressionFailedError):
        decompress(gzip_marker + b"not actually gzip data")


# --- encryption.py ---


def test_encrypt_decrypt_round_trips_arbitrary_bytes() -> None:
    key = generate_encryption_key()
    data = bytes(range(256))  # includes every byte value, not just valid UTF-8

    encrypted = encrypt_value(data, key=key)
    assert encrypted != data
    assert decrypt_value(encrypted, key=key) == data


def test_decrypt_raises_cache_encryption_error_with_wrong_key() -> None:
    key_a, key_b = generate_encryption_key(), generate_encryption_key()
    encrypted = encrypt_value(b"secret", key=key_a)

    with pytest.raises(CacheEncryptionError):
        decrypt_value(encrypted, key=key_b)


def test_encrypt_raises_cache_encryption_error_for_malformed_key() -> None:
    with pytest.raises(CacheEncryptionError):
        encrypt_value(b"data", key="not-a-valid-base64-key!!!")


# --- ttl.py ---


def test_validate_ttl_accepts_no_expiration_sentinel() -> None:
    validate_ttl(NO_EXPIRATION)  # does not raise


def test_validate_ttl_rejects_out_of_range_values() -> None:
    with pytest.raises(CacheTTLError):
        validate_ttl(MIN_TTL_SECONDS - 1)
    with pytest.raises(CacheTTLError):
        validate_ttl(MAX_TTL_SECONDS + 1)


def test_resolve_ttl_uses_default_when_none_given() -> None:
    assert resolve_ttl(None, default=42) == 42


def test_resolve_ttl_returns_none_for_no_expiration() -> None:
    assert resolve_ttl(NO_EXPIRATION) is None


def test_absolute_expiry_is_in_the_future() -> None:
    expiry = absolute_expiry(60)
    assert expiry > dt.datetime.now(dt.UTC)


def test_ttl_remaining_ratio_bounds() -> None:
    assert ttl_remaining_ratio(ttl_seconds=100, remaining_seconds=50) == 0.5
    assert ttl_remaining_ratio(ttl_seconds=100, remaining_seconds=1000) == 1.0
    assert ttl_remaining_ratio(ttl_seconds=0, remaining_seconds=10) == 0.0


# --- keys.py ---


def test_build_cache_key_joins_with_prefix() -> None:
    assert build_cache_key("organization", "abc-123") == "aiios:organization:abc-123"


def test_build_pattern_supports_wildcards() -> None:
    assert build_pattern("organization", "*") == "aiios:organization:*"


def test_named_key_builders() -> None:
    assert organization_key("1") == "aiios:organization:1"
    assert asset_key("2") == "aiios:asset:2"
    assert execution_key("3") == "aiios:execution:3"
    assert job_key("4") == "aiios:job:4"
    assert project_key("5") == "aiios:project:5"
    assert user_key("6") == "aiios:user:6"
    assert inventory_key("7") == "aiios:inventory:7"
    assert playbook_key("8") == "aiios:playbook:8"
    assert workflow_key("9") == "aiios:workflow:9"
    assert validation_key("10") == "aiios:validation:10"


def test_mask_sensitive_key() -> None:
    assert mask_sensitive_key("abcdefgh") == "****efgh"
    assert mask_sensitive_key("ab") == "**"


def test_validate_cache_key_rejects_empty() -> None:
    with pytest.raises(InvalidCacheKeyError):
        validate_cache_key("")
    with pytest.raises(InvalidCacheKeyError):
        validate_cache_key("   ")


def test_validate_cache_key_rejects_too_long() -> None:
    with pytest.raises(InvalidCacheKeyError):
        validate_cache_key("x" * 1000)


def test_validate_cache_key_rejects_whitespace() -> None:
    with pytest.raises(InvalidCacheKeyError):
        validate_cache_key("has a space")


def test_validate_cache_key_accepts_normal_key() -> None:
    validate_cache_key("aiios:organization:abc-123")  # does not raise


# --- CacheManager: expanded operations ---


async def test_manager_increment_and_decrement(manager: CacheManager) -> None:
    assert await manager.increment("counter") == 1
    assert await manager.increment("counter", amount=5) == 6
    assert await manager.decrement("counter", amount=2) == 4


async def test_manager_persist_removes_ttl(
    manager: CacheManager, redis_client: FakeAsyncRedis
) -> None:
    await manager.set("key1", "value", ttl_seconds=1000)
    assert await manager.persist("key1") is True
    assert await redis_client.ttl("key1") == -1


async def test_manager_touch_with_explicit_ttl_reexpires(manager: CacheManager) -> None:
    await manager.set("key1", "value", ttl_seconds=1000)
    assert await manager.touch("key1", ttl_seconds=50) is True


async def test_manager_touch_without_ttl_uses_redis_touch(real_redis_client: Redis) -> None:
    # fakeredis doesn't implement TOUCH; exercised against the real container instead.
    manager = CacheManager(real_redis_client)
    await manager.set("key1", "value")
    assert await manager.touch("key1") is True
    assert await manager.touch("missing-key") is False


async def test_manager_clear_matches_glob_pattern(manager: CacheManager) -> None:
    await manager.set("aiios:org:1", "a")
    await manager.set("aiios:org:2", "b")
    await manager.set("aiios:project:1", "c")

    deleted = await manager.clear("aiios:org:*")

    assert deleted == 2
    assert await manager.exists("aiios:org:1") is False
    assert await manager.exists("aiios:project:1") is True


async def test_manager_clear_prefix_delegates_to_clear(manager: CacheManager) -> None:
    await manager.set("aiios:org:1", "a")
    assert await manager.clear_prefix("aiios:org:") == 1


async def test_manager_bulk_set_and_bulk_get(manager: CacheManager) -> None:
    await manager.bulk_set({"k1": "v1", "k2": "v2"})

    result = await manager.bulk_get(["k1", "k2", "missing"])

    assert result == {"k1": "v1", "k2": "v2", "missing": None}


async def test_manager_bulk_get_empty_keys_returns_empty_dict(manager: CacheManager) -> None:
    assert await manager.bulk_get([]) == {}


async def test_manager_bulk_set_empty_items_is_a_noop(manager: CacheManager) -> None:
    await manager.bulk_set({})  # does not raise


async def test_manager_bulk_delete(manager: CacheManager) -> None:
    await manager.bulk_set({"k1": "v1", "k2": "v2"})

    deleted = await manager.bulk_delete(["k1", "k2", "missing"])

    assert deleted == 2


async def test_manager_bulk_delete_empty_keys_returns_zero(manager: CacheManager) -> None:
    assert await manager.bulk_delete([]) == 0


async def test_manager_statistics_track_hits_and_misses(manager: CacheManager) -> None:
    await manager.set("key1", "value")
    await manager.get("key1")
    await manager.get("missing")

    assert manager.statistics.hits == 1
    assert manager.statistics.misses == 1
    assert manager.statistics.hit_ratio == 0.5


async def test_manager_statistics_track_sets_and_deletes(manager: CacheManager) -> None:
    await manager.set("key1", "value")
    await manager.delete("key1")

    assert manager.statistics.sets == 1
    assert manager.statistics.deletes == 1


async def test_manager_delete_missing_key_does_not_record_delete(manager: CacheManager) -> None:
    await manager.delete("missing")
    assert manager.statistics.deletes == 0


async def test_manager_no_expiration_ttl_sets_key_without_expiry(
    manager: CacheManager, redis_client: FakeAsyncRedis
) -> None:
    await manager.set("permanent", "value", ttl_seconds=NO_EXPIRATION)
    assert await redis_client.ttl("permanent") == -1


async def test_manager_with_compression_disabled_still_round_trips(
    redis_client: FakeAsyncRedis,
) -> None:
    settings = CacheSettings(compression_enabled=False)
    manager = CacheManager(redis_client, settings=settings)

    await manager.set("key1", {"a": 1})
    assert await manager.get("key1") == {"a": 1}


async def test_manager_with_encryption_round_trips(redis_client: FakeAsyncRedis) -> None:
    key = generate_encryption_key()
    settings = CacheSettings(encryption_enabled=True, encryption_key=key)
    manager = CacheManager(redis_client, settings=settings)

    await manager.set("secret", {"token": "abc123"})
    assert await manager.get("secret") == {"token": "abc123"}


async def test_manager_with_encryption_enabled_but_no_key_raises_on_set(
    redis_client: FakeAsyncRedis,
) -> None:
    settings = CacheSettings(encryption_enabled=True, encryption_key=None)
    manager = CacheManager(redis_client, settings=settings)

    with pytest.raises(CacheEncryptionError):
        await manager.set("key1", "value")


async def test_manager_with_msgpack_format(redis_client: FakeAsyncRedis) -> None:
    settings = CacheSettings(serialization_format=SerializationFormat.MSGPACK)
    manager = CacheManager(redis_client, settings=settings)

    await manager.set("key1", {"a": 1, "b": [1, 2, 3]})
    assert await manager.get("key1") == {"a": 1, "b": [1, 2, 3]}


async def test_manager_uses_provided_statistics_instance(redis_client: FakeAsyncRedis) -> None:
    stats = CacheStatistics()
    manager = CacheManager(redis_client, statistics=stats)

    await manager.get("missing")

    assert stats.misses == 1
    assert manager.statistics is stats
