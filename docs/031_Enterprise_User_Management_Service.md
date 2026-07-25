# AI Infrastructure Operating System (AI-IOS)

# Prompt 031

## Enterprise User Management Service

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

---

# ROLE

You are the Principal Identity Management Architect.

Implement the Enterprise User Management Service.

Do NOT redesign the platform.

Use all previously implemented shared frameworks.

---

# OBJECTIVE

Build a production-ready User Management Service responsible for managing the complete lifecycle of platform users.

This service SHALL NOT authenticate users.

Authentication belongs to Prompt 030.

This service manages

• User Profiles

• User Lifecycle

• Invitations

• User Preferences

• Contact Information

• Account Status

• User Search

• User Import

• User Export

• User Metadata

• Avatar Management

• User Activity

---

# SERVICE LOCATION

services/user-management-service/

---

# DIRECTORY STRUCTURE

user-management-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

validators/

workers/

events/

notifications/

middleware/

config/

tests/

migrations/

README.md

---

# DATABASE TABLES

Create

users

user_profiles

user_preferences

user_settings

user_addresses

user_contacts

user_metadata

user_avatars

user_invitations

user_import_jobs

user_export_jobs

user_activity

user_tags

user_notes

Do NOT create

RBAC Tables

Organization Tables

Authentication Tables

---

# USER MODEL

Every user shall contain

User ID

Username

Display Name

First Name

Middle Name

Last Name

Email

Phone Number

Avatar

Timezone

Language

Locale

Status

Created At

Updated At

Last Login

Metadata

---

# USER STATUS

Pending

Invited

Active

Inactive

Locked

Disabled

Deleted

Archived

Suspended

Status transitions shall be validated.

---

# USER PROFILE

Manage

Personal Information

Contact Information

Biography

Job Title

Department

Employee ID

Manager

Profile Photo

Custom Fields

---

# USER PREFERENCES

Support

Language

Theme

Timezone

Date Format

Time Format

Dashboard Preferences

Notification Preferences

Accessibility

Default Organization

Default Project

---

# USER SETTINGS

Store

Display Settings

Privacy

Security Preferences

Default Views

Shortcuts

Favorites

Feature Flags

---

# INVITATIONS

Support

Invite User

Resend Invitation

Accept Invitation

Reject Invitation

Invitation Expiration

Invitation Audit

Invitation Tokens

Bulk Invitations

---

# USER SEARCH

Support

Username

Email

Phone

Department

Status

Tags

Metadata

Full Text Search

Pagination

Sorting

Filtering

---

# IMPORT

CSV

Excel

JSON

Bulk Import

Validation

Duplicate Detection

Error Report

Preview

Rollback

---

# EXPORT

CSV

Excel

JSON

PDF

Filtered Export

Background Processing

Audit

---

# AVATAR MANAGEMENT

Upload

Replace

Delete

Resize

Thumbnail

Storage Integration

Validation

Virus Scan Hook

---

# USER ACTIVITY

Track

Profile Updates

Status Changes

Preference Changes

Invitation Events

Import

Export

Last Active

Login History Reference

---

# USER TAGS

Support

Labels

Groups

Categories

Custom Tags

Search

Filtering

---

# EVENTS

Publish

UserCreated

UserUpdated

UserDeleted

UserActivated

UserDeactivated

UserInvited

InvitationAccepted

ProfileUpdated

PreferencesUpdated

AvatarUpdated

UserImported

UserExported

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025

Send

Invitation

Invitation Reminder

Profile Updated

Account Activated

Account Suspended

Account Deleted

---

# TELEMETRY

Integrate Prompt 024

Trace

Profile Operations

Search

Import

Export

Invitation

Avatar Upload

---

# AUDIT

Audit

Create

Update

Delete

Import

Export

Invitation

Preference Changes

Status Changes

Metadata Updates

---

# REST APIs

Implement

GET /users

GET /users/{id}

POST /users

PUT /users/{id}

PATCH /users/{id}

DELETE /users/{id}

POST /users/search

POST /users/import

POST /users/export

POST /users/invite

POST /users/invite/resend

POST /users/invite/accept

POST /users/avatar

DELETE /users/avatar

GET /users/preferences

PUT /users/preferences

GET /users/activity

GET /users/tags

POST /users/tags

DELETE /users/tags/{id}

---

# SECURITY

Integrate Prompt 017

Permission Hooks

Tenant Validation

Rate Limiting

Input Validation

Secret Protection

Audit

---

# PERFORMANCE

Async APIs

Database Pagination

Background Import

Background Export

Cache Integration

Queue Integration

Horizontal Scaling

---

# TESTING

Unit Tests

Integration Tests

REST API Tests

Import Tests

Export Tests

Invitation Tests

Search Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

User Management Guide

Invitation Guide

Import Guide

Export Guide

API Reference

Developer Guide

Operations Guide

---

# ACCEPTANCE CRITERIA

✓ User CRUD

✓ User Profiles

✓ Preferences

✓ Settings

✓ Invitations

✓ Import

✓ Export

✓ Avatar Management

✓ User Search

✓ User Activity

✓ Events

✓ Notifications

✓ Audit

✓ REST APIs

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

Authentication

RBAC

Organizations

Projects

Automation

Inventory

Workflow Engine

Only the Enterprise User Management Service.

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

End Prompt 031.
