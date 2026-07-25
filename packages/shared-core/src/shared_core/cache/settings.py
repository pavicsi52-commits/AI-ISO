"""Cache-framework connection and behavior configuration.

Adapts :class:`shared_core.config.settings.RedisSettings` (Prompt 013) into
the richer configuration the rest of this framework needs -- Sentinel/
Cluster topology, TLS, pooling, compression, and encryption -- without
modifying the Configuration Framework itself. This is an adapter, not a
duplicate settings source: credentials and the standalone host/port always
come from :class:`~shared_core.config.settings.RedisSettings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from shared_core.cache.constants import (
    DEFAULT_COMPRESSION_THRESHOLD_BYTES,
    DEFAULT_CONNECT_BACKOFF_BASE_SECONDS,
    DEFAULT_CONNECT_BACKOFF_MAX_SECONDS,
    DEFAULT_CONNECT_MAX_ATTEMPTS,
    DEFAULT_POOL_MAX_SIZE,
    DEFAULT_POOL_MIN_SIZE,
    DEFAULT_SOCKET_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_SOCKET_TIMEOUT_SECONDS,
    DEFAULT_TTL_SECONDS,
    KEY_PREFIX,
)
from shared_core.config.settings import RedisSettings


class CacheMode(StrEnum):
    """Which Redis topology the cache framework connects to."""

    STANDALONE = "standalone"
    SENTINEL = "sentinel"
    CLUSTER = "cluster"


class SerializationFormat(StrEnum):
    """Wire format used to serialize cached values."""

    JSON = "json"
    MSGPACK = "msgpack"
    PICKLE = "pickle"  # internal-only: never used for values crossing trust boundaries


@dataclass(frozen=True, slots=True)
class SentinelNode:
    """One Sentinel node's address."""

    host: str
    port: int = 26379


@dataclass(frozen=True, slots=True)
class ClusterNode:
    """One Redis Cluster node's address."""

    host: str
    port: int = 6379


@dataclass(frozen=True, slots=True)
class CacheSettings:
    """Fully-resolved cache framework configuration."""

    redis: RedisSettings = field(default_factory=RedisSettings)
    mode: CacheMode = CacheMode.STANDALONE
    sentinel_nodes: tuple[SentinelNode, ...] = ()
    sentinel_master_name: str = "mymaster"
    cluster_nodes: tuple[ClusterNode, ...] = ()
    tls_enabled: bool = False
    pool_min_size: int = DEFAULT_POOL_MIN_SIZE
    pool_max_size: int = DEFAULT_POOL_MAX_SIZE
    socket_timeout_seconds: float = DEFAULT_SOCKET_TIMEOUT_SECONDS
    socket_connect_timeout_seconds: float = DEFAULT_SOCKET_CONNECT_TIMEOUT_SECONDS
    connect_max_attempts: int = DEFAULT_CONNECT_MAX_ATTEMPTS
    connect_backoff_base_seconds: float = DEFAULT_CONNECT_BACKOFF_BASE_SECONDS
    connect_backoff_max_seconds: float = DEFAULT_CONNECT_BACKOFF_MAX_SECONDS
    default_ttl_seconds: int = DEFAULT_TTL_SECONDS
    key_prefix: str = KEY_PREFIX
    serialization_format: SerializationFormat = SerializationFormat.JSON
    compression_enabled: bool = True
    compression_threshold_bytes: int = DEFAULT_COMPRESSION_THRESHOLD_BYTES
    encryption_enabled: bool = False
    encryption_key: str | None = None


__all__ = [
    "CacheMode",
    "CacheSettings",
    "ClusterNode",
    "SentinelNode",
    "SerializationFormat",
]
