"""Knowledge graph service settings.

Composes ``shared_core.config``'s aggregate settings with the fields
specific to this service: host/port, CORS, JWT verification key, the
base URLs of every platform service the graph synchronises *from*, plus
the Neo4j, traversal, analytics, and import/export knobs.

**Two databases, and the split is deliberate.** Neo4j holds the graph
-- nodes and relationships. PostgreSQL holds everything *about* the
graph: sync jobs, versions, snapshots, saved queries, change history,
statistics, and audit. Putting job state in Neo4j would mean a
transactional bookkeeping workload inside a database tuned for
traversal, and it would make "which sync runs failed last night?" a
Cypher query.

**Every traversal is bounded twice, by depth and by node count.** Graph
traversal grows exponentially; an unbounded blast-radius query on a
large estate is an outage, not an analysis. The ceilings live here so
an operator can lower them without a deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared_core.config.cache import get_settings as get_shared_settings
from shared_core.config.settings import (
    ApplicationSettings,
    DatabaseSettings,
    EmailSettings,
    Neo4jSettings,
    RabbitMQSettings,
    RedisSettings,
)

from app.cypher.builder import MAX_LIMIT_CEILING


class KnowledgeGraphServiceSettings(BaseSettings):
    """Fields specific to this service, not covered by any shared_core section."""

    model_config = SettingsConfigDict(
        env_prefix="AIIOS_KNOWLEDGE_GRAPH_SERVICE_", env_file=".env", extra="ignore"
    )

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8020, ge=1, le=65_535)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    jwt_public_key_path: str = Field(default="keys/jwt_public_key.pem")

    # Synchronization sources ("GRAPH SYNCHRONIZATION").
    inventory_service_base_url: str = Field(default="http://localhost:8007")
    discovery_service_base_url: str = Field(default="http://localhost:8008")
    administration_service_base_url: str = Field(default="http://localhost:8009")
    configuration_service_base_url: str = Field(default="http://localhost:8010")
    automation_service_base_url: str = Field(default="http://localhost:8011")
    workflow_runtime_service_base_url: str = Field(default="http://localhost:8013")
    validation_service_base_url: str = Field(default="http://localhost:8014")
    monitoring_service_base_url: str = Field(default="http://localhost:8015")
    alerting_service_base_url: str = Field(default="http://localhost:8016")
    ai_assistant_service_base_url: str = Field(default="http://localhost:8017")
    reporting_service_base_url: str = Field(default="http://localhost:8018")

    http_client_timeout_seconds: float = Field(default=60.0, gt=0)

    # Neo4j.
    neo4j_database: str = Field(default="neo4j")
    neo4j_enabled: bool = Field(default=True)
    neo4j_max_connection_pool_size: int = Field(default=50, ge=1)
    neo4j_connection_timeout_seconds: float = Field(default=30.0, gt=0)

    # Traversal ceilings ("PERFORMANCE").
    max_traversal_depth: int = Field(default=6, ge=1, le=15)
    """Depth ceiling for any traversal.

    Cypher cannot parameterise a variable-length range literal, so depth
    is the one value formatted into query text -- always after
    :func:`app.cypher.builder.validate_depth` has proven it a bounded
    integer. That validation is what keeps the interpolation safe.
    """

    max_result_nodes: int = Field(default=5_000, ge=1)
    """Node ceiling for any traversal result.

    A graph that hits it comes back flagged ``truncated`` rather than
    silently short, so a caller knows they are looking at a partial
    picture.
    """

    max_parallel_traversals: int = Field(default=4, ge=1)
    """Bound on concurrent *Neo4j* traversals.

    Neo4j sessions are independent, so these are safe to overlap.
    Nothing here touches an ``AsyncSession`` concurrently -- that is not
    safe even for reads.
    """

    query_timeout_seconds: float = Field(default=30.0, gt=0)

    # Custom Cypher ("SECURITY").
    allow_custom_cypher: bool = Field(default=True)
    """Whether ``POST /graph/cypher`` accepts caller-authored Cypher.

    Even when enabled, submitted Cypher is **read-only enforced**: any
    write clause is refused before execution, and every value must
    arrive as a bound parameter. A deployment that wants no custom
    Cypher at all turns this off rather than relying on that check.
    """

    # Synchronization.
    sync_service_token: str = Field(default="")
    """The bearer token synchronization reads source services with.

    A sync runs unattended at 03:00, so there is no caller token to
    forward -- unlike every read path in
    ``services/dashboard-service``. Empty by default so a deployment
    that has not configured one gets an honest 401 from each source
    rather than a silent half-populated graph.
    """

    sync_enabled: bool = Field(default=True)
    sync_poll_seconds: int = Field(default=300, ge=30, le=86_400)
    sync_batch_size: int = Field(default=500, ge=1, le=10_000)
    sync_max_failures: int = Field(default=5, ge=1)
    """Consecutive failures before a source's sync is disabled.

    Retrying a permanently broken source every five minutes forever
    fills the log and hides the real problem.
    """

    # Analytics ("GRAPH ANALYTICS").
    analytics_max_nodes: int = Field(default=10_000, ge=1, le=MAX_LIMIT_CEILING)
    """Node ceiling for a centrality or community computation.

    Betweenness is O(V*E); running it unbounded on a large estate would
    pin a core for minutes. Above the ceiling the request is refused
    with the actual size, rather than accepted and left to time out.

    Bounded by :data:`~app.cypher.builder.MAX_LIMIT_CEILING` because
    these algorithms need the whole graph in one read, and a single
    Cypher read cannot return more rows than that. Configuring a higher
    number never bought a larger analysis -- it only made every
    analytics and statistics call fail on its own read limit, which is
    what the default of 20,000 was quietly doing.
    """

    pagerank_iterations: int = Field(default=20, ge=1, le=200)
    pagerank_damping: float = Field(default=0.85, gt=0.0, lt=1.0)

    # Snapshots and import/export.
    snapshot_enabled: bool = Field(default=True)
    snapshot_retention_days: int = Field(default=90, ge=1)
    max_import_nodes: int = Field(default=50_000, ge=1)
    max_export_nodes: int = Field(default=50_000, ge=1)

    # Statistics rollup (leader-elected).
    scheduler_enabled: bool = Field(default=True)
    statistics_rollup_seconds: int = Field(default=900, ge=60, le=86_400)


@dataclass(frozen=True, slots=True)
class Settings:
    """Every configuration section this service actually uses."""

    application: ApplicationSettings
    database: DatabaseSettings
    redis: RedisSettings
    rabbitmq: RabbitMQSettings
    email: EmailSettings
    neo4j: Neo4jSettings
    service: KnowledgeGraphServiceSettings


def build_settings(*, service: KnowledgeGraphServiceSettings | None = None) -> Settings:
    """Build a :class:`Settings`, reusing the shared aggregate's current values."""
    shared = get_shared_settings()
    return Settings(
        application=shared.application,
        database=shared.database,
        redis=shared.redis,
        rabbitmq=shared.rabbitmq,
        email=shared.email,
        neo4j=shared.neo4j,
        service=service if service is not None else KnowledgeGraphServiceSettings(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide cached settings, built once."""
    return build_settings()


__all__ = [
    "KnowledgeGraphServiceSettings",
    "Settings",
    "build_settings",
    "get_settings",
]
