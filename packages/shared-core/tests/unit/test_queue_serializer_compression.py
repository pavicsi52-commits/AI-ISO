"""Tests for message serialization (JSON/MessagePack) and compression re-export."""

from __future__ import annotations

from shared_core.cache.compression import CompressionAlgorithm as CacheCompressionAlgorithm
from shared_core.cache.compression import compress as cache_compress
from shared_core.cache.encryption import generate_encryption_key
from shared_core.queue.compression import CompressionAlgorithm, compress, decompress
from shared_core.queue.serializer import (
    SerializationFormat,
    compress_body,
    decompress_body,
    decrypt_body,
    deserialize_message,
    encrypt_body,
    serialize_message,
)


def test_serialize_message_json_round_trips() -> None:
    message = {"hello": "world", "count": 3, "nested": {"a": [1, 2, 3]}}

    encoded = serialize_message(message, format=SerializationFormat.JSON)
    decoded = deserialize_message(encoded, format=SerializationFormat.JSON)

    assert decoded == message
    assert encoded.startswith(b"{")


def test_serialize_message_msgpack_round_trips() -> None:
    message = {"hello": "world", "count": 3, "nested": {"a": [1, 2, 3]}}

    encoded = serialize_message(message, format=SerializationFormat.MSGPACK)
    decoded = deserialize_message(encoded, format=SerializationFormat.MSGPACK)

    assert decoded == message
    assert not encoded.startswith(b"{")  # not JSON text


def test_serialize_message_defaults_to_json() -> None:
    encoded = serialize_message({"x": 1})

    assert encoded == b'{"x": 1}'


def test_compress_and_decompress_body_round_trip() -> None:
    body = serialize_message({"description": "x" * 100})

    compressed = compress_body(body, threshold_bytes=10)
    assert compressed != body

    decompressed = decompress_body(compressed)
    assert decompressed == body


def test_compress_body_leaves_small_payloads_effectively_unchanged() -> None:
    body = serialize_message({"x": 1})

    compressed = compress_body(body, threshold_bytes=4096)

    assert decompress_body(compressed) == body


def test_encrypt_and_decrypt_body_round_trip() -> None:
    key = generate_encryption_key()
    body = serialize_message({"secret": "value"})

    encrypted = encrypt_body(body, key=key)
    assert encrypted != body

    decrypted = decrypt_body(encrypted, key=key)
    assert decrypted == body


def test_queue_compression_reexports_cache_compression() -> None:
    """shared_core.queue.compression is a thin re-export of shared_core.cache.compression."""
    assert CompressionAlgorithm is CacheCompressionAlgorithm
    assert compress is cache_compress


def test_compress_decompress_via_queue_module_directly() -> None:
    data = b"x" * 100

    compressed = compress(data, algorithm=CompressionAlgorithm.ZSTD, threshold_bytes=10)

    assert decompress(compressed) == data
