"""Tests for the reusable SQLAlchemy declarative mixins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from shared_core.base import BaseEntityMixin
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class _Base(DeclarativeBase):
    pass


class _Widget(_Base, BaseEntityMixin):
    __tablename__ = "widgets"

    name: Mapped[str] = mapped_column()


@pytest.fixture
def session():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_entity_gets_a_uuid_primary_key_on_flush(session: Session) -> None:
    widget = _Widget(name="thing", organization_id=uuid.uuid4())
    session.add(widget)
    session.flush()

    assert isinstance(widget.id, uuid.UUID)


def test_entity_defaults_to_active_and_version_one(session: Session) -> None:
    widget = _Widget(name="thing", organization_id=uuid.uuid4())
    session.add(widget)
    session.flush()

    assert widget.is_active is True
    assert widget.version == 1
    assert widget.deleted_at is None


def test_entity_gets_created_and_updated_timestamps(session: Session) -> None:
    widget = _Widget(name="thing", organization_id=uuid.uuid4())
    session.add(widget)
    session.flush()

    assert widget.created_at is not None
    assert widget.updated_at is not None


def test_entity_carries_tenant_scope(session: Session) -> None:
    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    widget = _Widget(name="thing", organization_id=org_id, project_id=project_id)
    session.add(widget)
    session.flush()

    assert widget.organization_id == org_id
    assert widget.project_id == project_id


def test_soft_delete_sets_flags_without_removing_row(session: Session) -> None:
    widget = _Widget(name="thing", organization_id=uuid.uuid4())
    session.add(widget)
    session.flush()
    widget_id = widget.id

    widget.deleted_at = datetime.now(UTC)
    widget.is_active = False
    session.flush()

    fetched = session.get(_Widget, widget_id)
    assert fetched is not None
    assert fetched.is_active is False
    assert fetched.deleted_at is not None
