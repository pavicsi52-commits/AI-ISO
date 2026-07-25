# AI Infrastructure Operating System (AI-IOS)

# Prompt 052

## Enterprise Incident Management Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 051

---

# ROLE

You are the Principal Enterprise Incident Management Architect.

Implement the Enterprise Incident Management Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise Incident Management platform.

---

# OBJECTIVE

Build a centralized Incident Management Service responsible for detecting, tracking, coordinating, resolving, auditing, and analyzing operational incidents across AI-IOS.

The Incident Management Service SHALL integrate with Monitoring, Alerting, Automation, Workflow Runtime, Validation, Knowledge Graph, Reporting, AI Assistant, Compliance, and Policy Engine.

The service SHALL support the complete incident lifecycle from creation through post-incident review.

---

# SERVICE LOCATION

services/incident-management-service/

---

# DIRECTORY STRUCTURE

incident-management-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

incidents/

major_incidents/

war_rooms/

timelines/

root_cause/

impact/

sla/

assignment/

escalation/

communication/

automation/

playbooks/

workflows/

postmortem/

problems/

known_errors/

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

incidents

incident_categories

incident_priorities

incident_status

incident_assignments

incident_timelines

incident_impacts

incident_services

incident_assets

incident_root_causes

incident_worklogs

incident_escalations

incident_slas

incident_major_events

incident_war_rooms

incident_postmortems

problem_records

known_errors

incident_reports

incident_statistics

incident_audit

---

# INCIDENT SOURCES

Monitoring

Alerting

Validation

Automation

Workflow Runtime

Configuration Management

Knowledge Graph

Manual Creation

REST API

Webhook

Email

Custom Sources

---

# INCIDENT CATEGORIES

Infrastructure

Application

Database

Network

Storage

Cloud

Kubernetes

Container

Security

Compliance

Automation

Workflow

Configuration

Industrial

Edge

Service Availability

Performance

Capacity

Backup

Disaster Recovery

Custom

---

# PRIORITY LEVELS

P1 Critical

P2 High

P3 Medium

P4 Low

P5 Informational

---

# INCIDENT STATUS

New

Assigned

Acknowledged

Investigating

Mitigating

Monitoring

Resolved

Closed

Cancelled

Merged

---

# INCIDENT LIFECYCLE

Support

Creation

Classification

Assignment

Investigation

Root Cause Analysis

Mitigation

Resolution

Verification

Closure

Post Incident Review

Knowledge Capture

---

# MAJOR INCIDENT MANAGEMENT

Support

Major Incident Declaration

Incident Commander

Communication Lead

Technical Lead

Business Lead

Stakeholder Notifications

Status Updates

Executive Summary

Major Incident Timeline

Closure Approval

---

# WAR ROOMS

Support

Virtual War Room

Participants

Roles

Timeline

Shared Notes

Shared Artifacts

Automation Actions

Workflow Execution

Recording Metadata

---

# ROOT CAUSE ANALYSIS

Support

Manual RCA

Dependency Analysis

Knowledge Graph Traversal

Alert Correlation

Validation Results

Automation History

Configuration Drift

AI-assisted RCA

Five Whys

Fishbone Analysis

Timeline Correlation

---

# IMPACT ANALYSIS

Integrate Prompt 049.

Support

Affected Services

Affected Assets

Business Impact

Customer Impact

Topology Impact

Blast Radius

Dependency Analysis

Risk Level

---

# SLA MANAGEMENT

Support

Response SLA

Acknowledgement SLA

Resolution SLA

Escalation SLA

Business Hours

24x7 SLA

Pause Conditions

Violation Tracking

---

# ASSIGNMENT

Support

Users

Teams

On-call Rotations

Skill-based Assignment

Manual Assignment

Automatic Assignment

Load Balancing

Ownership Transfer

---

# ESCALATION

Support

Time-based Escalation

Role Escalation

Manager Escalation

Executive Escalation

Workflow Escalation

Automation Escalation

Policy-based Escalation

---

# AUTOMATION INTEGRATION

Integrate Prompt 040.

Support

Automatic Remediation

Playbook Execution

Rollback Execution

Recovery Actions

Validation After Recovery

Execution History

---

# WORKFLOW INTEGRATION

Integrate Prompt 042.

Support

Incident Workflow

Approval Workflow

Escalation Workflow

Recovery Workflow

Postmortem Workflow

---

# PLAYBOOK INTEGRATION

Integrate Prompt 041.

Support

Recovery Playbooks

Diagnostic Playbooks

Validation Playbooks

Operational Runbooks

---

# PROBLEM MANAGEMENT

Support

Problem Records

Recurring Incident Detection

Known Error Database

Permanent Fix Tracking

Relationship to Incidents

Trend Analysis

---

# POST INCIDENT REVIEW

Support

Executive Summary

Timeline

Root Cause

Impact

Lessons Learned

Action Items

Owners

Due Dates

Verification

Approval

---

# AI INTEGRATION

Integrate Prompt 046.

Support

Incident Summary

Root Cause Suggestions

Impact Summary

Recovery Recommendations

Executive Summary

Timeline Generation

Next Best Actions

Knowledge Suggestions

---

# ANALYTICS

Collect

Incident Count

Incident Trends

MTTA

MTTR

SLA Compliance

Escalation Statistics

Major Incident Statistics

Recurring Incidents

Resolution Trends

Automation Success

---

# REPORTING

Generate

Incident Reports

Executive Reports

Major Incident Reports

SLA Reports

Root Cause Reports

Problem Reports

Postmortem Reports

Trend Reports

---

# EVENTS

Publish

IncidentCreated

IncidentAssigned

IncidentAcknowledged

IncidentEscalated

IncidentResolved

IncidentClosed

MajorIncidentDeclared

PostmortemCompleted

ProblemCreated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Incident Created

Assignment

Escalation

Major Incident

SLA Breach

Resolution

Postmortem Due

---

# TELEMETRY

Integrate Prompt 024.

Trace

Incident Lifecycle

Assignment

Escalation

Automation

Workflow

AI Recommendations

Reporting

---

# AUDIT

Audit

Incident Creation

Status Changes

Assignments

Escalations

Approvals

Postmortems

Administrative Operations

---

# REST APIs

Implement

GET /incidents

GET /incidents/{id}

POST /incidents

PUT /incidents/{id}

DELETE /incidents/{id}

POST /incidents/{id}/assign

POST /incidents/{id}/acknowledge

POST /incidents/{id}/resolve

POST /incidents/{id}/close

POST /incidents/{id}/escalate

GET /incidents/{id}/timeline

GET /incidents/{id}/postmortem

POST /incidents/{id}/postmortem

GET /problems

POST /problems

GET /known-errors

POST /known-errors

GET /incident/statistics

GET /incident/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secure evidence storage

Immutable audit history

Role-based incident visibility

---

# PERFORMANCE

Async Incident Processing

Queue Integration

Parallel Notifications

Caching

Horizontal Scaling

High Availability

Real-time Status Updates

---

# TESTING

Unit Tests

Integration Tests

Incident Lifecycle Tests

SLA Tests

Escalation Tests

Automation Integration Tests

Workflow Tests

AI Integration Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Incident Management Guide

Major Incident Guide

War Room Guide

Problem Management Guide

Postmortem Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Incident Lifecycle Management

✓ Major Incident Management

✓ War Rooms

✓ Root Cause Analysis

✓ Impact Analysis

✓ SLA Management

✓ Assignment Engine

✓ Escalation Engine

✓ Automation Integration

✓ Workflow Integration

✓ Problem Management

✓ Known Error Database

✓ AI Integration

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

ITSM Change Management

CMDB (handled by Inventory & Knowledge Graph)

External ITSM Integrations

Business-specific Incident Workflows

Only implement the Enterprise Incident Management Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate incident lifecycle engine.

Generate SLA engine.

Generate escalation engine.

Generate postmortem engine.

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

End Prompt 052.
