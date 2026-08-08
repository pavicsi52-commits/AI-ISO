"""Repository tests for :mod:`app.repositories.evaluation`,
:mod:`app.repositories.benchmark`, and :mod:`app.repositories.marketplace`.

Covers :class:`AgentEvaluationRepository`, :class:`AgentBenchmarkRepository`,
and :class:`AgentMarketplaceEntryRepository` against real seeded Postgres rows.
"""

from __future__ import annotations

import uuid

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.agent import Agent
from app.models.benchmark import AgentBenchmark
from app.models.enums import (
    AgentLifecycleStatus,
    AgentMarketplaceListingStatus,
    AgentType,
    BenchmarkStatus,
)
from app.models.evaluation import AgentEvaluation
from app.models.execution import AgentExecution
from app.models.marketplace import AgentMarketplaceEntry
from app.repositories.agent import AgentRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.evaluation import AgentEvaluationRepository
from app.repositories.execution import AgentExecutionRepository
from app.repositories.marketplace import AgentMarketplaceEntryRepository
from tests.conftest import ago, soon, utcnow


async def _agent(
    agents_repo: AgentRepository, organization_id: uuid.UUID, *, slug: str = "agent"
) -> Agent:
    return await agents_repo.create(
        Agent(
            organization_id=organization_id,
            slug=slug,
            name=f"Agent {slug}",
            agent_type=AgentType.EXECUTOR,
            status=AgentLifecycleStatus.ACTIVE,
        )
    )


async def _execution(
    executions_repo: AgentExecutionRepository, organization_id: uuid.UUID, agent_id: uuid.UUID
) -> AgentExecution:
    return await executions_repo.create(
        AgentExecution(organization_id=organization_id, agent_id=agent_id, started_at=utcnow())
    )


def _evaluation(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    execution_id: uuid.UUID,
    *,
    evaluated_at=None,
) -> AgentEvaluation:
    return AgentEvaluation(
        organization_id=organization_id,
        agent_id=agent_id,
        execution_id=execution_id,
        evaluated_at=evaluated_at or utcnow(),
    )


def _benchmark(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    name: str = "suite",
    status: BenchmarkStatus = BenchmarkStatus.COMPLETED,
    started_at=None,
) -> AgentBenchmark:
    return AgentBenchmark(
        organization_id=organization_id,
        agent_id=agent_id,
        name=name,
        status=status,
        started_at=started_at or utcnow(),
    )


def _listing(
    organization_id: uuid.UUID,
    agent_id: uuid.UUID,
    *,
    status: AgentMarketplaceListingStatus = AgentMarketplaceListingStatus.DRAFT,
    featured: bool = False,
) -> AgentMarketplaceEntry:
    return AgentMarketplaceEntry(
        organization_id=organization_id, agent_id=agent_id, status=status, featured=featured
    )


# ---- AgentEvaluationRepository.list_for_agent -------------------------------------


async def test_evaluation_list_for_agent_orders_newest_first(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    execution = await _execution(executions_repo, organization_id, agent.id)
    older = await evaluations_repo.create(
        _evaluation(organization_id, agent.id, execution.id, evaluated_at=ago(3600))
    )
    newer = await evaluations_repo.create(
        _evaluation(organization_id, agent.id, execution.id, evaluated_at=soon(3600))
    )

    found = await evaluations_repo.list_for_agent(agent.id)

    assert [e.id for e in found] == [newer.id, older.id]


async def test_evaluation_list_for_agent_scoped_to_agent(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    other_execution = await _execution(executions_repo, organization_id, other_agent.id)
    await evaluations_repo.create(_evaluation(organization_id, other_agent.id, other_execution.id))

    assert await evaluations_repo.list_for_agent(agent.id) == []


# ---- AgentEvaluationRepository.list_for_execution ----------------------------------


async def test_evaluation_list_for_execution_filters_by_execution(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    execution = await _execution(executions_repo, organization_id, agent.id)
    other_execution = await _execution(executions_repo, organization_id, agent.id)
    matching = await evaluations_repo.create(_evaluation(organization_id, agent.id, execution.id))
    await evaluations_repo.create(_evaluation(organization_id, agent.id, other_execution.id))

    found = await evaluations_repo.list_for_execution(execution.id)

    assert [e.id for e in found] == [matching.id]


# ---- AgentEvaluationRepository.list_for_org -----------------------------------------


async def test_evaluation_list_for_org_orders_newest_first_and_paginates(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    execution = await _execution(executions_repo, organization_id, agent.id)
    first = await evaluations_repo.create(
        _evaluation(organization_id, agent.id, execution.id, evaluated_at=ago(30))
    )
    second = await evaluations_repo.create(
        _evaluation(organization_id, agent.id, execution.id, evaluated_at=ago(20))
    )
    third = await evaluations_repo.create(
        _evaluation(organization_id, agent.id, execution.id, evaluated_at=ago(10))
    )

    page1 = await evaluations_repo.list_for_org(organization_id, limit=2, offset=0)
    page2 = await evaluations_repo.list_for_org(organization_id, limit=2, offset=2)

    assert [e.id for e in page1] == [third.id, second.id]
    assert [e.id for e in page2] == [first.id]


async def test_evaluation_list_for_org_scoped_to_org(
    evaluations_repo: AgentEvaluationRepository,
    executions_repo: AgentExecutionRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    other_execution = await _execution(executions_repo, other_org, other_agent.id)
    await evaluations_repo.create(_evaluation(other_org, other_agent.id, other_execution.id))

    assert await evaluations_repo.list_for_org(organization_id) == []


# ---- AgentBenchmarkRepository.list_for_agent ----------------------------------------


async def test_benchmark_list_for_agent_orders_newest_first(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    older = await benchmarks_repo.create(
        _benchmark(organization_id, agent.id, started_at=ago(3600))
    )
    newer = await benchmarks_repo.create(
        _benchmark(organization_id, agent.id, started_at=soon(3600))
    )

    found = await benchmarks_repo.list_for_agent(agent.id)

    assert [b.id for b in found] == [newer.id, older.id]


async def test_benchmark_list_for_agent_scoped_to_agent(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id, slug="alpha")
    other_agent = await _agent(agents_repo, organization_id, slug="beta")
    await benchmarks_repo.create(_benchmark(organization_id, other_agent.id))

    assert await benchmarks_repo.list_for_agent(agent.id) == []


# ---- AgentBenchmarkRepository.list_for_org ------------------------------------------


async def test_benchmark_list_for_org_orders_newest_first_and_paginates(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    agent = await _agent(agents_repo, organization_id)
    first = await benchmarks_repo.create(_benchmark(organization_id, agent.id, started_at=ago(30)))
    second = await benchmarks_repo.create(_benchmark(organization_id, agent.id, started_at=ago(20)))
    third = await benchmarks_repo.create(_benchmark(organization_id, agent.id, started_at=ago(10)))

    page1 = await benchmarks_repo.list_for_org(organization_id, limit=2, offset=0)
    page2 = await benchmarks_repo.list_for_org(organization_id, limit=2, offset=2)

    assert [b.id for b in page1] == [third.id, second.id]
    assert [b.id for b in page2] == [first.id]


async def test_benchmark_list_for_org_scoped_to_org(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    await benchmarks_repo.create(_benchmark(other_org, other_agent.id))

    assert await benchmarks_repo.list_for_org(organization_id) == []


# ---- AgentBenchmarkRepository.list_agent_ids_benchmarked_since ----------------------


async def test_list_agent_ids_benchmarked_since_includes_only_recent(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    since = ago(3600)
    recent_agent = await _agent(agents_repo, organization_id, slug="recent")
    stale_agent = await _agent(agents_repo, organization_id, slug="stale")
    await benchmarks_repo.create(_benchmark(organization_id, recent_agent.id, started_at=ago(60)))
    await benchmarks_repo.create(_benchmark(organization_id, stale_agent.id, started_at=ago(7200)))

    found = await benchmarks_repo.list_agent_ids_benchmarked_since(organization_id, since=since)

    assert found == {recent_agent.id}


async def test_list_agent_ids_benchmarked_since_includes_exact_cutoff(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    since = ago(3600)
    agent = await _agent(agents_repo, organization_id)
    await benchmarks_repo.create(_benchmark(organization_id, agent.id, started_at=since))

    found = await benchmarks_repo.list_agent_ids_benchmarked_since(organization_id, since=since)

    assert found == {agent.id}


async def test_list_agent_ids_benchmarked_since_scoped_to_org(
    benchmarks_repo: AgentBenchmarkRepository, agents_repo: AgentRepository, organization_id
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    await benchmarks_repo.create(_benchmark(other_org, other_agent.id, started_at=ago(60)))

    found = await benchmarks_repo.list_agent_ids_benchmarked_since(organization_id, since=ago(3600))

    assert found == set()


# ---- AgentMarketplaceEntryRepository.require_in_org ---------------------------------


async def test_marketplace_require_in_org_returns_entry(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    entry = await marketplace_repo.create(_listing(organization_id, agent.id))

    found = await marketplace_repo.require_in_org(organization_id, entry.id)

    assert found.id == entry.id


async def test_marketplace_require_in_org_raises_for_other_org(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    entry = await marketplace_repo.create(_listing(organization_id, agent.id))

    with pytest.raises(NotFoundError):
        await marketplace_repo.require_in_org(uuid.uuid4(), entry.id)


async def test_marketplace_require_in_org_raises_for_unknown_id(
    marketplace_repo: AgentMarketplaceEntryRepository, organization_id
):
    with pytest.raises(NotFoundError):
        await marketplace_repo.require_in_org(organization_id, uuid.uuid4())


# ---- AgentMarketplaceEntryRepository.get_for_agent -----------------------------------


async def test_get_for_agent_returns_listing(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)
    entry = await marketplace_repo.create(_listing(organization_id, agent.id))

    found = await marketplace_repo.get_for_agent(agent.id)

    assert found is not None
    assert found.id == entry.id


async def test_get_for_agent_returns_none_when_unlisted(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    agent = await _agent(agents_repo, organization_id)

    assert await marketplace_repo.get_for_agent(agent.id) is None


# ---- AgentMarketplaceEntryRepository.list_published -----------------------------------


async def test_list_published_includes_published_and_featured_only(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    published_agent = await _agent(agents_repo, organization_id, slug="published")
    featured_agent = await _agent(agents_repo, organization_id, slug="featured")
    draft_agent = await _agent(agents_repo, organization_id, slug="draft")
    deprecated_agent = await _agent(agents_repo, organization_id, slug="deprecated")
    removed_agent = await _agent(agents_repo, organization_id, slug="removed")

    published = await marketplace_repo.create(
        _listing(
            organization_id,
            published_agent.id,
            status=AgentMarketplaceListingStatus.PUBLISHED,
            featured=False,
        )
    )
    featured = await marketplace_repo.create(
        _listing(
            organization_id,
            featured_agent.id,
            status=AgentMarketplaceListingStatus.FEATURED,
            featured=True,
        )
    )
    await marketplace_repo.create(
        _listing(organization_id, draft_agent.id, status=AgentMarketplaceListingStatus.DRAFT)
    )
    await marketplace_repo.create(
        _listing(
            organization_id,
            deprecated_agent.id,
            status=AgentMarketplaceListingStatus.DEPRECATED,
        )
    )
    await marketplace_repo.create(
        _listing(organization_id, removed_agent.id, status=AgentMarketplaceListingStatus.REMOVED)
    )

    found = await marketplace_repo.list_published(organization_id)

    assert {e.id for e in found} == {published.id, featured.id}
    # Featured listings sort first.
    assert found[0].id == featured.id


async def test_list_published_scoped_to_org(
    marketplace_repo: AgentMarketplaceEntryRepository,
    agents_repo: AgentRepository,
    organization_id,
):
    other_org = uuid.uuid4()
    other_agent = await _agent(agents_repo, other_org, slug="theirs")
    await marketplace_repo.create(
        _listing(other_org, other_agent.id, status=AgentMarketplaceListingStatus.PUBLISHED)
    )

    assert await marketplace_repo.list_published(organization_id) == []
