"""Value compression.

Per docs/019_Enterprise_Cache_Framework.md.txt "SERIALIZATION":
"Compression: Gzip, Zstandard". Applied only when the serialized payload
is at least ``threshold_bytes`` long -- compressing tiny values wastes CPU
for no space benefit (docs/019 "PERFORMANCE": "Compression Threshold").
"""

from __future__ import annotations

import gzip
from enum import StrEnum
from typing import Final

import zstandard

from shared_core.cache.constants import DEFAULT_GZIP_LEVEL, DEFAULT_ZSTD_LEVEL
from shared_core.cache.exceptions import CompressionFailedError

_MARKER_LENGTH: Final[int] = 1


class CompressionAlgorithm(StrEnum):
    """Compression algorithm applied to a stored value."""

    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"


_MARKERS: Final[dict[CompressionAlgorithm, bytes]] = {
    CompressionAlgorithm.NONE: b"\x00",
    CompressionAlgorithm.GZIP: b"\x01",
    CompressionAlgorithm.ZSTD: b"\x02",
}
_ALGORITHMS_BY_MARKER: Final[dict[bytes, CompressionAlgorithm]] = {
    marker: algorithm for algorithm, marker in _MARKERS.items()
}


def compress(data: bytes, *, algorithm: CompressionAlgorithm, threshold_bytes: int) -> bytes:
    """Compress *data* with *algorithm* if it's at least *threshold_bytes* long.

    The chosen algorithm (or "none", for payloads under the threshold) is
    prefixed as a single marker byte, so :func:`decompress` never needs to
    be told separately which algorithm was used.
    """
    if algorithm is CompressionAlgorithm.NONE or len(data) < threshold_bytes:
        return _MARKERS[CompressionAlgorithm.NONE] + data
    try:
        if algorithm is CompressionAlgorithm.GZIP:
            compressed = gzip.compress(data, compresslevel=DEFAULT_GZIP_LEVEL)
        else:
            compressed = zstandard.ZstdCompressor(level=DEFAULT_ZSTD_LEVEL).compress(data)
    except Exception as exc:
        raise CompressionFailedError(f"Failed to compress value with {algorithm.value}.") from exc
    return _MARKERS[algorithm] + compressed


def decompress(data: bytes) -> bytes:
    """Decompress bytes produced by :func:`compress`.

    Raises:
        CompressionFailedError: If *data* has no recognizable compression
            marker, or decompression itself fails (corrupt payload).
    """
    marker, payload = data[:_MARKER_LENGTH], data[_MARKER_LENGTH:]
    algorithm = _ALGORITHMS_BY_MARKER.get(marker)
    if algorithm is None:
        raise CompressionFailedError(f"Unrecognized compression marker: {marker!r}.")
    if algorithm is CompressionAlgorithm.NONE:
        return payload
    try:
        if algorithm is CompressionAlgorithm.GZIP:
            return gzip.decompress(payload)
        return zstandard.ZstdDecompressor().decompress(payload)
    except Exception as exc:
        raise CompressionFailedError(f"Failed to decompress value ({algorithm.value}).") from exc


__all__ = ["CompressionAlgorithm", "compress", "decompress"]
