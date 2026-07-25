"""Message serialization.

Per docs/021_Enterprise_Queue_Framework.md.txt "SERIALIZATION": JSON,
MessagePack, Compression, Encryption, Versioning.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

import msgpack

from shared_core.cache.encryption import decrypt_value, encrypt_value
from shared_core.helpers.json_helper import from_json, to_json
from shared_core.queue.compression import CompressionAlgorithm, compress, decompress
from shared_core.queue.constants import DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES


class SerializationFormat(StrEnum):
    """Message body encoding, per docs/021 "SERIALIZATION"."""

    JSON = "json"
    MSGPACK = "msgpack"


def serialize_message(
    message: dict[str, Any], *, format: SerializationFormat = SerializationFormat.JSON
) -> bytes:
    """Encode *message* to bytes using *format*."""
    if format is SerializationFormat.JSON:
        return to_json(message).encode("utf-8")
    return msgpack.packb(message, use_bin_type=True)  # type: ignore[no-any-return]


def deserialize_message(
    data: bytes, *, format: SerializationFormat = SerializationFormat.JSON
) -> dict[str, Any]:
    """Decode bytes produced by :func:`serialize_message` back into a message dict."""
    if format is SerializationFormat.JSON:
        result: dict[str, Any] = from_json(data)
        return result
    unpacked: dict[str, Any] = msgpack.unpackb(data, raw=False)
    return unpacked


def compress_body(
    data: bytes, *, threshold_bytes: int = DEFAULT_PAYLOAD_COMPRESSION_THRESHOLD_BYTES
) -> bytes:
    """Compress a serialized message body if it's at least *threshold_bytes* long.

    Reuses :mod:`shared_core.cache.compression` (Prompt 019) -- see
    :mod:`shared_core.queue.compression`.
    """
    return compress(data, algorithm=CompressionAlgorithm.ZSTD, threshold_bytes=threshold_bytes)


def decompress_body(data: bytes) -> bytes:
    """Reverse :func:`compress_body`."""
    return decompress(data)


def encrypt_body(data: bytes, *, key: str) -> bytes:
    """Encrypt an already-serialized (and optionally compressed) message body.

    Reuses :func:`shared_core.cache.encryption.encrypt_value` (same
    AES-256-GCM implementation Prompt 019 built, bytes-native, no
    dependency cycle -- ``cache`` doesn't depend on ``queue``).
    """
    return encrypt_value(data, key=key)


def decrypt_body(data: bytes, *, key: str) -> bytes:
    """Reverse :func:`encrypt_body`."""
    return decrypt_value(data, key=key)


__all__ = [
    "SerializationFormat",
    "compress_body",
    "decompress_body",
    "decrypt_body",
    "deserialize_message",
    "encrypt_body",
    "serialize_message",
]
