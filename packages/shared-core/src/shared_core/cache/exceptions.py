"""Cache-framework-specific exceptions.

Each subclasses :class:`shared_core.exceptions.cache.CacheError` so a bare
``except CacheError`` still catches everything raised anywhere in this
framework. Not registered in :mod:`shared_core.exceptions.constants`'s
central catalog -- that module already depends on
:mod:`shared_core.exceptions.cache`, so importing back from here would
cycle. Error codes are still manually kept unique against the rest of the
``AIIOS-CACHE-*`` range (the same approach
:mod:`shared_core.database.exceptions` uses for ``AIIOS-DB-*``), per
docs/019_Enterprise_Cache_Framework.md.txt "ERROR HANDLING": "Map all
errors using Prompt 015."
"""

from __future__ import annotations

from shared_core.exceptions.cache import CacheError


class CacheConnectionError(CacheError):
    """Raised when a Redis connection cannot be established after retries."""

    error_code = "AIIOS-CACHE-0002"
    retryable = True
    default_user_message = "Could not connect to the cache. Please try again."


class CacheTimeoutError(CacheError):
    """Raised when a cache operation exceeds its configured timeout."""

    error_code = "AIIOS-CACHE-0003"
    status_code = 504
    retryable = True
    default_user_message = "The request took too long to process. Please try again."


class SerializationFailedError(CacheError):
    """Raised when a value cannot be serialized for storage, or deserialized on read."""

    error_code = "AIIOS-CACHE-0004"
    severity = "high"
    retryable = False
    default_user_message = "The request could not be processed."


class CompressionFailedError(CacheError):
    """Raised when compressing or decompressing a cached value fails."""

    error_code = "AIIOS-CACHE-0005"
    severity = "high"
    retryable = False
    default_user_message = "The request could not be processed."


class CacheEncryptionError(CacheError):
    """Raised when encrypting or decrypting a cached value fails."""

    error_code = "AIIOS-CACHE-0006"
    severity = "critical"
    retryable = False
    default_user_message = "The request could not be processed."


class ClusterUnavailableError(CacheError):
    """Raised when no reachable node in a Redis Cluster/Sentinel topology can serve a request."""

    error_code = "AIIOS-CACHE-0007"
    severity = "high"
    retryable = True
    default_user_message = "The cache is temporarily unavailable. Please try again."


class LockAcquisitionFailedError(CacheError):
    """Raised when a distributed lock could not be acquired within its retry budget."""

    error_code = "AIIOS-CACHE-0008"
    status_code = 409
    retryable = True
    default_user_message = "The resource is currently locked. Please try again."


class InvalidCacheKeyError(CacheError):
    """Raised when a cache key fails validation (empty, too long, disallowed characters)."""

    error_code = "AIIOS-CACHE-0009"
    status_code = 400
    retryable = False
    default_user_message = "The request is invalid."


class CacheTTLError(CacheError):
    """Raised when a TTL value fails validation (negative, zero, or out of range)."""

    error_code = "AIIOS-CACHE-0010"
    status_code = 400
    retryable = False
    default_user_message = "The request is invalid."


__all__ = [
    "CacheConnectionError",
    "CacheEncryptionError",
    "CacheTTLError",
    "CacheTimeoutError",
    "ClusterUnavailableError",
    "CompressionFailedError",
    "InvalidCacheKeyError",
    "LockAcquisitionFailedError",
    "SerializationFailedError",
]
