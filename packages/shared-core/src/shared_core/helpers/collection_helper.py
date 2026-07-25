"""Collection manipulation helper functions."""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def chunk[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield successive chunks of ``size`` items from ``items``."""
    if size <= 0:
        raise ValueError("size must be positive")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def deduplicate[T](items: Iterable[T]) -> list[T]:
    """Return items with duplicates removed, preserving order."""
    seen: set[T] = set()
    result: list[T] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def flatten[T](nested: Iterable[Iterable[T]]) -> list[T]:
    """Flatten one level of nested iterables into a single list."""
    return [item for sub in nested for item in sub]


def first[T](items: Iterable[T], default: T | None = None) -> T | None:
    """Return the first item of ``items``, or ``default`` if empty."""
    return next(iter(items), default)
