"""Tests for :class:`app.services.review.PlaybookReviewService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReviewStatus
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_review import PlaybookReviewRepository
from app.services.review import PlaybookReviewService
from tests.conftest import make_playbook


def _build_service(db_session: AsyncSession) -> PlaybookReviewService:
    return PlaybookReviewService(
        PlaybookReviewRepository(db_session), PlaybookRepository(db_session)
    )


class TestPlaybookReviewService:
    async def test_request_creates_pending_review(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        reviewer_id = uuid.uuid4()

        review = await service.request(playbook.id, version_id=None, reviewer_id=reviewer_id)
        assert review.status == ReviewStatus.PENDING
        assert review.reviewer_id == reviewer_id

    async def test_request_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.request(uuid.uuid4(), version_id=None, reviewer_id=None)

    async def test_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        await service.request(playbook.id, version_id=None, reviewer_id=None)

        reviews = await service.list_for_playbook(playbook.id)
        assert len(reviews) == 1

    async def test_decide_records_status_and_comments(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        review = await service.request(playbook.id, version_id=None, reviewer_id=None)

        decided = await service.decide(
            review.id, status=ReviewStatus.CHANGES_REQUESTED, comments="Please fix X."
        )
        assert decided.status == ReviewStatus.CHANGES_REQUESTED
        assert decided.comments == "Please fix X."
        assert decided.reviewed_at is not None

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())
