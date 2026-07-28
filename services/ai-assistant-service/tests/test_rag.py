"""RAG pipeline tests against real Postgres and real pgvector.

These exercise genuine ``vector(1536)`` columns and the ``<=>`` cosine
operator -- not a stubbed similarity function -- because the whole
reason this platform ships ``pgvector/pgvector:pg17`` is to have real
indexed nearest-neighbour search.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pytest_httpx import HTTPXMock
from shared_core.exceptions.ai import AIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client import EmbeddingClient
from app.embeddings.encoder import HashingEncoder
from app.models.ai_embedding import EMBEDDING_DIMENSIONS
from app.models.enums import DocumentSourceType, RetrievalStrategy
from app.rag.pipeline import RagPipeline
from app.repositories.ai_chunk import AiChunkRepository
from app.repositories.ai_document import AiDocumentRepository
from app.repositories.ai_embedding import AiEmbeddingRepository
from app.repositories.ai_retrieval_history import AiRetrievalHistoryRepository
from tests.conftest import make_conversation


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def _pipeline(db_session: AsyncSession, *, chunk_size: int = 200) -> RagPipeline:
    return RagPipeline(
        AiDocumentRepository(db_session),
        AiChunkRepository(db_session),
        AiEmbeddingRepository(db_session),
        AiRetrievalHistoryRepository(db_session),
        HashingEncoder(EMBEDDING_DIMENSIONS),
        embedding_client=None,
        embedding_provider="local",
        embedding_model="local-hashing",
        chunk_size=chunk_size,
        chunk_overlap=40,
    )


async def _seed(pipeline: RagPipeline, organization_id: uuid.UUID) -> None:
    documents = [
        (
            "rb-db",
            "Database Runbook",
            DocumentSourceType.RUNBOOKS,
            "Restart the postgres database on host db-1 using systemctl. "
            "Verify replication lag afterwards.",
        ),
        (
            "rb-lb",
            "Load Balancer Runbook",
            DocumentSourceType.RUNBOOKS,
            "Rotate TLS certificates on the load balancer every 90 days using certbot.",
        ),
        (
            "pol-1",
            "Change Policy",
            DocumentSourceType.POLICIES,
            "All production changes require change-approval sign off before deployment.",
        ),
    ]
    for external_id, title, source_type, text in documents:
        await pipeline.ingest(
            organization_id=organization_id,
            project_id=None,
            source_type=source_type,
            title=title,
            text=text,
            external_id=external_id,
        )


class TestIngestion:
    async def test_ingest_creates_chunks_and_embeddings(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        result = await pipeline.ingest(
            organization_id=org,
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook",
            text="Restart the postgres database on host db-1.",
        )
        assert result.chunks_created == 1
        assert not result.skipped_unchanged

        chunks = await AiChunkRepository(db_session).list_for_document(result.document.id)
        assert len(chunks) == 1
        embeddings = await AiEmbeddingRepository(db_session).list_for_chunk(chunks[0].id)
        assert len(embeddings) == 1
        assert len(embeddings[0].vector) == EMBEDDING_DIMENSIONS

    async def test_unchanged_content_is_skipped(self, db_session: AsyncSession) -> None:
        """Incremental indexing: the dominant cost of any repeated sync."""
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        text = "Restart the postgres database on host db-1."

        first = await pipeline.ingest(
            organization_id=org,
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook",
            text=text,
            external_id="rb-1",
        )
        second = await pipeline.ingest(
            organization_id=org,
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook",
            text=text,
            external_id="rb-1",
        )
        assert second.skipped_unchanged
        assert second.chunks_created == 0
        assert second.document.id == first.document.id

    async def test_changed_content_purges_stale_chunks(self, db_session: AsyncSession) -> None:
        """Retrieval must never rank against text that no longer exists."""
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await pipeline.ingest(
            organization_id=org,
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook",
            text="Restart the postgres database on host db-1.",
            external_id="rb-1",
        )
        await pipeline.ingest(
            organization_id=org,
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook v2",
            text="Drain the kubernetes node before maintenance.",
            external_id="rb-1",
        )
        hits = await pipeline.retrieve(
            org, "postgres", top_k=10, strategy=RetrievalStrategy.KEYWORD
        )
        assert all("postgres" not in hit.content for hit in hits)

    async def test_empty_document_creates_no_chunks(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        result = await pipeline.ingest(
            organization_id=uuid.uuid4(),
            project_id=None,
            source_type=DocumentSourceType.UPLOADED,
            title="Empty",
            text="   ",
        )
        assert result.chunks_created == 0

    async def test_long_document_creates_several_chunks(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session, chunk_size=120)
        result = await pipeline.ingest(
            organization_id=uuid.uuid4(),
            project_id=None,
            source_type=DocumentSourceType.DOCUMENTATION,
            title="Long",
            text=". ".join(f"Sentence number {index} about infrastructure" for index in range(20)),
        )
        assert result.chunks_created > 1


class TestRetrieval:
    @pytest.mark.parametrize(
        "strategy",
        [RetrievalStrategy.VECTOR, RetrievalStrategy.KEYWORD, RetrievalStrategy.HYBRID],
    )
    async def test_every_strategy_finds_the_right_document(
        self, db_session: AsyncSession, strategy: RetrievalStrategy
    ) -> None:
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await _seed(pipeline, org)

        hits = await pipeline.retrieve(org, "restart postgres on db-1", top_k=3, strategy=strategy)
        assert hits
        assert hits[0].document_title == "Database Runbook"

    async def test_results_are_ranked_descending(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await _seed(pipeline, org)

        hits = await pipeline.retrieve(
            org, "restart postgres database", top_k=3, strategy=RetrievalStrategy.HYBRID
        )
        scores = [hit.score for hit in hits]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.parametrize(
        "strategy",
        [RetrievalStrategy.VECTOR, RetrievalStrategy.KEYWORD, RetrievalStrategy.HYBRID],
    )
    async def test_metadata_filter_applies_to_every_strategy(
        self, db_session: AsyncSession, strategy: RetrievalStrategy
    ) -> None:
        """A real bug once let keyword hits bypass the source filter."""
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await _seed(pipeline, org)

        hits = await pipeline.retrieve(
            org,
            "change approval production",
            top_k=5,
            strategy=strategy,
            source_types=[DocumentSourceType.POLICIES],
        )
        assert all(hit.document_title == "Change Policy" for hit in hits)

    async def test_retrieval_is_tenant_scoped(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        mine, theirs = uuid.uuid4(), uuid.uuid4()
        await _seed(pipeline, theirs)

        hits = await pipeline.retrieve(
            mine, "restart postgres", top_k=5, strategy=RetrievalStrategy.HYBRID
        )
        assert hits == []

    async def test_retrieval_is_recorded_for_audit(self, db_session: AsyncSession) -> None:
        """ "Why did the assistant say that?" must stay answerable.

        Uses a *real* conversation row: ``conversation_id`` is a genuine
        foreign key, so a fabricated id correctly fails rather than
        silently recording orphaned history.
        """
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        conversation = await make_conversation(db_session, organization_id=org)
        await _seed(pipeline, org)

        await pipeline.retrieve(
            org,
            "restart postgres",
            top_k=2,
            strategy=RetrievalStrategy.HYBRID,
            conversation_id=conversation.id,
        )
        history = await AiRetrievalHistoryRepository(db_session).list_for_conversation(
            conversation.id
        )
        assert len(history) == 1
        assert history[0].query == "restart postgres"
        assert history[0].duration_ms is not None

    async def test_citations_carry_what_a_reader_needs(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await _seed(pipeline, org)

        hits = await pipeline.retrieve(
            org, "restart postgres", top_k=1, strategy=RetrievalStrategy.VECTOR
        )
        citation = hits[0].as_citation()
        assert set(citation) == {"chunk_id", "document_id", "title", "uri", "score"}
        assert citation["title"] == "Database Runbook"

    async def test_unrelated_query_scores_low(self, db_session: AsyncSession) -> None:
        pipeline = _pipeline(db_session)
        org = uuid.uuid4()
        await _seed(pipeline, org)

        hits = await pipeline.retrieve(
            org,
            "quarterly marketing budget projections",
            top_k=3,
            strategy=RetrievalStrategy.VECTOR,
        )
        assert all(hit.score < 0.3 for hit in hits)


class TestProviderEmbeddings:
    """The provider-backed embedding path, distinct from the offline encoder."""

    def _pipeline_with_provider(
        self, db_session: AsyncSession, http_client: httpx.AsyncClient
    ) -> RagPipeline:
        return RagPipeline(
            AiDocumentRepository(db_session),
            AiChunkRepository(db_session),
            AiEmbeddingRepository(db_session),
            AiRetrievalHistoryRepository(db_session),
            HashingEncoder(EMBEDDING_DIMENSIONS),
            embedding_client=EmbeddingClient(
                http_client,
                base_url="https://api.openai.test/v1",
                api_key="sk-test",
                provider="openai",
            ),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            chunk_size=400,
            chunk_overlap=40,
        )

    async def test_provider_vectors_are_stored(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        vector = [0.01] * EMBEDDING_DIMENSIONS
        httpx_mock.add_response(json={"data": [{"index": 0, "embedding": vector}]})

        pipeline = self._pipeline_with_provider(db_session, http_client)
        result = await pipeline.ingest(
            organization_id=uuid.uuid4(),
            project_id=None,
            source_type=DocumentSourceType.RUNBOOKS,
            title="Runbook",
            text="Restart the postgres database on host db-1.",
        )
        assert result.chunks_created == 1
        chunks = await AiChunkRepository(db_session).list_for_document(result.document.id)
        stored = await AiEmbeddingRepository(db_session).list_for_chunk(chunks[0].id)
        assert stored[0].provider == "openai"
        assert stored[0].model == "text-embedding-3-small"

    async def test_wrong_width_is_rejected_loudly(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        """Storing a mis-sized vector would corrupt the shared index."""
        httpx_mock.add_response(json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

        pipeline = self._pipeline_with_provider(db_session, http_client)
        with pytest.raises(AIError, match="3-dimensional"):
            await pipeline.ingest(
                organization_id=uuid.uuid4(),
                project_id=None,
                source_type=DocumentSourceType.RUNBOOKS,
                title="Runbook",
                text="Restart the postgres database on host db-1.",
            )

    async def test_provider_failure_propagates(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock, http_client: httpx.AsyncClient
    ) -> None:
        httpx_mock.add_response(status_code=429, json={})
        pipeline = self._pipeline_with_provider(db_session, http_client)
        with pytest.raises(AIError):
            await pipeline.ingest(
                organization_id=uuid.uuid4(),
                project_id=None,
                source_type=DocumentSourceType.RUNBOOKS,
                title="Runbook",
                text="Restart the postgres database.",
            )
