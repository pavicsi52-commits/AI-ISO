"""``/ai/knowledge`` -- document ingestion and RAG search.

Added beyond docs/046's own literal REST list: "RAG Pipeline" and
"Embedding Pipeline" are explicit ACCEPTANCE CRITERIA, and without
these endpoints there is no way to put a document into the knowledge
base or to inspect what retrieval actually returns.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, DbSession, RagDep
from app.models.ai_document import AiDocument
from app.repositories.ai_document import AiDocumentRepository
from app.schemas.knowledge import (
    DocumentIngestRequest,
    DocumentIngestResponse,
    DocumentResponse,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/ai/knowledge", tags=["AI Knowledge"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def document_to_response(document: AiDocument) -> DocumentResponse:
    """Map a document row onto its own response schema."""
    return DocumentResponse(
        id=document.id,
        organization_id=document.organization_id,
        source_type=document.source_type,
        external_id=document.external_id,
        title=document.title,
        uri=document.uri,
        content_hash=document.content_hash,
        document_metadata=document.document_metadata,
    )


@router.post("/documents", response_model=SuccessResponse[DocumentIngestResponse], status_code=201)
async def ingest_document(
    body: DocumentIngestRequest, rag: RagDep, _caller: CurrentUserId
) -> SuccessResponse[DocumentIngestResponse]:
    """Ingest one document into the knowledge base.

    Re-ingesting unchanged content is a no-op that reports
    ``skipped_unchanged`` rather than re-embedding it.

    Raises:
        AIError: If the configured embedding provider fails or returns
            vectors of the wrong width.
    """
    result = await rag.ingest(
        organization_id=body.organization_id,
        project_id=body.project_id,
        source_type=body.source_type,
        title=body.title,
        text=body.text,
        external_id=body.external_id,
        uri=body.uri,
        document_metadata=body.document_metadata,
    )
    return SuccessResponse(
        message=(
            "Document unchanged; indexing skipped."
            if result.skipped_unchanged
            else "Document ingested."
        ),
        data=DocumentIngestResponse(
            document_id=result.document.id,
            title=result.document.title,
            chunks_created=result.chunks_created,
            skipped_unchanged=result.skipped_unchanged,
        ),
        meta=_meta(),
    )


@router.get("/documents", response_model=SuccessResponse[list[DocumentResponse]])
async def list_documents(
    organization_id: UUID, session: DbSession, _caller: CurrentUserId
) -> SuccessResponse[list[DocumentResponse]]:
    """Every document ingested for an organization."""
    records = await AiDocumentRepository(session).list_for_org(organization_id)
    return SuccessResponse(
        message="Documents retrieved.",
        data=[document_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/search", response_model=SuccessResponse[list[KnowledgeSearchHit]])
async def search_knowledge(
    body: KnowledgeSearchRequest, rag: RagDep, _caller: CurrentUserId
) -> SuccessResponse[list[KnowledgeSearchHit]]:
    """Retrieve passages relevant to a query.

    Exposes the retrieval half of RAG directly, which is what makes a
    "why did the assistant say that?" question answerable.
    """
    passages = await rag.retrieve(
        body.organization_id,
        body.query,
        top_k=body.top_k,
        strategy=body.strategy,
        source_types=body.source_types,
    )
    return SuccessResponse(
        message="Knowledge search completed.",
        data=[
            KnowledgeSearchHit(
                chunk_id=passage.chunk_id,
                document_id=passage.document_id,
                document_title=passage.document_title,
                document_uri=passage.document_uri,
                content=passage.content,
                score=passage.score,
            )
            for passage in passages
        ],
        meta=_meta(),
    )


__all__ = ["document_to_response", "router"]
