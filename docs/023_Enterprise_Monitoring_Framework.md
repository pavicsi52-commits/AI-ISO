# AI Infrastructure Operating System (AI-IOS)

# Prompt 023

## Enterprise Monitoring Framework

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

---

# ROLE

You are the Principal Site Reliability Engineer (SRE) and Observability Architect.

Implement the Enterprise Monitoring Framework.

Do NOT redesign the platform.

Do NOT implement business logic.

Implement ONLY the reusable monitoring framework.

Every AI-IOS microservice shall use this framework.

---

# OBJECTIVE

Build a centralized monitoring framework responsible for monitoring the health, availability, performance, and resource utilization of every component in the AI-IOS platform.

The framework shall provide:

- Health Monitoring
- Infrastructure Monitoring
- Application Monitoring
- Service Monitoring
- Dependency Monitoring
- Resource Monitoring
- Availability Monitoring
- SLA Monitoring
- Alert Integration
- Monitoring Registry
- Metrics Collection
- Status Aggregation

---

# PACKAGE

packages/shared-core/monitoring/

---

# DIRECTORY STRUCTURE

monitoring/

__init__.py

manager.py

registry.py

collector.py

health.py

heartbeat.py

application.py

services.py

dependencies.py

resources.py

availability.py

status.py

checks.py

thresholds.py

alerts.py

sla.py

metrics.py

dashboard.py

middleware.py

decorators.py

factory.py

helpers.py

constants.py

exceptions.py

tests/

README.md

---

# MONITORING PRINCIPLES

Monitoring must be centralized.

Monitoring shall never affect application performance.

Monitoring shall support horizontal scaling.

Monitoring shall be asynchronous whenever possible.

Monitoring shall be configurable.

Monitoring data must never expose secrets.

---

# MONITORING CATEGORIES

Application

Infrastructure

Database

Cache

Queue

Storage

Network

Security

Workflow

Automation

Validation

AI

Plugin

Connector

Scheduler

Background Workers

---

# APPLICATION MONITORING

Collect

CPU Usage

Memory Usage

Response Time

Request Count

Error Count

Exception Count

Open Connections

Thread Count

Garbage Collection

Event Loop Delay

---

# INFRASTRUCTURE MONITORING

Monitor

Servers

Virtual Machines

Containers

Kubernetes Pods

Namespaces

Nodes

Clusters

Operating System

Filesystem

Network Interfaces

---

# DEPENDENCY MONITORING

Monitor

PostgreSQL

Neo4j

Redis

RabbitMQ

MinIO

OpenSearch

SMTP

AI Providers

External REST APIs

Every dependency must expose health status.

---

# RESOURCE MONITORING

CPU

Memory

Disk

Filesystem

Processes

Network

Bandwidth

Open Files

GPU (Future)

---

# HEALTH CHECKS

Support

Liveness

Readiness

Startup

Deep Health

Dependency Health

Custom Health Checks

Periodic Health Checks

---

# SERVICE STATUS

Support

Healthy

Degraded

Warning

Unavailable

Maintenance

Unknown

Status shall be calculated automatically.

---

# HEARTBEAT

Every service shall publish heartbeat.

Heartbeat includes

Service Name

Version

Hostname

Environment

Timestamp

Status

CPU

Memory

Latency

Request Count

Error Count

---

# AVAILABILITY

Track

Current Availability

Historical Availability

Daily

Weekly

Monthly

Quarterly

Yearly

Availability Percentage

---

# SLA MONITORING

Track

Uptime

Response Time

Availability

Error Rate

Recovery Time

Downtime

Service Objectives

Service Level Indicators

Service Level Agreements

---

# THRESHOLDS

Support

Critical

High

Medium

Low

Informational

Thresholds shall be configurable.

---

# ALERT INTEGRATION

Generate alerts for

Health Failure

Dependency Failure

High CPU

High Memory

Disk Full

Database Down

Redis Down

Queue Overflow

Storage Failure

Plugin Failure

Connector Failure

Worker Failure

High Error Rate

High Latency

---

# MONITORING REGISTRY

Maintain registry for

Services

Dependencies

Health Checks

Metrics

Thresholds

Dashboards

Alert Rules

---

# METRICS COLLECTION

Collect

Request Count

Response Time

Error Rate

Success Rate

Queue Size

Worker Count

Database Connections

Redis Hit Ratio

Cache Miss Ratio

Storage Usage

Workflow Duration

Automation Duration

Validation Duration

AI Request Duration

Plugin Count

Connector Count

---

# DASHBOARD SUPPORT

Provide reusable APIs for

Grafana

OpenSearch Dashboards

Native AI-IOS Dashboard

Custom Dashboards

---

# SECURITY

Monitoring endpoints require authentication.

Mask sensitive values.

Never expose passwords.

Never expose API keys.

Never expose secrets.

---

# PERFORMANCE

Async collection

Cached health checks

Efficient polling

Minimal overhead

Horizontal scalability

---

# TESTING

Unit Tests

Integration Tests

Health Tests

Dependency Tests

Metrics Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Monitoring Guide

Health Guide

Metrics Guide

Dashboard Guide

Developer Guide

Operations Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Monitoring Manager

✓ Monitoring Registry

✓ Health Framework

✓ Dependency Monitoring

✓ Infrastructure Monitoring

✓ Resource Monitoring

✓ Availability Monitoring

✓ SLA Monitoring

✓ Alert Integration

✓ Metrics Collection

✓ Dashboard Support

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Grafana Server

Prometheus Server

Business Logic

REST APIs

Authentication

Automation

Inventory

Validation

Only the Enterprise Monitoring Framework.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

No placeholders.

No TODO comments.

No demo code.

Implementation must compile successfully.

Implementation must pass Ruff, Black, MyPy and Pytest.

Do not summarize.

End Prompt 023.
