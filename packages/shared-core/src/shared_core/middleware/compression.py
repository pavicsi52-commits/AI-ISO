"""Compression middleware.

Re-exports Starlette's battle-tested ``GZipMiddleware`` under this
package's namespace so every AI-IOS service imports compression from
``shared_core.middleware`` rather than reaching into Starlette directly.
"""

from __future__ import annotations

from starlette.middleware.gzip import GZipMiddleware as CompressionMiddleware

__all__ = ["CompressionMiddleware"]
