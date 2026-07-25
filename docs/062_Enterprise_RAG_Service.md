# AI Infrastructure Operating System (AI-IOS)

# Prompt 062

## Enterprise RAG Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 061

---

# ROLE

You are the Principal Enterprise AI Knowledge Architect.

Implement the Enterprise Retrieval-Augmented Generation (RAG) Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise RAG platform.

---

# OBJECTIVE

Build a centralized RAG Service responsible for document ingestion, indexing, embedding generation, vector storage abstraction, hybrid retrieval, reranking, context assembly, GraphRAG integration, access-controlled retrieval, and knowledge lifecycle management.

The RAG Service SHALL become the enterprise knowledge retrieval layer for every AI capability across AI-IOS.

---

# SERVICE LOCATION

services/rag-service/

---

# DIRECTORY STRUCTURE

rag-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

documents/

ingestion/

parsers/

chunking/

embeddings/

vector_store/

hybrid_search/

graph_rag/

reranking/

retrieval/

context/

citations/

indexing/

synchronization/

metadata/

security/

evaluation/

analytics/

reports/

events/

notifications/

middleware/

validators/

workers/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

documents

document_versions

document_chunks

document_metadata

embedding_models

embedding_vectors

vector_indexes

retrieval_queries

retrieval_results

retrieval_feedback

reranking_results

knowledge_sources

indexing_jobs

rag_statistics

rag_reports

rag_audit

---

# KNOWLEDGE SOURCES

Support

PDF

DOCX

TXT

Markdown

HTML

CSV

JSON

XML

YAML

REST APIs

Git Repositories

Confluence

SharePoint

S3 / MinIO

Neo4j

PostgreSQL

Custom Sources

---

# DOCUMENT LIFECYCLE

Support

Upload

Import

Parse

Normalize

Chunk

Embed

Index

Publish

Update

Archive

Delete

Restore

---

# DOCUMENT PARSING

Support

Text Extraction

OCR Integration

Metadata Extraction

Table Extraction

Code Extraction

Image Metadata

Structured Documents

Unstructured Documents

Mixed Documents

---

# CHUNKING STRATEGIES

Support

Fixed Size

Sliding Window

Semantic Chunking

Heading-based

Paragraph-based

Sentence-based

Code-aware

Table-aware

Hybrid Chunking

Configurable Chunk Sizes

Chunk Overlap

---

# EMBEDDING MODELS

Support

OpenAI

Azure OpenAI

Gemini

Voyage AI

Cohere

Sentence Transformers

BGE

E5

Ollama Embeddings

Custom Models

Model Versioning

---

# VECTOR DATABASE

Support

PgVector

Qdrant

Milvus

Weaviate

Chroma

Pinecone

Redis Vector

FAISS

Pluggable Provider Architecture

---

# HYBRID SEARCH

Support

Vector Search

Keyword Search

BM25

Metadata Filtering

Graph Search

Hybrid Ranking

Weighted Scoring

Boolean Queries

Fuzzy Search

Semantic Search

---

# GRAPHRAG

Integrate Prompt 049.

Support

Neo4j Traversal

Entity Linking

Relationship Expansion

Graph Context Retrieval

Dependency Context

Topology-aware Retrieval

Knowledge Graph Enrichment

---

# RERANKING

Support

Cross Encoder Models

LLM Reranking

Metadata Scoring

Freshness Scoring

Access Priority

Hybrid Scoring

Confidence Scoring

Top-K Selection

---

# CONTEXT ASSEMBLY

Support

Token Budgeting

Context Ordering

Deduplication

Metadata Inclusion

Citation Mapping

Conversation Context

Graph Context

Multi-source Context

---

# CITATIONS

Support

Source References

Chunk References

Document References

Page Numbers

Section References

Confidence Scores

Evidence Traceability

---

# ACCESS CONTROL

Integrate Prompt 032.

Support

Organization Isolation

Project Isolation

Document Permissions

Role-based Retrieval

Tag-based Access

Classification Levels

Confidential Documents

---

# INDEXING

Support

Full Index

Incremental Index

Realtime Index

Batch Index

Scheduled Index

Priority Index

Index Validation

Index Optimization

---

# SYNCHRONIZATION

Support

Knowledge Source Sync

Incremental Updates

Conflict Detection

Version Tracking

Automatic Reindexing

Deletion Detection

---

# PLATFORM INTEGRATIONS

Integrate

Knowledge Graph (049)

AI Assistant (046)

AI Agent Platform (060)

Prompt Management (061)

Integration Hub (058)

Scheduler (054)

Notification Center (055)

Policy Engine (050)

---

# EVALUATION

Support

Precision

Recall

MRR

nDCG

Hit Rate

Latency

Citation Accuracy

Hallucination Detection

Grounding Validation

Human Feedback

---

# ANALYTICS

Collect

Documents Indexed

Chunks Generated

Embedding Count

Retrieval Requests

Average Latency

Top Sources

Index Size

Search Accuracy

Embedding Costs

---

# REPORTING

Generate

Index Reports

Retrieval Reports

Knowledge Source Reports

Embedding Reports

Accuracy Reports

Evaluation Reports

Audit Reports

---

# EVENTS

Publish

DocumentImported

DocumentIndexed

EmbeddingGenerated

RetrievalExecuted

ContextGenerated

ReindexCompleted

KnowledgeSourceUpdated

EvaluationCompleted

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Index Failed

Knowledge Source Unavailable

Embedding Failure

Reindex Completed

Storage Threshold Reached

Evaluation Completed

---

# TELEMETRY

Integrate Prompt 024.

Trace

Document Parsing

Chunk Generation

Embedding

Vector Search

Graph Search

Context Assembly

Citation Generation

---

# AUDIT

Audit

Document Upload

Document Update

Index Operations

Retrieval Queries

Permission Changes

Knowledge Source Changes

Administrative Operations

---

# REST APIs

Implement

GET /rag/documents

POST /rag/documents

PUT /rag/documents/{id}

DELETE /rag/documents/{id}

POST /rag/index

POST /rag/reindex

POST /rag/search

POST /rag/retrieve

POST /rag/context

GET /rag/sources

POST /rag/sources

GET /rag/statistics

GET /rag/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Integrate Prompt 050.

Enforce

Organization isolation

Project isolation

RBAC authorization

Encrypted embeddings

Secure document storage

Access-controlled retrieval

Immutable audit history

Protection against prompt injection

Protection against data leakage

---

# PERFORMANCE

Distributed Index Workers

Embedding Cache

Vector Cache

Parallel Retrieval

Incremental Indexing

Horizontal Scaling

Connection Pooling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Chunking Tests

Embedding Tests

Retrieval Tests

Hybrid Search Tests

GraphRAG Tests

Reranking Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

RAG Guide

Document Ingestion Guide

Embedding Guide

Hybrid Search Guide

GraphRAG Guide

Indexing Guide

Evaluation Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Document Ingestion

✓ Multi-format Parsing

✓ Chunking Engine

✓ Embedding Generation

✓ Vector Database Abstraction

✓ Hybrid Search

✓ GraphRAG Integration

✓ Reranking

✓ Context Assembly

✓ Citation Generation

✓ Incremental Indexing

✓ Access-controlled Retrieval

✓ Evaluation Framework

✓ Analytics

✓ Reports

✓ Events

✓ Notifications

✓ Audit

✓ REST APIs

✓ Database Migrations

✓ OpenAPI Documentation

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

LLM Training

Model Fine-tuning

Enterprise Search UI

Business-specific Knowledge Bases

Only implement the Enterprise RAG Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate document ingestion engine.

Generate embedding engine.

Generate hybrid retrieval engine.

Generate GraphRAG integration.

Generate reranking engine.

Generate evaluation framework.

Generate unit and integration tests.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

- Ruff
- Black
- MyPy
- Pytest

Do not summarize.

End Prompt 062.
