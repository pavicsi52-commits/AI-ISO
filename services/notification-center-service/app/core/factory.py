"""Application factory.

Assembles the FastAPI application: configuration, logging, PostgreSQL,
Redis, events, the notification manager and its registered channels, the
JWT verification key, middleware, exception handlers, routers, the
background workers, and Prometheus instrumentation.

**No single top-level prefix covers every router** -- see
``app/api/__init__.py`` for why ``/notifications``, ``/notifications/preferences``,
``/notifications/templates``, ``/notifications/subscriptions``,
``/notifications/channels``, ``/notifications/announcements``, and
``/notifications/dead-letters`` are each mounted at their own path under
the shared ``/notifications`` namespace instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from shared_core.cache.factory import create_cache_framework
from shared_core.cache.settings import CacheSettings
from shared_core.database.factory import create_database_framework
from shared_core.events.factory import create_event_framework
from shared_core.exceptions import register_exception_handlers
from shared_core.logging import configure_logging, get_logger
from shared_core.middleware import (
    LocalizationMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from shared_core.notifications.channels import ChannelRegistry, NotificationMessage
from shared_core.notifications.discord import DiscordChannel
from shared_core.notifications.factory import create_notification_framework
from shared_core.notifications.in_app import InAppChannel, InAppNotificationStore
from shared_core.notifications.manager import NotificationManager
from shared_core.notifications.slack import SlackChannel
from shared_core.notifications.teams import TeamsChannel
from shared_core.notifications.webhook import WebhookChannel
from shared_core.queue.factory import create_queue_framework
from shared_core.scheduler import SchedulerManager
from shared_core.scheduler.factory import create_scheduler_framework
from shared_core.security.cors import CorsConfig, development_cors_config, production_cors_config
from shared_core.validation.middleware import RequestValidationMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    analytics_router,
    announcements_router,
    channels_router,
    deliveries_router,
    health_router,
    notifications_router,
    preferences_router,
    subscriptions_router,
    templates_router,
)
from app.config.keys import load_public_key
from app.config.settings import Settings, get_settings
from app.workers.announcement_expiry import AnnouncementExpiryWorker
from app.workers.digest_sweep import DigestSweepWorker
from app.workers.registrar import (
    register_announcement_expiry_sweep,
    register_digest_sweep,
    register_retry_sweep,
    register_statistics_rollup,
)
from app.workers.retry_sweep import RetrySweepWorker
from app.workers.statistics import StatisticsWorker

logger = get_logger("app.startup")


def _webhook_url_from_metadata(message: NotificationMessage) -> str:
    """Resolve the outbound webhook/Slack/Teams/Discord URL from *message*'s own metadata.

    :class:`~app.services.delivery.DeliveryService` embeds an
    organization's configured webhook URL into ``metadata["webhook_url"]``
    before dispatch (read from :class:`~app.models.channel
    .NotificationChannelConfig`, which is per-organization) -- a static
    resolver bound once at startup could not vary per tenant, so every
    webhook-shaped channel shares this same per-message lookup instead.
    """
    return str(message.metadata.get("webhook_url", ""))


def _register_channels(channels: ChannelRegistry) -> None:
    """Register every channel this service can dispatch to without external provider configuration.

    ``EMAIL`` is registered by `shared_core.notifications.factory
    .create_notification_framework` itself, from `EmailSettings`.
    ``IN_APP`` here only exists so a dispatch to it succeeds -- the
    channel's own :class:`~shared_core.notifications.in_app
    .InAppNotificationStore` is in-memory and discarded; this service's
    own persisted ``notifications``/``notification_deliveries`` tables
    are the actual, durable in-app notification center (docs/055
    "IN-APP NOTIFICATION CENTER"), not `shared_core`'s in-memory
    equivalent. ``SMS``/``MOBILE_PUSH``/``BROWSER_PUSH`` need a concrete
    external provider endpoint docs/055 names no specific vendor for --
    an operator registers those against ``app.state.notification_manager
    .channels`` at deployment time, the same extension point
    `create_notification_framework`'s own docstring already establishes.
    """
    channels.register(InAppChannel(InAppNotificationStore()))
    channels.register(SlackChannel(webhook_url_resolver=_webhook_url_from_metadata))
    channels.register(TeamsChannel(webhook_url_resolver=_webhook_url_from_metadata))
    channels.register(DiscordChannel(webhook_url_resolver=_webhook_url_from_metadata))
    channels.register(WebhookChannel(webhook_url_resolver=_webhook_url_from_metadata))


async def _build_workers(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    settings: Settings,
    notification_manager: NotificationManager,
    publish_event: object,
) -> SchedulerManager | None:
    """Register and start the leader-elected background jobs.

    All four are leader-elected: each is pure database work with no
    per-replica state, so N replicas would be N times the load for an
    identical result -- and concurrent sweeps of the same due retries or
    digest subscribers would race on the same rows.
    """
    if not settings.service.workers_enabled:
        return None

    queue = await create_queue_framework(settings.rabbitmq)
    manager = create_scheduler_framework(
        queue.manager, redis_client, queue_name="notification_service_scheduler_queue"
    )
    register_retry_sweep(
        manager,
        RetrySweepWorker(
            session_factory,
            notification_manager,
            settings.service,
            publish_event=publish_event,  # type: ignore[arg-type]
        ).run_job,
        interval_seconds=settings.service.retry_sweep_seconds,
    )
    register_digest_sweep(
        manager,
        DigestSweepWorker(session_factory, notification_manager, settings.service).run_job,
        interval_seconds=settings.service.digest_sweep_seconds,
    )
    register_statistics_rollup(
        manager,
        StatisticsWorker(
            session_factory, window_hours=settings.service.statistics_window_hours
        ).run_job,
        interval_seconds=settings.service.statistics_rollup_seconds,
    )
    register_announcement_expiry_sweep(
        manager,
        AnnouncementExpiryWorker(session_factory).run_job,
        interval_seconds=settings.service.announcement_expiry_sweep_seconds,
    )
    await manager.start()
    return manager


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    database = await create_database_framework(settings.database)
    app.state.db_engine = database.engine
    app.state.db_session_factory = database.session_factory

    cache = await create_cache_framework(CacheSettings(redis=settings.redis))
    app.state.cache_manager = cache.manager
    app.state.redis_client = cache.client

    events = await create_event_framework(settings.rabbitmq)
    app.state.publish_event = events.manager.publish

    notification_manager = create_notification_framework(email_settings=settings.email)
    _register_channels(notification_manager.channels)
    app.state.notification_manager = notification_manager

    app.state.jwt_public_key = load_public_key(settings.service.jwt_public_key_path)
    app.state.service_settings = settings.service

    scheduler_manager = await _build_workers(
        database.session_factory,
        cache.client,
        settings,
        notification_manager,
        events.manager.publish,
    )
    app.state.scheduler_manager = scheduler_manager

    logger.info(
        "notification-center-service starting up",
        extra={
            "extra_fields": {
                "default_max_attempts": settings.service.default_max_attempts,
                "rate_limit_max_per_user": settings.service.rate_limit_max_per_user,
                "digest_sweep_seconds": settings.service.digest_sweep_seconds,
                "workers_enabled": settings.service.workers_enabled,
                "registered_channels": [str(c) for c in notification_manager.channels.registered_channels()],
            }
        },
    )
    try:
        yield
    finally:
        if scheduler_manager is not None:
            await scheduler_manager.stop()
        await database.shutdown()
        await cache.shutdown()
        await events.shutdown()
        logger.info("notification-center-service shutting down")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(
        service=settings.application.app_name,
        environment=settings.application.environment,
        level=settings.application.log_level,
    )

    app = FastAPI(
        title="AI-IOS Enterprise Notification Center Service",
        description=(
            "Centralized, persisted, multi-channel notification delivery -- "
            "templates, localization, preferences, subscriptions, retry "
            "and dead-letter queues, delivery tracking, announcements and "
            "broadcasts, digests, analytics, reports, and an append-only "
            "audit trail. Wraps `shared_core.notifications` (Prompt 025) "
            "rather than redesigning it -- see this package's own README."
        ),
        version=settings.application.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    cors_config = _build_cors_config(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_config.allow_origins),
        allow_methods=list(cors_config.allow_methods),
        allow_headers=list(cors_config.allow_headers),
        allow_credentials=cors_config.allow_credentials,
        max_age=cors_config.max_age_seconds,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(LocalizationMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)

    # `notifications_router` is registered *last*, deliberately. Its own
    # `GET/DELETE /{notification_id}` (and the `/{notification_id}/...`
    # lifecycle routes) match any single path segment under
    # `/notifications/` -- FastAPI/Starlette resolve routes in
    # registration order, so had it been registered first, that catch-all
    # would have intercepted `GET /notifications/preferences`,
    # `/templates`, `/subscriptions`, `/channels`, `/announcements`,
    # `/dead-letters`, `/statistics`, `/reports`, and `/audit` before any
    # of those routers' own literal routes were ever tried (a UUID path
    # conversion failure on e.g. "preferences", surfaced as a 400 instead
    # of reaching the intended router at all). Every other router's own
    # literal sub-paths are never a real notification id, so trying them
    # first is always correct and this reordering changes no other route's
    # behaviour.
    app.include_router(health_router)
    app.include_router(preferences_router)
    app.include_router(templates_router)
    app.include_router(subscriptions_router)
    app.include_router(channels_router)
    app.include_router(announcements_router)
    app.include_router(deliveries_router)
    app.include_router(analytics_router)
    app.include_router(notifications_router)

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)

    return app


def _build_cors_config(settings: Settings) -> CorsConfig:
    """Build the CORS policy for the current environment."""
    if settings.application.environment.value == "production":
        return production_cors_config(settings.service.cors_allowed_origins)
    return development_cors_config()


__all__ = ["create_app"]
