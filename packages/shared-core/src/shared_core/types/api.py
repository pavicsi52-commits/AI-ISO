"""API-layer type aliases."""

from __future__ import annotations

type JsonValue = str | int | float | bool | None | dict[str, JsonValue] | list[JsonValue]
type QueryParams = dict[str, str | int | float | bool | list[str] | None]
