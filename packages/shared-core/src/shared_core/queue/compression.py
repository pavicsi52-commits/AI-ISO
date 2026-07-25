"""Message compression.

Per docs/021_Enterprise_Queue_Framework.md.txt "SERIALIZATION":
"Compression." Re-exports :mod:`shared_core.cache.compression` (Prompt
019) rather than reimplementing Gzip/Zstandard framing a second time --
``cache`` has no dependency on ``queue``, so this direction is safe
(unlike the ``cache -> security`` cycle Prompt 019 hit and reverted).
"""

from __future__ import annotations

from shared_core.cache.compression import CompressionAlgorithm, compress, decompress

__all__ = ["CompressionAlgorithm", "compress", "decompress"]
