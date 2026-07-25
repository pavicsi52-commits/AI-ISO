"""Bulk operation request schema."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, field_validator

from shared_core.requests.base import BaseRequest


class BulkRequest(BaseRequest):
    """Inbound list of entity IDs targeted by a bulk operation.

    Per docs/006_API_Design_Master.md.txt "BULK OPERATIONS".
    """

    ids: list[UUID] = Field(min_length=1)

    @field_validator("ids")
    @classmethod
    def _ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("ids must not contain duplicates")
        return value
