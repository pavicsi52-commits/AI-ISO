"""Factory / Fixture support for tests and seeds.

Per docs/018_Enterprise_Database_Framework.md.txt "SEED FRAMEWORK": "Factory
Support" and "Fixture Support". :class:`ModelFactory` is the reusable base
every service's own test factories subclass -- it owns no business-specific
defaults itself (that would be business logic this framework must not
implement), only the mechanics: sequence numbers, build vs. persist, and
batch construction.
"""

from __future__ import annotations

import itertools
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession


class ModelFactory[T]:
    """Base test-data factory for one entity model.

    Concrete factories subclass this, set ``model``, and override
    :meth:`default_values`::

        class WidgetFactory(ModelFactory[Widget]):
            model = Widget

            @classmethod
            def default_values(cls) -> dict[str, Any]:
                return {"name": f"widget-{cls.next_sequence()}", "organization_id": uuid4()}

        widget = WidgetFactory.build(name="custom")       # not persisted
        widget = await WidgetFactory.create(session)       # persisted
        widgets = await WidgetFactory.create_batch(session, 5)
    """

    model: ClassVar[type[Any]]
    _sequence: ClassVar[itertools.count[int]] = itertools.count(1)

    @classmethod
    def next_sequence(cls) -> int:
        """Return the next value in this factory's monotonic sequence counter.

        Useful for guaranteed-unique field values, e.g.
        ``f"user-{cls.next_sequence()}@example.com"``.
        """
        return next(cls._sequence)

    @classmethod
    def default_values(cls) -> dict[str, Any]:
        """Return this factory's default field values. Override per model."""
        return {}

    @classmethod
    def build(cls, **overrides: Any) -> T:
        """Construct an entity instance without persisting it."""
        values = {**cls.default_values(), **overrides}
        return cls.model(**values)  # type: ignore[no-any-return]

    @classmethod
    def build_batch(cls, count: int, **overrides: Any) -> list[T]:
        """Construct *count* entity instances without persisting them."""
        return [cls.build(**overrides) for _ in range(count)]

    @classmethod
    async def create(cls, session: AsyncSession, **overrides: Any) -> T:
        """Construct and persist one entity instance."""
        entity = cls.build(**overrides)
        session.add(entity)
        await session.flush()
        return entity

    @classmethod
    async def create_batch(cls, session: AsyncSession, count: int, **overrides: Any) -> list[T]:
        """Construct and persist *count* entity instances in one flush."""
        entities = cls.build_batch(count, **overrides)
        session.add_all(entities)
        await session.flush()
        return entities


__all__ = ["ModelFactory"]
