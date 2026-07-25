# AI Infrastructure Operating System (AI-IOS)

# Prompt 022

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

---

# ROLE

You are the Principal Observability Architect.

Implement the Enterprise Monitoring Framework.

Do not redesign the platform.

Do not implement business logic.

Implement only the monitoring framework.

---

# OBJECTIVE

Build a reusable monitoring framework for the entire AI-IOS platform.

Every microservice shall expose monitoring through this framework.

No service may implement custom monitoring.

The framework shall support

• Application Monitoring
• Infrastructure Monitoring
• Service Health
• Dependency Monitoring
• Resource Monitoring
• SLA Monitoring
• Synthetic Monitoring
• Alert Integration
• Metrics Collection
• Health Checks
• Monitoring Dashboard Support

---

# PACKAGE

packages/shared-core/monitoring/

---

# DIRECTORY STRUCTURE

monitoring/

__init__.py

manager.py

collector.py

registry.py

health.py

checks.py

heartbeat.py

resources.py

application.py

services.py

dependencies.py

metrics.py

thresholds.py

alerts.py

sla.py

synthetic.py

availability.py

status.py

factory.py

middleware.py

decorators.py

helpers.py

constants.py

exceptions.py

tests/

README.md

---

# MONITORING CATEGORIES

Application

Infrastructure

Database

Redis

RabbitMQ

Neo4j

Storage

API

Background Workers

Scheduled Jobs

AI Services

Automation Engine

Validation Engine

Workflow Engine

Plugin System

Connector System

---

# APPLICATION HEALTH

Monitor

CPU

Memory

Threads

Open Files

Event Loop

Garbage Collection

Response Time

Errors

Warnings

---

# SERVICE HEALTH

Support

Healthy

Degraded

Unavailable

Maintenance

Unknown

Health shall be calculated automatically.

---

# DEPENDENCY HEALTH

Monitor

PostgreSQL

Neo4j

Redis

RabbitMQ

MinIO

OpenSearch

AI Providers

SMTP

External APIs

Every dependency shall expose health status.

---

# RESOURCE MONITORING

CPU

Memory

Disk

Filesystem

Network

Processes

Containers

Pods

Nodes

GPU (Future)

---

# HEALTH CHECK FRAMEWORK

Support

Liveness

Readiness

Startup

Dependency

Deep Health

Custom Health Checks

---

# HEARTBEAT

Every service shall emit heartbeat.

Heartbeat contains

Service Name

Version

Timestamp

Status

Latency

Memory

CPU

Request Count

---

# METRICS

Collect

Requests

Errors

Latency

Queue Size

Database Connections

Redis Hits

Redis Misses

Worker Count

Open Sessions

Jobs Running

Jobs Failed

Plugin Count

Connector Count

---

# SLA MONITORING

Track

Availability

Latency

Error Rate

Success Rate

Recovery Time

Downtime

Historical Trends

---

# THRESHOLDS

Support

Critical

Warning

Informational

Configurable per environment.

---

# ALERT INTEGRATION

Generate alerts for

Health Failure

High CPU

High Memory

Database Down

Queue Overflow

Worker Failure

Storage Failure

Plugin Failure

Connector Failure

---

# SYNTHETIC MONITORING

Support

HTTP Checks

API Checks

Workflow Checks

Database Checks

Authentication Checks

Scheduled Validation

---

# AVAILABILITY

Track

Current Status

Historical Status

Monthly Uptime

Quarterly Uptime

Yearly Uptime

Availability Percentage

---

# DASHBOARD SUPPORT

Provide data for

Grafana

OpenSearch Dashboards

Future Native Dashboard

---

# SECURITY

Monitoring endpoints require authorization.

Mask sensitive information.

Do not expose secrets.

---

# PERFORMANCE

Low overhead

Async

Cached health checks

Configurable polling

Horizontal scalability

---

# TESTING

Unit Tests

Health Tests

Dependency Tests

Metrics Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Health Guide

Metrics Guide

Monitoring Guide

Dashboard Guide

Developer Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Health Framework

✓ Dependency Monitoring

✓ Resource Monitoring

✓ SLA Monitoring

✓ Metrics Collection

✓ Alert Integration

✓ Dashboard Support

✓ Synthetic Monitoring

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Grafana Dashboards

Prometheus Server

Business Logic

REST APIs

Automation

Authentication

Only Enterprise Monitoring Framework.

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

End Prompt 022.
