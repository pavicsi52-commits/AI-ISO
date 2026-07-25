# AI Infrastructure Operating System (AI-IOS)

# Prompt 044

## Enterprise Monitoring Service

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
Prompt 024
Prompt 025
Prompt 026
Prompt 027
Prompt 028
Prompt 029
Prompt 030
Prompt 031
Prompt 032
Prompt 033
Prompt 034
Prompt 035
Prompt 036
Prompt 037
Prompt 038
Prompt 039
Prompt 040
Prompt 041
Prompt 042
Prompt 043

---

# ROLE

You are the Principal Enterprise Monitoring Architect.

Implement the Enterprise Monitoring Service.

Use every previously implemented framework.

Do NOT redesign the platform.

Implement a production-ready enterprise monitoring and observability service.

---

# OBJECTIVE

Build a centralized Monitoring Service responsible for continuously collecting, storing, processing, correlating, and evaluating operational telemetry across AI-IOS.

The Monitoring Service SHALL support infrastructure, cloud, Kubernetes, applications, databases, industrial systems, and custom telemetry sources.

Monitoring SHALL integrate with Inventory, Discovery, Automation, Workflow Runtime, Validation, Configuration Management, Alerting, Dashboards, AI Assistant, and Incident Management.

---

# SERVICE LOCATION

services/monitoring-service/

---

# DIRECTORY STRUCTURE

monitoring-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

collectors/

agents/

metrics/

health/

availability/

performance/

thresholds/

rules/

aggregation/

timeseries/

retention/

sampling/

synthetic/

dependency/

sla/

slo/

forecasting/

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

monitoring_targets

monitoring_metrics

monitoring_metric_series

monitoring_collectors

monitoring_health

monitoring_availability

monitoring_thresholds

monitoring_rules

monitoring_sla

monitoring_slo

monitoring_dependencies

monitoring_synthetic_tests

monitoring_reports

monitoring_statistics

monitoring_retention

monitoring_history

monitoring_audit

---

# MONITORING TARGETS

Support

Physical Servers

Virtual Machines

Containers

Kubernetes

Applications

Microservices

Databases

Storage

Network Devices

Cloud Resources

Industrial Controllers

Edge Devices

IoT Devices

Custom Targets

Target Groups

Dynamic Inventory

---

# METRIC COLLECTION

Collect

CPU Usage

Memory Usage

Disk Usage

Filesystem

IOPS

Latency

Bandwidth

Packet Loss

Process Status

Service Status

Application Metrics

Database Metrics

Network Metrics

Power Metrics

Temperature

Fan Speed

Redfish Metrics

Custom Metrics

---

# HEALTH MONITORING

Support

Heartbeat

Service Availability

Application Health

Infrastructure Health

Dependency Health

Component Health

Cluster Health

Overall Health Score

---

# AVAILABILITY

Track

Uptime

Downtime

Availability Percentage

Maintenance Windows

Outages

Recovery Time

Historical Availability

---

# PERFORMANCE

Monitor

Response Time

Throughput

Queue Length

Resource Utilization

Database Performance

Application Performance

Container Performance

Kubernetes Performance

Cloud Performance

---

# THRESHOLDS

Support

Static Thresholds

Dynamic Thresholds

Baseline Thresholds

Adaptive Thresholds

Percentage Thresholds

Time-based Thresholds

Custom Thresholds

---

# RULE ENGINE

Support

Metric Rules

Composite Rules

Dependency Rules

Rate-of-Change Rules

Anomaly Hooks

Window Aggregation

Correlation Rules

Escalation Triggers

---

# TIME SERIES

Support

High-frequency Metrics

Retention Policies

Downsampling

Compression

Aggregation

Historical Queries

Time-window Analysis

---

# SYNTHETIC MONITORING

Support

HTTP Checks

TCP Checks

DNS Checks

API Checks

SSH Checks

Database Checks

Custom Scripts

Scheduled Tests

---

# DEPENDENCY HEALTH

Integrate Prompt 036.

Support

Topology-aware Health

Parent/Child Health

Service Dependency

Application Dependency

Infrastructure Dependency

Blast Radius Calculation

---

# SLA / SLO

Track

Availability SLA

Performance SLA

Latency SLO

Error Budget

Objective Violations

Compliance Percentage

Reporting

---

# INTEGRATIONS

Inventory (Prompt 036)

Discovery (Prompt 037)

Configuration Management (Prompt 039)

Automation (Prompt 040)

Workflow Runtime (Prompt 042)

Validation (Prompt 043)

Future:

Alerting (Prompt 045)

Incident Management

AI Assistant

---

# ANALYTICS

Collect

Metric Trends

Capacity Trends

Availability Trends

Failure Trends

Resource Utilization

Growth Analysis

Forecasting Inputs

---

# REPORTING

Generate

Health Reports

Availability Reports

Performance Reports

Capacity Reports

Executive Dashboards

SLA Reports

SLO Reports

Historical Reports

---

# EVENTS

Publish

MetricCollected

HealthChanged

AvailabilityChanged

ThresholdExceeded

ThresholdRecovered

SyntheticTestFailed

DependencyChanged

SLOViolated

SLAViolated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Critical Health Change

Availability Issue

Synthetic Failure

Threshold Exceeded

Capacity Warning

Monitoring Failure

---

# TELEMETRY

Integrate Prompt 024.

Trace

Collectors

Metric Processing

Aggregation

Rule Evaluation

Time Series Storage

Dependency Resolution

Health Calculation

---

# AUDIT

Audit

Collector Configuration

Threshold Changes

Rule Changes

Synthetic Test Changes

Retention Policy Updates

Administrative Operations

---

# REST APIs

Implement

GET /monitoring/targets

POST /monitoring/targets

GET /monitoring/metrics

GET /monitoring/metrics/{id}

GET /monitoring/health

GET /monitoring/availability

GET /monitoring/performance

GET /monitoring/thresholds

POST /monitoring/thresholds

GET /monitoring/sla

GET /monitoring/slo

GET /monitoring/reports

GET /monitoring/statistics

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secure collector credentials

Audit all monitoring configuration changes

---

# PERFORMANCE

Distributed Collectors

Async Processing

Metric Batching

Time-series Optimization

Horizontal Scaling

Collector Auto-discovery

Caching

High Availability

---

# TESTING

Unit Tests

Integration Tests

Collector Tests

Rule Engine Tests

Health Calculation Tests

Time-series Tests

Performance Tests

Load Tests

Coverage >=95%

---

# DOCUMENTATION

README

Monitoring Guide

Collector Guide

Health Guide

Threshold Guide

SLA/SLO Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Monitoring Engine

✓ Distributed Collectors

✓ Time-series Storage

✓ Health Monitoring

✓ Availability Monitoring

✓ Performance Monitoring

✓ Synthetic Monitoring

✓ Dependency-aware Health

✓ SLA/SLO Tracking

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

Alerting Engine

Incident Management

AI Anomaly Detection

Dashboard UI

Business-specific monitoring

Only implement the Enterprise Monitoring Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate monitoring engine.

Generate distributed collectors.

Generate time-series processing.

Generate health engine.

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

End Prompt 044.
