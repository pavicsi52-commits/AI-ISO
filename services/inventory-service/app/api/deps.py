"""FastAPI dependency injection for the inventory service.

One factory function per business service, each building its own
repositories from the request-scoped database session -- routes depend
on services only, never repositories directly, keeping DB session and
Neo4j driver management entirely inside this module. Matches
``services/project-service/app/api/deps.py``'s established shape, with
the addition of :func:`get_topology_graph_client` since this is the
first AI-IOS service that talks to Neo4j.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from neo4j import AsyncDriver
from shared_core.database.session import session_scope
from shared_core.exceptions.authentication import AuthenticationError
from shared_core.notifications.manager import NotificationManager
from shared_core.queue.producer import Producer
from shared_core.security.jwt import decode_token
from shared_core.storage import StorageWrapper
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.inventory_notifications import InventoryNotificationService
from app.repositories.asset import AssetRepository
from app.repositories.asset_attribute import AssetAttributeRepository
from app.repositories.asset_category import AssetCategoryRepository
from app.repositories.asset_class import AssetClassRepository
from app.repositories.asset_contact import AssetContactRepository
from app.repositories.asset_custom_field import AssetCustomFieldRepository
from app.repositories.asset_discovery_link import AssetDiscoveryLinkRepository
from app.repositories.asset_export_job import AssetExportJobRepository
from app.repositories.asset_group import AssetGroupRepository
from app.repositories.asset_health_history import AssetHealthHistoryRepository
from app.repositories.asset_history import AssetHistoryRepository
from app.repositories.asset_import_job import AssetImportJobRepository
from app.repositories.asset_label import AssetLabelRepository
from app.repositories.asset_lifecycle_history import AssetLifecycleHistoryRepository
from app.repositories.asset_location import AssetLocationRepository
from app.repositories.asset_metadata import AssetMetadataRepository
from app.repositories.asset_owner import AssetOwnerRepository
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.repositories.asset_status_history import AssetStatusHistoryRepository
from app.repositories.asset_tag import AssetTagRepository
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.repositories.asset_type import AssetTypeDefinitionRepository
from app.repositories.asset_version import AssetVersionRepository
from app.repositories.inventory_audit import InventoryAuditRepository
from app.repositories.inventory_statistics import InventoryStatisticsRepository
from app.services.asset import AssetService
from app.services.asset_class import AssetClassService
from app.services.asset_type import AssetTypeDefinitionService
from app.services.attribute import AssetAttributeService
from app.services.audit import InventoryAuditService
from app.services.category import AssetCategoryService
from app.services.contact import AssetContactService
from app.services.custom_field import AssetCustomFieldService
from app.services.discovery_link import AssetDiscoveryLinkService
from app.services.export_service import AssetExportService
from app.services.group import AssetGroupService
from app.services.health_history import AssetHealthHistoryService
from app.services.history import AssetHistoryService
from app.services.import_service import AssetImportService
from app.services.label import AssetLabelService
from app.services.lifecycle_history import AssetLifecycleHistoryService
from app.services.location import AssetLocationService
from app.services.metadata import AssetMetadataService
from app.services.owner import AssetOwnerService
from app.services.relationship import AssetRelationshipService
from app.services.statistics import InventoryStatisticsService
from app.services.status_history import AssetStatusHistoryService
from app.services.tag import AssetTagService
from app.services.topology import TopologyService
from app.services.version import AssetVersionService
from app.topology.graph import TopologyGraphClient

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session, committing on success.

    Per docs/018 "Transaction Session" -- see the identical rationale in
    every prior AI-IOS service's own ``get_db_session``.
    """
    session_factory = request.app.state.db_session_factory
    async with session_scope(session_factory) as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_neo4j_driver(request: Request) -> AsyncDriver:
    """The process-wide Neo4j :class:`~neo4j.AsyncDriver`."""
    return request.app.state.neo4j_driver  # type: ignore[no-any-return]


def get_topology_graph_client(
    driver: Annotated[AsyncDriver, Depends(get_neo4j_driver)],
) -> TopologyGraphClient:
    """The current request's :class:`TopologyGraphClient`."""
    return TopologyGraphClient(driver)


def get_notification_manager(request: Request) -> NotificationManager:
    """The process-wide :class:`NotificationManager`."""
    return request.app.state.notification_manager  # type: ignore[no-any-return]


def get_minio_client(request: Request) -> Minio:
    """The process-wide MinIO client."""
    return request.app.state.minio_client  # type: ignore[no-any-return]


def get_storage_wrapper(client: Annotated[Minio, Depends(get_minio_client)]) -> StorageWrapper:
    """The current request's :class:`StorageWrapper`."""
    return StorageWrapper(client)


def get_queue_producer(request: Request) -> Producer:
    """The process-wide queue :class:`Producer`, for enqueueing import/export jobs."""
    return request.app.state.queue_producer  # type: ignore[no-any-return]


async def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UUID:
    """Resolve the calling user's id from a Bearer token issued by
    ``services/authentication-service``.

    Raises:
        AuthenticationError: If no valid Bearer token is presented.
    """
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    public_key = request.app.state.jwt_public_key
    claims = decode_token(credentials.credentials, public_key=public_key)
    return UUID(str(claims["sub"]))


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_notification_service(
    manager: Annotated[NotificationManager, Depends(get_notification_manager)],
) -> InventoryNotificationService:
    """The current request's :class:`InventoryNotificationService`."""
    return InventoryNotificationService(manager)


def get_category_service(session: DbSession) -> AssetCategoryService:
    """The current request's :class:`AssetCategoryService`."""
    return AssetCategoryService(AssetCategoryRepository(session))


CategorySvc = Annotated[AssetCategoryService, Depends(get_category_service)]


def get_class_service(session: DbSession) -> AssetClassService:
    """The current request's :class:`AssetClassService`."""
    return AssetClassService(AssetClassRepository(session))


ClassSvc = Annotated[AssetClassService, Depends(get_class_service)]


def get_asset_type_service(session: DbSession) -> AssetTypeDefinitionService:
    """The current request's :class:`AssetTypeDefinitionService`."""
    return AssetTypeDefinitionService(AssetTypeDefinitionRepository(session))


AssetTypeSvc = Annotated[AssetTypeDefinitionService, Depends(get_asset_type_service)]


def get_tag_service(session: DbSession) -> AssetTagService:
    """The current request's :class:`AssetTagService`."""
    return AssetTagService(AssetTagRepository(session))


TagSvc = Annotated[AssetTagService, Depends(get_tag_service)]


def get_label_service(session: DbSession) -> AssetLabelService:
    """The current request's :class:`AssetLabelService`."""
    return AssetLabelService(AssetLabelRepository(session))


LabelSvc = Annotated[AssetLabelService, Depends(get_label_service)]


def get_location_service(session: DbSession) -> AssetLocationService:
    """The current request's :class:`AssetLocationService`."""
    return AssetLocationService(AssetLocationRepository(session))


LocationSvc = Annotated[AssetLocationService, Depends(get_location_service)]


def get_owner_service(session: DbSession) -> AssetOwnerService:
    """The current request's :class:`AssetOwnerService`."""
    return AssetOwnerService(AssetOwnerRepository(session))


OwnerSvc = Annotated[AssetOwnerService, Depends(get_owner_service)]


def get_contact_service(session: DbSession) -> AssetContactService:
    """The current request's :class:`AssetContactService`."""
    return AssetContactService(AssetContactRepository(session))


ContactSvc = Annotated[AssetContactService, Depends(get_contact_service)]


def get_metadata_service(session: DbSession) -> AssetMetadataService:
    """The current request's :class:`AssetMetadataService`."""
    return AssetMetadataService(AssetMetadataRepository(session))


MetadataSvc = Annotated[AssetMetadataService, Depends(get_metadata_service)]


def get_custom_field_service(session: DbSession) -> AssetCustomFieldService:
    """The current request's :class:`AssetCustomFieldService`."""
    return AssetCustomFieldService(AssetCustomFieldRepository(session))


CustomFieldSvc = Annotated[AssetCustomFieldService, Depends(get_custom_field_service)]


def get_attribute_service(session: DbSession) -> AssetAttributeService:
    """The current request's :class:`AssetAttributeService`."""
    return AssetAttributeService(
        AssetAttributeRepository(session), AssetCustomFieldRepository(session)
    )


AttributeSvc = Annotated[AssetAttributeService, Depends(get_attribute_service)]


def get_discovery_link_service(session: DbSession) -> AssetDiscoveryLinkService:
    """The current request's :class:`AssetDiscoveryLinkService`."""
    return AssetDiscoveryLinkService(AssetDiscoveryLinkRepository(session))


DiscoveryLinkSvc = Annotated[AssetDiscoveryLinkService, Depends(get_discovery_link_service)]


def get_status_history_service(session: DbSession) -> AssetStatusHistoryService:
    """The current request's :class:`AssetStatusHistoryService`."""
    return AssetStatusHistoryService(AssetStatusHistoryRepository(session))


StatusHistorySvc = Annotated[AssetStatusHistoryService, Depends(get_status_history_service)]


def get_health_history_service(session: DbSession) -> AssetHealthHistoryService:
    """The current request's :class:`AssetHealthHistoryService`."""
    return AssetHealthHistoryService(AssetHealthHistoryRepository(session))


HealthHistorySvc = Annotated[AssetHealthHistoryService, Depends(get_health_history_service)]


def get_lifecycle_history_service(session: DbSession) -> AssetLifecycleHistoryService:
    """The current request's :class:`AssetLifecycleHistoryService`."""
    return AssetLifecycleHistoryService(AssetLifecycleHistoryRepository(session))


LifecycleHistorySvc = Annotated[
    AssetLifecycleHistoryService, Depends(get_lifecycle_history_service)
]


def get_history_service(session: DbSession) -> AssetHistoryService:
    """The current request's :class:`AssetHistoryService`."""
    return AssetHistoryService(AssetHistoryRepository(session))


HistorySvc = Annotated[AssetHistoryService, Depends(get_history_service)]


def get_audit_service(session: DbSession) -> InventoryAuditService:
    """The current request's :class:`InventoryAuditService`."""
    return InventoryAuditService(InventoryAuditRepository(session))


AuditSvc = Annotated[InventoryAuditService, Depends(get_audit_service)]


def get_version_service(session: DbSession) -> AssetVersionService:
    """The current request's :class:`AssetVersionService`."""
    return AssetVersionService(AssetVersionRepository(session))


VersionSvc = Annotated[AssetVersionService, Depends(get_version_service)]


def get_topology_service(
    session: DbSession, graph: Annotated[TopologyGraphClient, Depends(get_topology_graph_client)]
) -> TopologyService:
    """The current request's :class:`TopologyService`."""
    return TopologyService(graph, AssetTopologyCacheRepository(session))


TopologySvc = Annotated[TopologyService, Depends(get_topology_service)]


def get_asset_service(
    request: Request,
    session: DbSession,
    versions: VersionSvc,
    tags: TagSvc,
    status_history: StatusHistorySvc,
    health_history: HealthHistorySvc,
    lifecycle_history: LifecycleHistorySvc,
    history: HistorySvc,
    audit: AuditSvc,
    topology: TopologySvc,
) -> AssetService:
    """The current request's fully-wired :class:`AssetService`."""
    return AssetService(
        AssetRepository(session),
        versions,
        tags,
        status_history,
        health_history,
        lifecycle_history,
        history,
        audit,
        topology,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


AssetSvc = Annotated[AssetService, Depends(get_asset_service)]


def get_relationship_service(
    request: Request, session: DbSession, topology: TopologySvc
) -> AssetRelationshipService:
    """The current request's fully-wired :class:`AssetRelationshipService`."""
    return AssetRelationshipService(
        AssetRelationshipRepository(session),
        topology,
        publish_event=getattr(request.app.state, "publish_event", None),
    )


RelationshipSvc = Annotated[AssetRelationshipService, Depends(get_relationship_service)]


def get_group_service(session: DbSession) -> AssetGroupService:
    """The current request's :class:`AssetGroupService`."""
    return AssetGroupService(AssetGroupRepository(session), AssetRepository(session))


GroupSvc = Annotated[AssetGroupService, Depends(get_group_service)]


def get_statistics_service(session: DbSession) -> InventoryStatisticsService:
    """The current request's :class:`InventoryStatisticsService`."""
    return InventoryStatisticsService(
        InventoryStatisticsRepository(session),
        AssetRepository(session),
        AssetRelationshipRepository(session),
        AssetDiscoveryLinkRepository(session),
    )


StatisticsSvc = Annotated[InventoryStatisticsService, Depends(get_statistics_service)]


def get_import_service(
    session: DbSession,
    assets: AssetSvc,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
    request: Request,
) -> AssetImportService:
    """The current request's fully-wired :class:`AssetImportService`."""
    settings = request.app.state.service_settings
    return AssetImportService(
        AssetImportJobRepository(session),
        assets,
        storage,
        session,
        bucket=settings.import_export_bucket,
    )


ImportSvc = Annotated[AssetImportService, Depends(get_import_service)]


def get_export_service(
    session: DbSession,
    storage: Annotated[StorageWrapper, Depends(get_storage_wrapper)],
    request: Request,
) -> AssetExportService:
    """The current request's fully-wired :class:`AssetExportService`."""
    settings = request.app.state.service_settings
    return AssetExportService(
        AssetExportJobRepository(session),
        AssetRepository(session),
        AssetTagRepository(session),
        storage,
        session,
        bucket=settings.import_export_bucket,
    )


ExportSvc = Annotated[AssetExportService, Depends(get_export_service)]

__all__ = [
    "AssetSvc",
    "AssetTypeSvc",
    "AttributeSvc",
    "AuditSvc",
    "CategorySvc",
    "ClassSvc",
    "ContactSvc",
    "CurrentUserId",
    "CustomFieldSvc",
    "DbSession",
    "DiscoveryLinkSvc",
    "ExportSvc",
    "GroupSvc",
    "HealthHistorySvc",
    "HistorySvc",
    "ImportSvc",
    "LabelSvc",
    "LifecycleHistorySvc",
    "LocationSvc",
    "MetadataSvc",
    "OwnerSvc",
    "RelationshipSvc",
    "StatisticsSvc",
    "StatusHistorySvc",
    "TagSvc",
    "TopologySvc",
    "VersionSvc",
    "get_asset_service",
    "get_asset_type_service",
    "get_attribute_service",
    "get_audit_service",
    "get_category_service",
    "get_class_service",
    "get_contact_service",
    "get_current_user_id",
    "get_custom_field_service",
    "get_db_session",
    "get_discovery_link_service",
    "get_export_service",
    "get_group_service",
    "get_health_history_service",
    "get_history_service",
    "get_import_service",
    "get_label_service",
    "get_lifecycle_history_service",
    "get_location_service",
    "get_metadata_service",
    "get_minio_client",
    "get_neo4j_driver",
    "get_notification_manager",
    "get_notification_service",
    "get_owner_service",
    "get_queue_producer",
    "get_relationship_service",
    "get_statistics_service",
    "get_status_history_service",
    "get_storage_wrapper",
    "get_tag_service",
    "get_topology_graph_client",
    "get_topology_service",
    "get_version_service",
]
