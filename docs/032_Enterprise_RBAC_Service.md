# AI Infrastructure Operating System (AI-IOS)

# Prompt 032

## Enterprise RBAC Service

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

---

# ROLE

You are the Principal Authorization Architect.

Implement the Enterprise RBAC Service.

Do NOT redesign the platform.

Use all previously implemented frameworks.

Implement a production-ready authorization system.

---

# OBJECTIVE

Build a centralized authorization service responsible for controlling access across the entire AI-IOS platform.

The service shall support

- Role-Based Access Control (RBAC)
- Permission Management
- Policy Engine
- Resource-Based Authorization
- Hierarchical Roles
- Organization Roles
- Project Roles
- Custom Roles
- Permission Groups
- Dynamic Permissions
- Permission Evaluation
- Authorization Cache
- Audit
- REST APIs

---

# SERVICE LOCATION

services/rbac-service/

---

# DIRECTORY STRUCTURE

rbac-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

authorization/

permissions/

roles/

policies/

resources/

evaluators/

cache/

events/

workers/

middleware/

validators/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

roles

permissions

permission_groups

role_permissions

user_roles

organization_roles

project_roles

resource_permissions

authorization_policies

policy_conditions

policy_assignments

permission_cache

authorization_audit

---

# ROLE TYPES

System Role

Organization Role

Project Role

Custom Role

Temporary Role

Read-Only Role

Service Role

---

# DEFAULT SYSTEM ROLES

Platform Administrator

Organization Administrator

Project Administrator

Operator

Automation Engineer

Validation Engineer

Viewer

Auditor

API Client

Service Account

---

# PERMISSION MODEL

Every permission shall contain

Permission ID

Name

Code

Description

Category

Resource

Action

Scope

Status

Version

Metadata

---

# PERMISSION ACTIONS

Create

Read

Update

Delete

Execute

Approve

Import

Export

Assign

Manage

Configure

Audit

Monitor

Schedule

Deploy

Rollback

---

# RESOURCE TYPES

Users

Organizations

Projects

Assets

Inventory

Automation

Workflows

Validation

Monitoring

Notifications

Reports

Dashboards

Plugins

Connectors

Settings

Secrets

AI

Storage

Scheduler

API Keys

---

# ROLE HIERARCHY

Support

Inheritance

Parent Roles

Child Roles

Permission Aggregation

Recursive Evaluation

Circular Dependency Detection

---

# PERMISSION GROUPS

Support

Infrastructure

Automation

Validation

Monitoring

Security

Administration

AI

Reporting

Custom Groups

---

# POLICY ENGINE

Support

Allow

Deny

Conditional Access

Time-Based Access

Location-Based Access

IP-Based Access

Organization Scope

Project Scope

Resource Scope

Custom Rules

---

# RESOURCE AUTHORIZATION

Support

Resource Owner

Organization Scope

Project Scope

Shared Resources

Public Resources

Private Resources

Inherited Permissions

---

# AUTHORIZATION EVALUATION

Evaluate

User

Role

Permissions

Policies

Conditions

Resource Ownership

Tenant

Environment

Decision

Return

Allow

Deny

Reason

---

# CACHING

Cache

Permissions

Roles

Policy Results

Authorization Decisions

User Permission Matrix

Integrate with Prompt 019.

---

# EVENTS

Publish

RoleCreated

RoleUpdated

RoleDeleted

PermissionCreated

PermissionUpdated

PermissionDeleted

RoleAssigned

RoleRemoved

PolicyCreated

PolicyUpdated

PolicyDeleted

AuthorizationDenied

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Notify

Role Assignment

Permission Changes

Policy Changes

Security Violations

Unauthorized Access Attempts

---

# TELEMETRY

Integrate Prompt 024

Trace

Authorization Evaluation

Policy Evaluation

Permission Lookup

Role Assignment

Permission Cache

---

# AUDIT

Audit

Role Creation

Role Update

Role Assignment

Permission Changes

Policy Changes

Authorization Decisions

Privilege Escalation Attempts

Administrative Actions

---

# REST APIs

Implement

GET /roles

GET /roles/{id}

POST /roles

PUT /roles/{id}

DELETE /roles/{id}

GET /permissions

POST /permissions

PUT /permissions/{id}

DELETE /permissions/{id}

POST /roles/{id}/permissions

DELETE /roles/{id}/permissions/{permissionId}

POST /users/{id}/roles

DELETE /users/{id}/roles/{roleId}

GET /users/{id}/permissions

POST /authorization/evaluate

POST /policies

GET /policies

PUT /policies/{id}

DELETE /policies/{id}

GET /permission-groups

POST /permission-groups

---

# SECURITY

Integrate Prompt 017.

Validate tenant isolation.

Prevent privilege escalation.

Prevent circular role inheritance.

Validate every authorization request.

Enforce least privilege.

---

# PERFORMANCE

Permission caching

Async APIs

Efficient policy evaluation

Batch authorization

Horizontal scaling

Distributed cache

---

# TESTING

Unit Tests

Integration Tests

Permission Tests

Role Hierarchy Tests

Policy Tests

Authorization Tests

Cache Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

RBAC Guide

Permission Guide

Policy Guide

Role Hierarchy Guide

API Reference

Developer Guide

Operations Guide

Examples

---

# ACCEPTANCE CRITERIA

✓ Role Management

✓ Permission Management

✓ Permission Groups

✓ Role Hierarchy

✓ Policy Engine

✓ Resource Authorization

✓ Authorization Evaluation

✓ Permission Cache

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

Authentication

Organizations

Projects

Inventory

Automation

Workflow Engine

Business Logic

Only the Enterprise RBAC Service.

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

End Prompt 032.
