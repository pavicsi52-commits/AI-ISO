"""Tests for :class:`app.services.kubernetes.ConfigurationKubernetesService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ManifestFormat
from app.repositories.configuration_kubernetes_manifest import (
    ConfigurationKubernetesManifestRepository,
)
from app.services.kubernetes import ConfigurationKubernetesService
from tests.conftest import make_profile


def build_service(db_session: AsyncSession) -> ConfigurationKubernetesService:
    return ConfigurationKubernetesService(ConfigurationKubernetesManifestRepository(db_session))


async def test_create_valid_manifest_marks_validated(db_session: AsyncSession) -> None:
    service = build_service(db_session)

    manifest = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        manifest_format=ManifestFormat.YAML_MANIFEST,
        namespace="default",
        name="web-deployment",
        content={
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "web"},
        },
    )

    assert manifest.validated is True
    assert manifest.validation_errors is None


async def test_create_invalid_manifest_records_errors_without_raising(
    db_session: AsyncSession,
) -> None:
    service = build_service(db_session)

    manifest = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        manifest_format=ManifestFormat.YAML_MANIFEST,
        namespace=None,
        name="broken",
        content={"apiVersion": "v1"},
    )

    assert manifest.validated is False
    assert manifest.validation_errors is not None
    assert len(manifest.validation_errors) > 0


async def test_revalidate_reflects_content_changes(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    manifest = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_id=None,
        manifest_format=ManifestFormat.YAML_MANIFEST,
        namespace=None,
        name="fixable",
        content={"apiVersion": "v1"},
    )
    assert manifest.validated is False

    manifest.content = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "fixable"},
    }
    revalidated = await service.revalidate(manifest.id)

    assert revalidated.validated is True
    assert revalidated.validation_errors is None


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_profile_and_delete(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    manifest = await service.create(
        organization_id=profile.organization_id,
        project_id=None,
        profile_id=profile.id,
        manifest_format=ManifestFormat.HELM_CHART,
        namespace=None,
        name="chart",
        content={"apiVersion": "v2", "name": "chart", "version": "1.0.0"},
    )

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1

    await service.delete(manifest.id)
    with pytest.raises(NotFoundError):
        await service.get_by_id(manifest.id)
