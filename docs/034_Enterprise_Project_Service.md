# AI Infrastructure Operating System (AI-IOS)

# Prompt 034

## Enterprise Project Service

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

---

# ROLE

You are the Principal Enterprise Platform Architect.

Implement the Enterprise Project Service.

Use all previously implemented platform frameworks.

Do NOT redesign the architecture.

Implement a production-ready Project Management Service.

---

# OBJECTIVE

Build a centralized Project Service responsible for organizing enterprise resources within an organization.

Every infrastructure resource, inventory asset, workflow, automation, validation job, connector, AI assistant, report, dashboard, and secret SHALL belong to a Project.

Projects SHALL provide isolation, ownership, governance, lifecycle management, quotas, auditing, and collaboration.

---

# SERVICE LOCATION

services/project-service/

---

# DIRECTORY STRUCTURE

project-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

projects/

members/

roles/

settings/

metadata/

tags/

templates/

favorites/

archives/

analytics/

events/

notifications/

validators/

middleware/

workers/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

projects

project_settings

project_preferences

project_metadata

project_members

project_roles

project_tags

project_labels

project_templates

project_favorites

project_activity

project_statistics

project_archives

project_resources

project_integrations

project_notes

project_audit

---

# PROJECT MODEL

Every project shall contain

Project ID

Organization ID

Name

Display Name

Description

Code

Status

Owner

Visibility

Default Language

Timezone

Category

Priority

Created At

Updated At

Archived At

Metadata

---

# PROJECT STATUS

Draft

Planning

Active

Maintenance

Archived

Suspended

Completed

Deleted

Status transitions shall be validated.

---

# PROJECT VISIBILITY

Private

Internal

Organization

Public (Optional)

---

# PROJECT SETTINGS

Support

Default Environment

Default Connector

Default Workflow Runtime

Notification Settings

Retention Policies

Execution Policies

Automation Policies

Validation Policies

Monitoring Policies

AI Settings

Storage Policies

Security Policies

---

# PROJECT MEMBERS

Support

Invite Member

Remove Member

Transfer Ownership

Assign Roles

Deactivate Member

Reactivate Member

Track Membership History

---

# PROJECT ROLES

Support

Owner

Administrator

Operator

Automation Engineer

Validation Engineer

Developer

Viewer

Auditor

Custom Roles

Integrate with Prompt 032.

---

# PROJECT TAGS

Support

Custom Tags

Labels

Categories

Search

Filtering

Bulk Assignment

---

# PROJECT TEMPLATES

Support reusable project templates

Infrastructure Projects

Automation Projects

Validation Projects

Industrial Projects

Cloud Projects

Hybrid Projects

Custom Templates

Template Versioning

---

# PROJECT RESOURCES

Track associated resources

Inventory Assets

Discovered Assets

Connectors

Credentials

Secrets

Automation Jobs

Workflow Definitions

Workflow Executions

Validation Profiles

Monitoring Profiles

Dashboards

Reports

AI Agents

Knowledge Bases

Storage Objects

Plugins

---

# PROJECT ANALYTICS

Collect

Member Count

Automation Count

Workflow Count

Validation Count

Inventory Count

Connector Count

AI Usage

Storage Usage

Execution Statistics

Failure Rates

Success Rates

Activity Trends

---

# PROJECT LIFECYCLE

Support

Create

Clone

Archive

Restore

Export

Import

Transfer Ownership

Soft Delete

Permanent Delete

---

# EVENTS

Publish

ProjectCreated

ProjectUpdated

ProjectArchived

ProjectRestored

ProjectDeleted

ProjectCloned

ProjectMemberAdded

ProjectMemberRemoved

ProjectRoleChanged

ProjectOwnershipTransferred

ProjectSettingsUpdated

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Project Created

Invitation Sent

Invitation Accepted

Ownership Changed

Project Archived

Project Restored

Project Deleted

---

# TELEMETRY

Integrate Prompt 024

Trace

Project CRUD

Membership Changes

Settings Updates

Project Search

Analytics Collection

Lifecycle Operations

---

# AUDIT

Audit

Project Creation

Updates

Deletion

Membership Changes

Role Changes

Ownership Changes

Settings Updates

Template Usage

Resource Linking

Administrative Operations

---

# SEARCH

Support

Project Name

Project Code

Tags

Labels

Owner

Status

Organization

Metadata

Full Text Search

Pagination

Sorting

Filtering

---

# IMPORT

Support

JSON

YAML

CSV

ZIP Package

Validation

Preview

Conflict Detection

Rollback

---

# EXPORT

Support

JSON

YAML

ZIP Package

PDF Summary

Background Processing

Audit Logging

---

# REST APIs

Implement

GET /projects

GET /projects/{id}

POST /projects

PUT /projects/{id}

PATCH /projects/{id}

DELETE /projects/{id}

POST /projects/{id}/clone

POST /projects/{id}/archive

POST /projects/{id}/restore

POST /projects/import

POST /projects/export

GET /projects/{id}/members

POST /projects/{id}/members

DELETE /projects/{id}/members/{memberId}

PUT /projects/{id}/members/{memberId}/roles

GET /projects/{id}/settings

PUT /projects/{id}/settings

GET /projects/{id}/analytics

GET /projects/search

GET /projects/templates

POST /projects/templates

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 033.

Validate

Organization ownership

Project membership

Role permissions

Tenant isolation

Cross-project access prevention

Audit all administrative operations.

---

# PERFORMANCE

Async APIs

Caching

Background Analytics

Queue Integration

Bulk Operations

Efficient Pagination

Optimized Search

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

Membership Tests

Role Tests

Lifecycle Tests

Import Tests

Export Tests

Analytics Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Project Management Guide

Project Templates Guide

Membership Guide

Analytics Guide

Import/Export Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Project CRUD

✓ Membership Management

✓ Project Roles

✓ Project Settings

✓ Project Templates

✓ Project Analytics

✓ Import

✓ Export

✓ Search

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

Inventory

Discovery

Automation

Workflow Runtime

Validation

Monitoring

Secrets

Connector Execution

Business-specific logic

Only implement the Enterprise Project Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate complete REST APIs.

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

End Prompt 034.
