# AI Infrastructure Operating System (AI-IOS)

# Prompt 040

## Enterprise Automation Service

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

---

# ROLE

You are the Principal Enterprise Automation Architect.

Implement the Enterprise Automation Service.

Use every previously implemented framework.

Do NOT redesign the platform.

Implement a production-ready enterprise automation and orchestration engine.

---

# OBJECTIVE

Build a centralized Automation Service responsible for executing infrastructure automation across on-premises, cloud, edge, Kubernetes, virtualization, and industrial environments.

Automation SHALL support playbooks, workflows, scripts, TOSCA deployments, configuration enforcement, validation execution, operational tasks, and scheduled jobs.

Automation SHALL integrate with Workflow SDK, Connector SDK, Inventory, Configuration Management, Secrets Management, Scheduler, Queue Framework, and RBAC.

---

# SERVICE LOCATION

services/automation-service/

---

# DIRECTORY STRUCTURE

automation-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

automation/

jobs/

executions/

playbooks/

execution_plans/

runners/

dispatchers/

connectors/

workflow/

ansible/

tosca/

scripts/

approvals/

rollback/

retry/

logs/

outputs/

artifacts/

variables/

inventory/

scheduling/

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

automation_jobs

automation_templates

automation_executions

automation_execution_steps

automation_execution_logs

automation_artifacts

automation_outputs

automation_variables

automation_parameters

automation_targets

automation_schedules

automation_execution_plans

automation_retry_history

automation_rollbacks

automation_approvals

automation_results

automation_statistics

automation_reports

automation_audit

---

# AUTOMATION TYPES

Infrastructure Automation

Configuration Automation

Provisioning

Decommissioning

Deployment

Patch Management

Software Installation

Firmware Upgrade

OS Configuration

Validation Execution

Discovery Execution

Monitoring Actions

Database Automation

Cloud Automation

Container Automation

Kubernetes Automation

Industrial Automation

Security Automation

Backup Automation

Custom Automation

---

# EXECUTION TARGETS

Physical Servers

Virtual Machines

Containers

Kubernetes

Cloud Resources

Storage Systems

Switches

Routers

Firewalls

Industrial Controllers

Applications

Databases

Custom Targets

Target Groups

Dynamic Inventory

---

# EXECUTION MODES

Immediate

Scheduled

Workflow Triggered

Event Triggered

Webhook Triggered

API Triggered

Manual

Approval Required

Continuous

---

# PLAYBOOK SUPPORT

Support

Ansible Playbooks

Python Scripts

Shell Scripts

PowerShell

Bash

TOSCA Service Templates

Custom Plugins

Workflow Tasks

Future DSL Support

---

# EXECUTION ENGINE

Support

Sequential Execution

Parallel Execution

Distributed Execution

Conditional Execution

Loop Execution

Matrix Execution

Fan-Out

Fan-In

Checkpointing

Resume

Pause

Cancel

Timeout

Execution Priority

---

# EXECUTION PLANS

Support

Pre-check Tasks

Preparation

Validation

Execution

Post-validation

Cleanup

Notifications

Rollback Planning

Approval Gates

---

# WORKFLOW INTEGRATION

Integrate Prompt 028.

Support

Workflow Trigger

Workflow Task Execution

Workflow Callbacks

Workflow Events

Execution Context

Shared Variables

---

# CONNECTOR INTEGRATION

Integrate Prompt 027.

Support

SSH

WinRM

Redfish

SNMP

REST

gRPC

VMware

Kubernetes

Cloud Providers

Industrial Protocols

Plugin Connectors

---

# INVENTORY INTEGRATION

Integrate Prompt 036.

Support

Dynamic Inventory

Asset Groups

Labels

Tags

Topology Queries

Relationship-aware Execution

---

# CONFIGURATION MANAGEMENT

Integrate Prompt 039.

Support

Desired State Enforcement

Configuration Deployment

Drift Remediation

Baseline Deployment

Configuration Validation

---

# SECRETS MANAGEMENT

Integrate Prompt 035.

Support

Credential Injection

SSH Keys

Certificates

API Keys

Vault References

Temporary Credentials

Secrets SHALL never be logged.

---

# APPROVALS

Support

Single Approval

Multi-Level Approval

Conditional Approval

Role-Based Approval

Approval Expiration

Approval History

Emergency Override

---

# RETRY

Support

Immediate Retry

Delayed Retry

Exponential Backoff

Retry Policies

Retry Limits

Failure Classification

---

# ROLLBACK

Support

Step Rollback

Execution Rollback

Configuration Rollback

Playbook Rollback

Automatic Rollback

Manual Rollback

Rollback Validation

Rollback Reports

---

# LOGGING

Capture

Execution Logs

Console Output

Structured Logs

Connector Logs

Timing

Errors

Warnings

Execution Metadata

---

# ARTIFACTS

Store

Execution Reports

Generated Files

Playbook Outputs

Logs

Configuration Snapshots

Validation Results

Attachments

---

# ANALYTICS

Collect

Execution Count

Success Rate

Failure Rate

Average Runtime

Resource Usage

Connector Usage

Automation Trends

Top Failed Jobs

Most Executed Jobs

Execution Heatmaps

---

# REPORTING

Generate

Execution Reports

Failure Reports

Success Reports

Performance Reports

Compliance Reports

Executive Dashboards

Automation Trends

---

# EVENTS

Publish

AutomationCreated

AutomationStarted

AutomationCompleted

AutomationFailed

AutomationCancelled

AutomationPaused

AutomationResumed

ApprovalRequested

ApprovalGranted

RollbackStarted

RollbackCompleted

ExecutionTimedOut

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Execution Started

Execution Completed

Execution Failed

Approval Required

Rollback Completed

Critical Failure

Long Running Job

Schedule Missed

---

# TELEMETRY

Integrate Prompt 024.

Trace

Execution Engine

Connector Calls

Workflow Execution

Inventory Resolution

Secrets Access

Execution Timing

Queue Operations

---

# AUDIT

Audit

Automation Creation

Execution

Cancellation

Approval

Rollback

Configuration Changes

Target Selection

Administrative Operations

---

# REST APIs

Implement

GET /automation/jobs

GET /automation/jobs/{id}

POST /automation/jobs

PUT /automation/jobs/{id}

DELETE /automation/jobs/{id}

POST /automation/jobs/{id}/execute

POST /automation/jobs/{id}/cancel

POST /automation/jobs/{id}/pause

POST /automation/jobs/{id}/resume

GET /automation/executions

GET /automation/executions/{id}

GET /automation/executions/{id}/logs

GET /automation/executions/{id}/artifacts

POST /automation/templates

GET /automation/templates

GET /automation/statistics

GET /automation/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

Role-based authorization

Approval validation

Secure credential injection

Audit every execution

Prevent privilege escalation

---

# PERFORMANCE

Async Execution

Distributed Workers

Queue Framework Integration

Parallel Execution

Connection Pooling

Execution Caching

Horizontal Scaling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Execution Engine Tests

Workflow Integration Tests

Connector Tests

Retry Tests

Rollback Tests

Approval Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Automation Guide

Execution Engine Guide

Playbook Guide

Workflow Integration Guide

Connector Guide

Rollback Guide

Approval Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Automation CRUD

✓ Execution Engine

✓ Execution Plans

✓ Workflow Integration

✓ Connector Integration

✓ Inventory Integration

✓ Configuration Enforcement

✓ Secret Injection

✓ Approval Workflow

✓ Retry Engine

✓ Rollback Engine

✓ Execution Logs

✓ Artifacts

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

Monitoring Engine

Validation Engine

AI Assistant

Incident Management

Business-specific automation

Only implement the Enterprise Automation Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate complete REST APIs.

Generate execution engine.

Generate workflow integration.

Generate connector integration.

Generate rollback engine.

Generate approval engine.

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

End Prompt 040.
