# AI Infrastructure Operating System (AI-IOS)

# Prompt 046

## Enterprise AI Assistant Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 045

---

# ROLE

You are the Principal Enterprise AI Architect.

Implement the Enterprise AI Assistant Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise AI Operations Assistant.

---

# OBJECTIVE

Build a centralized AI Assistant Service that acts as an intelligent operations copilot for AI-IOS.

The assistant SHALL understand infrastructure, topology, automation, workflows, monitoring, validation, configuration management, inventory, and enterprise documentation.

The assistant SHALL support secure tool execution, Retrieval-Augmented Generation (RAG), multi-agent orchestration, reasoning, recommendations, troubleshooting, and operational automation.

---

# SERVICE LOCATION

services/ai-assistant-service/

---

# DIRECTORY STRUCTURE

ai-assistant-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

agents/

planner/

executor/

reasoning/

rag/

embeddings/

retrievers/

vector_store/

memory/

prompts/

models/

tool_calling/

guardrails/

policies/

knowledge/

chat/

conversation/

recommendations/

root_cause/

summaries/

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

ai_conversations

ai_messages

ai_sessions

ai_agents

ai_prompts

ai_prompt_versions

ai_tools

ai_tool_calls

ai_tool_results

ai_embeddings

ai_documents

ai_chunks

ai_retrieval_history

ai_memory

ai_feedback

ai_recommendations

ai_reports

ai_statistics

ai_audit

---

# AGENT TYPES

Planner Agent

Reasoning Agent

Infrastructure Agent

Automation Agent

Validation Agent

Monitoring Agent

Configuration Agent

Knowledge Agent

Workflow Agent

Reporting Agent

Security Agent

Custom Agents

---

# MULTI AGENT ORCHESTRATION

Support

Task Decomposition

Planner

Coordinator

Parallel Agents

Sequential Agents

Agent Communication

Shared Memory

Agent Routing

Failure Recovery

Result Aggregation

---

# MODEL MANAGEMENT

Support

OpenAI

Azure OpenAI

Anthropic

Google Gemini

Ollama

vLLM

OpenRouter

Local Models

Model Selection Policies

Fallback Models

Streaming Responses

---

# RAG

Support

Document Ingestion

Chunking

Embeddings

Vector Search

Hybrid Search

Metadata Filtering

Citation Support

Context Ranking

Semantic Search

Incremental Indexing

---

# KNOWLEDGE SOURCES

Inventory

Discovery

Configuration Management

Automation

Workflow Runtime

Validation

Monitoring

Alerting

Reports

Documentation

Policies

Playbooks

Runbooks

Enterprise Wiki

Uploaded Documents

---

# MEMORY

Support

Conversation Memory

Session Memory

User Memory

Organization Memory

Project Memory

Tool Results

Summaries

Context Compression

Memory Expiration

---

# TOOL CALLING

Support

Inventory Queries

Automation Execution

Workflow Execution

Validation Execution

Monitoring Queries

Alert Queries

Configuration Queries

Reporting

Search

REST APIs

Plugin Tools

Custom Tools

---

# INFRASTRUCTURE ASSISTANCE

Support

Troubleshooting

Root Cause Analysis

Configuration Review

Dependency Analysis

Topology Questions

Capacity Analysis

Health Summary

Impact Analysis

Operational Guidance

---

# AUTOMATION ASSISTANCE

Support

Playbook Recommendation

Workflow Recommendation

Automation Generation

Execution Planning

Rollback Planning

Risk Assessment

---

# VALIDATION ASSISTANCE

Support

Validation Summary

Failure Analysis

Remediation Suggestions

Compliance Explanation

Health Recommendations

---

# MONITORING ASSISTANCE

Support

Metric Analysis

Trend Analysis

Health Summary

Capacity Planning

Performance Insights

Alert Explanation

---

# CONFIGURATION ASSISTANCE

Support

Drift Explanation

Configuration Comparison

Baseline Review

Policy Suggestions

Change Risk Analysis

---

# REPORT GENERATION

Generate

Executive Reports

Operational Reports

Incident Summaries

Health Summaries

Capacity Reports

Automation Reports

Validation Reports

Compliance Reports

Natural Language Reports

---

# PROMPT MANAGEMENT

Support

Prompt Templates

Versioning

Testing

Approval

Rollback

Variables

Prompt Libraries

---

# SAFETY

Support

RBAC-aware Responses

Permission-aware Tool Calls

PII Protection

Secret Redaction

Prompt Injection Protection

Tool Permission Validation

Hallucination Mitigation

Output Validation

---

# ANALYTICS

Collect

Conversation Count

Tool Usage

Agent Usage

Model Usage

Latency

Cost

Token Usage

Recommendation Accuracy

Feedback Scores

---

# EVENTS

Publish

ConversationStarted

ConversationCompleted

ToolCalled

RecommendationGenerated

ReportGenerated

ModelChanged

FeedbackReceived

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Long Running AI Tasks

Report Completion

Recommendation Ready

Model Failure

Tool Failure

---

# TELEMETRY

Integrate Prompt 024.

Trace

Prompt Execution

RAG Retrieval

Embedding Search

Tool Calls

Agent Execution

Model Latency

Streaming Responses

---

# AUDIT

Audit

Prompt Changes

Tool Calls

Recommendations

Model Selection

Conversation Access

Administrative Operations

---

# REST APIs

Implement

POST /ai/chat

POST /ai/chat/stream

GET /ai/conversations

GET /ai/conversations/{id}

POST /ai/reports

POST /ai/recommendations

POST /ai/tools/execute

GET /ai/models

POST /ai/models/select

GET /ai/statistics

GET /ai/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secret redaction

Tool permission validation

Audit every AI interaction

---

# PERFORMANCE

Streaming Responses

Async Tool Calls

Parallel Agent Execution

Embedding Cache

Prompt Cache

Horizontal Scaling

Model Pooling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Agent Tests

RAG Tests

Tool Calling Tests

Memory Tests

Guardrail Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

AI Assistant Guide

Agent Guide

RAG Guide

Tool Calling Guide

Prompt Guide

Security Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Multi-Agent Framework

✓ Model Management

✓ RAG Pipeline

✓ Embedding Pipeline

✓ Tool Calling

✓ Infrastructure Reasoning

✓ Automation Recommendations

✓ Root Cause Analysis

✓ Report Generation

✓ Prompt Management

✓ Conversation Memory

✓ Analytics

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

Dashboard UI

Business-specific prompts

Custom LLM training

External SaaS integrations not defined by the platform

Only implement the Enterprise AI Assistant Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate multi-agent framework.

Generate RAG pipeline.

Generate tool-calling framework.

Generate prompt management.

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

End Prompt 046.
