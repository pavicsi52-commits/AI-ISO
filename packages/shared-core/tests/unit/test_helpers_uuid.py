"""Tests for the UUID helper functions."""

from __future__ import annotations

import uuid

from shared_core.helpers.uuid_helper import generate_uuid, is_valid_uuid, short_uuid


def test_generate_uuid_returns_a_uuid() -> None:
    assert isinstance(generate_uuid(), uuid.UUID)


def test_generate_uuid_returns_unique_values() -> None:
    assert generate_uuid() != generate_uuid()


def test_is_valid_uuid_accepts_valid_string() -> None:
    assert is_valid_uuid(str(uuid.uuid4())) is True


def test_is_valid_uuid_rejects_invalid_string() -> None:
    assert is_valid_uuid("not-a-uuid") is False


def test_short_uuid_returns_first_segment() -> None:
    value = uuid.uuid4()

    assert short_uuid(value) == str(value).split("-")[0]


def test_short_uuid_generates_when_none_given() -> None:
    result = short_uuid()

    assert len(result) == 8
