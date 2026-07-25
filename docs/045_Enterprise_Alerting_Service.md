# AI Infrastructure Operating System (AI-IOS)

# Prompt 045

## Enterprise Alerting Service

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
Prompt 044

---

# ROLE

You are the Principal Enterprise Alerting Architect.

Implement the Enterprise Alerting Service.

Use every previously implemented framework.

Do NOT redesign the platform.

Implement a production-ready intelligent alerting platform.

---

# OBJECTIVE

Build a centralized Alerting Service responsible for detecting, correlating, deduplicating, suppressing, routing, escalating, tracking, and resolving enterprise operational alerts.

The Alerting Service SHALL consume events from Monitoring, Validation, Automation, Workflow Runtime, Configuration Management, Discovery, Inventory, and future AI services.

The service SHALL act as the operational nervous system of AI-IOS.

---

# SERVICE LOCATION

services/alerting-service/

---

# DIRECTORY STRUCTURE

alerting-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

alerts/

rules/

conditions/

evaluation/

correlation/

deduplication/

suppression/

routing/

escalation/

acknowledgements/

maintenance/

schedules/

notifications/

analytics/

reports/

events/

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

alert_rules

alert_conditions

alert_instances

alert_history

alert_correlation

alert_suppression

alert_deduplication

alert_routes

alert_escalation

alert_acknowledgements

alert_maintenance_windows

alert_oncall_schedules

alert_notifications

alert_statistics

alert_reports

alert_audit

---

# ALERT SOURCES

Monitoring

Validation

Automation

Workflow Runtime

Configuration Management

Discovery

Inventory

System Events

Application Events

Custom Events

Future AI Events

---

# ALERT SEVERITY

Critical

High

Medium

Low

Informational

---

# ALERT STATUS

New

Open

Acknowledged

Investigating

Suppressed

Escalated

Resolved

Closed

Expired

---

# RULE ENGINE

Support

Metric Threshold Rules

Validation Rules

Composite Rules

Dependency Rules

Time Window Rules

Rate of Change

Pattern Matching

Boolean Logic

Event Aggregation

Custom Expressions

---

# CORRELATION

Support

Topology Correlation

Time Correlation

Dependency Correlation

Application Correlation

Infrastructure Correlation

Service Correlation

Workflow Correlation

Custom Correlation Rules

---

# DEDUPLICATION

Support

Duplicate Detection

Fingerprinting

Hash Matching

Time Window Deduplication

Rule-based Deduplication

Event Consolidation

---

# SUPPRESSION

Support

Maintenance Windows

Scheduled Suppression

Dependency Suppression

Parent/Child Suppression

Temporary Suppression

Rule-based Suppression

Manual Suppression

---

# ROUTING

Support

Email

SMS

Slack

Microsoft Teams

Discord

Webhooks

PagerDuty

ServiceNow

Opsgenie

Custom Connectors

Role-based Routing

Organization Routing

Project Routing

---

# ESCALATION

Support

Escalation Policies

Time-based Escalation

Multi-level Escalation

Automatic Escalation

Manager Escalation

On-call Escalation

Workflow Escalation

---

# ACKNOWLEDGEMENT

Support

Manual Acknowledgement

Automatic Acknowledgement

Ownership

Assignment

Comments

Resolution Notes

Audit History

---

# MAINTENANCE WINDOWS

Support

Scheduled Windows

Recurring Windows

Emergency Windows

Asset Scope

Group Scope

Organization Scope

Project Scope

---

# ON-CALL MANAGEMENT

Support

Schedules

Rotations

Time Zones

Escalation Chains

Overrides

Holiday Calendars

---

# ANALYTICS

Collect

Alert Volume

Alert Frequency

Top Alert Sources

Top Rules

Noise Ratio

Suppression Rate

Resolution Time

MTTA

MTTR

Escalation Statistics

---

# REPORTING

Generate

Alert Reports

Executive Reports

Operational Reports

SLA Reports

Escalation Reports

Trend Reports

Noise Analysis

---

# EVENTS

Publish

AlertCreated

AlertAcknowledged

AlertEscalated

AlertSuppressed

AlertResolved

AlertClosed

AlertExpired

AlertNotificationSent

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Support

Email

Slack

Teams

Webhook

SMS

PagerDuty

ServiceNow

Custom Providers

Retry

Delivery Tracking

---

# TELEMETRY

Integrate Prompt 024.

Trace

Rule Evaluation

Correlation

Notification Delivery

Escalation

Routing

Acknowledgements

---

# AUDIT

Audit

Rule Changes

Alert Lifecycle

Escalation

Acknowledgements

Suppression

Maintenance Changes

Administrative Operations

---

# REST APIs

Implement

GET /alerts

GET /alerts/{id}

POST /alerts

PUT /alerts/{id}

DELETE /alerts/{id}

POST /alerts/{id}/acknowledge

POST /alerts/{id}/resolve

POST /alerts/{id}/escalate

GET /alert-rules

POST /alert-rules

GET /maintenance-windows

POST /maintenance-windows

GET /oncall-schedules

POST /oncall-schedules

GET /alert-statistics

GET /alert-reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Audit every alert lifecycle event

Secure notification credentials

---

# PERFORMANCE

Async Rule Evaluation

Distributed Workers

Queue Integration

Event Batching

Horizontal Scaling

High Availability

Caching

---

# TESTING

Unit Tests

Integration Tests

Rule Engine Tests

Correlation Tests

Deduplication Tests

Escalation Tests

Notification Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Alerting Guide

Rule Engine Guide

Correlation Guide

Escalation Guide

Maintenance Window Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Alert Rule Engine

✓ Correlation Engine

✓ Deduplication

✓ Suppression

✓ Routing

✓ Escalation

✓ On-call Management

✓ Maintenance Windows

✓ Notification Integration

✓ Analytics

✓ Reports

✓ Events

✓ Audit

✓ REST APIs

✓ Database Migrations

✓ OpenAPI Documentation

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Incident Management

AI Alert Prioritization

Dashboard UI

Business-specific alert rules

Only implement the Enterprise Alerting Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate alert evaluation engine.

Generate correlation engine.

Generate routing engine.

Generate escalation engine.

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

End Prompt 045.
