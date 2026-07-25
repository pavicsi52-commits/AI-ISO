"""Response-layer type aliases."""

from __future__ import annotations

from typing import Any

type ResponseData = dict[str, Any] | list[Any] | None
