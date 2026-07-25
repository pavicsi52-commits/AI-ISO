# AI Infrastructure Operating System (AI-IOS)

# Prompt 024

## Enterprise Telemetry Framework

Reference Documents

Prompt 000
Prompt 001
Prompt 002
Prompt 003
Prompt 004
Prompt 005
Prompt 006
Prompt 007
Prompt 008
Prompt 009
Prompt 010
Prompt 011
Prompt 012
Prompt 013
Prompt 014
Prompt 015
Prompt 016
Prompt 017
Prompt 018
Prompt 019
Prompt 020
Prompt 021
Prompt 022
Prompt 023

---

# ROLE

You are the Principal Observability Architect.

Implement the complete Enterprise Telemetry Framework.

Do NOT redesign the architecture.

Do NOT implement business logic.

Implement ONLY the reusable telemetry framework.

Every AI-IOS microservice, SDK, worker, connector and API shall use this framework.

---

# OBJECTIVE

Create a centralized telemetry framework that provides complete end-to-end observability throughout the AI-IOS platform.

The framework shall provide

• Distributed Tracing

• OpenTelemetry Integration

• Context Propagation

• Span Management

• Correlation IDs

• Request IDs

• Performance Profiling

• Trace Analytics

• Metrics Correlation

• Log Correlation

• Trace Export

• Trace Search

• Performance Baselines

---

# PACKAGE

packages/shared-core/telemetry/

---

# DIRECTORY STRUCTURE

telemetry/

__init__.py

manager.py

provider.py

configuration.py

context.py

trace.py

span.py

propagation.py

middleware.py

decorators.py

request.py

worker.py

scheduler.py

queue.py

database.py

cache.py

storage.py

connector.py

plugin.py

workflow.py

automation.py

validation.py

ai.py

profiling.py

analytics.py

sampling.py

metrics.py

logs.py

exporters.py

health.py

helpers.py

constants.py

exceptions.py

factory.py

tests/

README.md

---

# TELEMETRY PRINCIPLES

Every request shall be traceable.

Every operation shall belong to a trace.

Every span shall have a parent.

Telemetry must have minimal runtime overhead.

Sensitive information shall never be collected.

---

# TRACE CONTEXT

Every trace shall contain

trace_id

span_id

parent_span_id

correlation_id

request_id

organization_id

project_id

user_id

tenant_id

service_name

service_version

environment

hostname

timestamp

---

# DISTRIBUTED TRACING

Support tracing across

Frontend

API Gateway

Backend APIs

Background Workers

RabbitMQ

Redis

PostgreSQL

Neo4j

OpenSearch

MinIO

Workflow SDK

Connector SDK

Plugin SDK

Scheduler

Automation Engine

Validation Engine

AI Engine

Future

gRPC

GraphQL

---

# SPAN TYPES

HTTP Request

REST API

Database Query

Cache Access

Queue Publish

Queue Consume

Workflow Step

Automation Step

Validation Step

Connector Execution

Plugin Execution

AI Request

Model Inference

File Upload

File Download

Background Job

Scheduler Job

CLI Command

---

# CONTEXT PROPAGATION

Support propagation through

HTTP Headers

Queue Messages

Background Workers

Scheduler Jobs

Async Tasks

WebSockets

Future gRPC Metadata

Maintain trace continuity across all services.

---

# MIDDLEWARE

Automatically create root traces for

HTTP Requests

Background Jobs

Queue Workers

CLI Commands

Scheduler Tasks

Workflow Executions

---

# DECORATORS

Implement

@trace

@span

@measure

@profile

@track_database

@track_cache

@track_queue

@track_storage

@track_connector

@track_plugin

@track_workflow

@track_automation

@track_validation

@track_ai

---

# METRICS CORRELATION

Associate metrics with traces.

Track

Latency

Request Count

Error Count

CPU

Memory

Queue Depth

Database Time

Cache Time

Storage Time

Workflow Duration

Automation Duration

Validation Duration

Inference Duration

---

# LOG CORRELATION

Every log entry shall contain

trace_id

span_id

correlation_id

request_id

service

organization_id

project_id

hostname

Logs shall be searchable using trace identifiers.

---

# PERFORMANCE PROFILING

Profile

REST APIs

Database Queries

Redis Operations

RabbitMQ Operations

Neo4j Queries

Workflow Execution

Automation Execution

Validation Execution

AI Inference

Connector Execution

Plugin Execution

Storage Operations

---

# SAMPLING

Support

Always Sample

Never Sample

Probability Sampling

Adaptive Sampling

Rule Based Sampling

Environment Based Sampling

Dynamic Sampling

---

# ANALYTICS

Provide

Trace Search

Slowest Requests

Slowest Queries

Service Dependency Graph

Error Hotspots

Top Exceptions

P50

P90

P95

P99

Average Latency

Throughput

---

# EXPORTERS

Support

OTLP

Console

JSON

Future

Jaeger

Grafana Tempo

Zipkin

Azure Monitor

AWS X-Ray

Google Cloud Trace

Exporters shall be configurable.

---

# HEALTH

Monitor

Exporter Status

Dropped Spans

Sampling Rate

Buffer Usage

Queue Length

Export Latency

Telemetry Service Health

---

# SECURITY

Never capture

Passwords

API Keys

JWT Tokens

Secrets

Private Keys

Personally Identifiable Information

Automatically mask sensitive fields.

---

# PERFORMANCE

Async Export

Batch Export

Buffered Writes

Compression

Minimal Allocation

Low CPU Usage

Horizontal Scaling

---

# OPENTELEMETRY

Integrate

OpenTelemetry SDK

OTLP Exporter

Context Propagation

Metrics

Tracing

Logs

Follow OpenTelemetry semantic conventions.

---

# TESTING

Unit Tests

Tracing Tests

Propagation Tests

Sampling Tests

Exporter Tests

Load Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Telemetry Guide

Tracing Guide

OpenTelemetry Guide

Sampling Guide

Performance Guide

Developer Guide

Operations Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ OpenTelemetry Integration

✓ Distributed Tracing

✓ Context Propagation

✓ Correlation IDs

✓ Request IDs

✓ Span Management

✓ Trace Analytics

✓ Performance Profiling

✓ Exporters

✓ Log Correlation

✓ Metrics Correlation

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Jaeger Server

Tempo Server

Prometheus Server

Business Logic

REST APIs

Authentication

Automation

Inventory

Validation

Only the Enterprise Telemetry Framework.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate production-quality code.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass

• Ruff

• Black

• MyPy

• Pytest

Do not summarize.

End Prompt 024.
