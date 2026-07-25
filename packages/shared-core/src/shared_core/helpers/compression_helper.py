"""Compression helper functions."""

from __future__ import annotations

import gzip
import zlib


def gzip_compress(data: bytes) -> bytes:
    """Compress ``data`` using gzip."""
    return gzip.compress(data)


def gzip_decompress(data: bytes) -> bytes:
    """Decompress gzip-compressed ``data``."""
    return gzip.decompress(data)


def zlib_compress(data: bytes, level: int = 6) -> bytes:
    """Compress ``data`` using zlib at the given compression level."""
    return zlib.compress(data, level)


def zlib_decompress(data: bytes) -> bytes:
    """Decompress zlib-compressed ``data``."""
    return zlib.decompress(data)
