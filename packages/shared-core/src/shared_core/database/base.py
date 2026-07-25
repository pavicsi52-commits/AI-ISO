"""Shared SQLAlchemy declarative base and the standard entity base model.

Per docs/018_Enterprise_Database_Framework.md.txt "BASE MODEL": every future
entity inherits UUID, ``created_at``, ``updated_at``, ``deleted_at``,
``created_by``, ``updated_by``, ``deleted_by``, ``version``, ``is_active``,
``organization_id``, ``project_id`` -- "No future entity may redefine these
fields." Those columns are already composed once, correctly, in
:class:`shared_core.base.BaseEntityMixin` (Prompt 012); :class:`BaseModel`
here is that composition applied to this package's declarative ``Base`` so a
concrete entity only has to inherit one class instead of two.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from shared_core.base import BaseEntityMixin


class Base(DeclarativeBase):
    """Declarative base every AI-IOS entity model inherits."""


class BaseModel(Base, BaseEntityMixin):
    """Standard base every future AI-IOS entity table inherits.

    Combines :class:`Base` with :class:`~shared_core.base.BaseEntityMixin`'s
    full standard column set. A concrete entity only ever adds its own
    domain-specific columns::

        class Asset(BaseModel):
            __tablename__ = "assets"
            name: Mapped[str] = mapped_column()
    """

    __abstract__ = True


__all__ = ["Base", "BaseModel"]
