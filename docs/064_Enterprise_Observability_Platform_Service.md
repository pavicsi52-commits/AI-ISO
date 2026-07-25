# AI Infrastructure Operating System (AI-IOS)

# Prompt 064

## Enterprise Observability Platform Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 063

---

# ROLE

You are the Principal Enterprise Observability Architect.

Implement the Enterprise Observability Platform Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise observability platform.

---

# OBJECTIVE

Build a centralized Observability Platform responsible for collecting, correlating, storing, analyzing, visualizing, and reporting logs, metrics, traces, events, profiles, and telemetry across every AI-IOS component.

The platform SHALL provide complete operational visibility into applications, infrastructure, workflows, AI agents, connectors, plugins, Kubernetes clusters, cloud resources, and edge deployments.

---

# SERVICE LOCATION

services/observability-platform-service/

---

# DIRECTORY STRUCTURE

observability-platform-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

metrics/

logs/

traces/

events/

profiling/

topology/

correlation/

analytics/

dashboards/

slo/

capacity/

anomaly/

root_cause/

cost/

collectors/

ingestion/

processors/

storage/

retention/

search/

queries/

notifications/

reports/

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

metrics

metric_series

log_entries

trace_spans

trace_sessions

events

profiles

service_dependencies

service_topology

slos

slis

capacity_forecasts

anomaly_detections

root_cause_reports

cost_reports

observability_statistics

observability_reports

observability_audit

---

# DATA SOURCES

Support

Platform Services

Microservices

FastAPI

Workers

Schedulers

AI Agents

AI Assistant

Workflows

Automation Jobs

Plugins

Connectors

Webhooks

API Gateway

Kubernetes

Docker

Linux

Windows

Cloud Providers

Edge Nodes

Custom Applications

---

# METRICS

Support

System Metrics

Application Metrics

Business Metrics

Infrastructure Metrics

AI Metrics

Workflow Metrics

Automation Metrics

Database Metrics

Network Metrics

Custom Metrics

---

# LOG MANAGEMENT

Support

Structured Logs

JSON Logs

Plain Text Logs

Centralized Collection

Log Parsing

Log Enrichment

Log Correlation

Log Retention

Log Compression

Log Search

Saved Queries

Live Streaming

---

# DISTRIBUTED TRACING

Support

OpenTelemetry

Span Collection

Trace Correlation

Cross-service Tracing

Parent-child Relationships

Sampling Policies

Trace Search

Trace Visualization

Latency Analysis

---

# EVENT MANAGEMENT

Support

Platform Events

Infrastructure Events

Application Events

Security Events

Audit Events

AI Events

Custom Events

Event Correlation

---

# PROFILING

Support

CPU Profiling

Memory Profiling

Heap Analysis

Thread Analysis

I/O Profiling

Async Profiling

Resource Utilization

Performance Hotspots

---

# TOPOLOGY

Support

Service Dependency Mapping

Application Topology

Infrastructure Topology

Kubernetes Topology

Knowledge Graph Integration

Dynamic Discovery

Impact Analysis

Dependency Visualization

---

# CORRELATION

Correlate

Logs

Metrics

Traces

Events

Alerts

Incidents

Changes

Deployments

AI Executions

Automation Runs

---

# SLO / SLI MANAGEMENT

Support

Availability

Latency

Error Rate

Success Rate

Throughput

Custom SLIs

SLO Targets

Burn Rate

Compliance Tracking

---

# ANOMALY DETECTION

Support

Statistical Detection

Threshold Detection

Seasonality Detection

AI-assisted Detection

Forecast Deviations

Spike Detection

Trend Analysis

Custom Rules

---

# ROOT CAUSE ANALYSIS

Support

Dependency Analysis

Timeline Reconstruction

Correlation Engine

Failure Propagation

Blast Radius

Incident Correlation

AI-assisted RCA

Recommendations

---

# CAPACITY PLANNING

Support

Resource Forecasting

Storage Forecasting

CPU Forecasting

Memory Forecasting

Network Forecasting

Growth Trends

Infrastructure Planning

---

# COST ANALYTICS

Support

Compute Cost

Storage Cost

Network Cost

Model Usage Cost

Embedding Cost

Cloud Cost

Department Cost

Project Cost

Organization Cost

---

# SEARCH

Support

Log Search

Trace Search

Metric Search

Event Search

Saved Queries

Query History

Advanced Filters

Time Range Queries

---

# DASHBOARDS

Support

Executive Dashboard

Operations Dashboard

Infrastructure Dashboard

AI Dashboard

Automation Dashboard

Developer Dashboard

Custom Dashboards

Widget Library

---

# PLATFORM INTEGRATIONS

Integrate

Monitoring (044)

Alerting (045)

Knowledge Graph (049)

Incident Management (052)

Scheduler (054)

Notification Center (055)

API Gateway (056)

AI Agent Platform (060)

RAG Service (062)

Document Intelligence (063)

---

# ANALYTICS

Collect

Metric Volume

Log Volume

Trace Volume

Average Latency

Service Availability

Top Errors

SLO Compliance

Capacity Trends

Resource Consumption

---

# REPORTING

Generate

Observability Reports

Log Reports

Trace Reports

Performance Reports

Capacity Reports

SLO Reports

Cost Reports

Audit Reports

---

# EVENTS

Publish

MetricCollected

LogIngested

TraceCompleted

AnomalyDetected

SLOBreached

RootCauseCompleted

CapacityForecastGenerated

DashboardUpdated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

SLO Violation

Anomaly Detected

Storage Threshold Reached

Capacity Warning

Root Cause Completed

Service Degradation

---

# TELEMETRY

Integrate Prompt 024.

Support

OpenTelemetry SDK

OpenTelemetry Collector

Trace Exporters

Metric Exporters

Log Exporters

OTLP

Jaeger Export

Prometheus Export

---

# AUDIT

Audit

Configuration Changes

Retention Policy Changes

Dashboard Changes

Collector Changes

Administrative Operations

---

# REST APIs

Implement

GET /observability/metrics

GET /observability/logs

GET /observability/traces

GET /observability/events

GET /observability/topology

GET /observability/slos

POST /observability/slos

GET /observability/anomalies

GET /observability/root-cause

GET /observability/capacity

GET /observability/cost

GET /observability/statistics

GET /observability/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 050.

Enforce

Organization isolation

Project isolation

RBAC authorization

Encrypted telemetry storage

Immutable audit history

Secure OTLP endpoints

Log redaction

PII masking

---

# PERFORMANCE

Distributed Collectors

Horizontal Scaling

Streaming Pipelines

Partitioned Storage

Compression

Index Optimization

Connection Pooling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Metrics Tests

Tracing Tests

Logging Tests

Correlation Tests

SLO Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Observability Guide

Logging Guide

Tracing Guide

Metrics Guide

SLO Guide

Topology Guide

Root Cause Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Metrics Collection

✓ Log Aggregation

✓ Distributed Tracing

✓ Event Correlation

✓ Service Topology

✓ SLO Management

✓ Root Cause Analysis

✓ Capacity Planning

✓ Cost Analytics

✓ Dashboards

✓ Search

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

Commercial Observability SaaS

Vendor-specific Monitoring Agents

External Billing Platforms

Only implement the Enterprise Observability Platform Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate distributed telemetry collectors.

Generate log correlation engine.

Generate trace processing engine.

Generate anomaly detection framework.

Generate root cause analysis engine.

Generate SLO management framework.

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

End Prompt 064.
