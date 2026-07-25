# AI Infrastructure Operating System (AI-IOS)

# Prompt 055

## Enterprise Notification Center Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 054

---

# ROLE

You are the Principal Enterprise Communication Architect.

Implement the Enterprise Notification Center Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready centralized enterprise notification platform.

---

# OBJECTIVE

Build a centralized Notification Center Service responsible for receiving platform events, routing notifications, managing templates, delivering notifications through multiple communication channels, tracking delivery status, and maintaining complete notification history.

The Notification Center SHALL provide reliable, scalable, auditable, and configurable notification delivery across every AI-IOS service.

---

# SERVICE LOCATION

services/notification-center-service/

---

# DIRECTORY STRUCTURE

notification-center-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

channels/

email/

sms/

slack/

teams/

discord/

webhooks/

push/

in_app/

templates/

localization/

preferences/

subscriptions/

broadcast/

announcements/

delivery/

queue/

retry/

dead_letter/

tracking/

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

notifications

notification_channels

notification_templates

notification_template_versions

notification_preferences

notification_subscriptions

notification_deliveries

notification_delivery_attempts

notification_retry_queue

notification_dead_letters

notification_announcements

notification_broadcasts

notification_statistics

notification_reports

notification_audit

---

# NOTIFICATION CHANNELS

Support

Email

SMS

Slack

Microsoft Teams

Discord

Webhook

Mobile Push

Browser Push

In-App Notifications

REST Callback

Custom Channels

---

# EVENT SOURCES

Automation

Workflow Runtime

Validation

Monitoring

Alerting

Dashboard

Knowledge Graph

Policy Engine

Compliance

Incident Management

Change Management

Scheduler

Reporting

Administration

AI Assistant

Custom Events

---

# NOTIFICATION TYPES

Alert

Warning

Information

Success

Failure

Critical

Reminder

Approval Request

Assignment

System Announcement

Maintenance Notice

Digest

Custom

---

# TEMPLATE MANAGEMENT

Support

Plain Text Templates

HTML Templates

Markdown Templates

Rich Templates

Template Variables

Conditional Rendering

Reusable Components

Template Versioning

Preview

Testing

---

# LOCALIZATION

Support

Multiple Languages

Locale Detection

Fallback Language

Localized Templates

Localized Variables

Localized Date Formats

Localized Number Formats

---

# USER PREFERENCES

Support

Preferred Channels

Preferred Language

Notification Categories

Mute Categories

Quiet Hours

Do Not Disturb

Priority Overrides

Digest Preferences

Device Preferences

---

# SUBSCRIPTIONS

Support

Event Subscription

Category Subscription

Role Subscription

Project Subscription

Organization Subscription

Topic Subscription

Webhook Subscription

Custom Subscription

---

# DELIVERY MANAGEMENT

Support

Immediate Delivery

Scheduled Delivery

Delayed Delivery

Bulk Delivery

Broadcast Delivery

Priority Delivery

Rate Limiting

Delivery Windows

---

# RETRY MANAGEMENT

Support

Retry Queue

Retry Policies

Exponential Backoff

Maximum Attempts

Dead Letter Queue

Manual Retry

Automatic Retry

Retry Reports

---

# DELIVERY TRACKING

Track

Queued

Sent

Delivered

Read

Acknowledged

Failed

Expired

Cancelled

Delivery Time

Response Metadata

---

# ANNOUNCEMENTS

Support

System Announcements

Organization Announcements

Project Announcements

Maintenance Announcements

Broadcast Messages

Pinned Announcements

Expiration Dates

Audience Targeting

---

# IN-APP NOTIFICATION CENTER

Support

Notification Feed

Read/Unread

Pin

Archive

Delete

Search

Filter

Grouping

Pagination

Real-time Updates

---

# TARGETING

Support

Users

Teams

Roles

Organizations

Projects

Groups

Regions

Environments

Custom Audiences

---

# PLATFORM INTEGRATIONS

Integrate

Authentication (030)

RBAC (032)

Organizations (033)

Projects (034)

Automation (040)

Workflow Runtime (042)

Validation (043)

Monitoring (044)

Alerting (045)

AI Assistant (046)

Reporting (047)

Policy Engine (050)

Incident Management (052)

Change Management (053)

Scheduler (054)

---

# ANALYTICS

Collect

Notifications Sent

Delivery Success

Delivery Failures

Average Delivery Time

Read Rate

Acknowledgement Rate

Retry Rate

Channel Usage

Template Usage

User Engagement

---

# REPORTING

Generate

Delivery Reports

Failure Reports

Retry Reports

Announcement Reports

Template Usage Reports

Channel Reports

Engagement Reports

Audit Reports

---

# EVENTS

Publish

NotificationCreated

NotificationQueued

NotificationSent

NotificationDelivered

NotificationRead

NotificationAcknowledged

NotificationFailed

NotificationRetried

AnnouncementPublished

Integrate with Prompt 020.

---

# TELEMETRY

Integrate Prompt 024.

Trace

Template Rendering

Queue Processing

Delivery

Retries

Acknowledgements

API Calls

---

# AUDIT

Audit

Notification Creation

Template Changes

Preference Changes

Subscriptions

Announcements

Broadcasts

Administrative Operations

---

# REST APIs

Implement

GET /notifications

GET /notifications/{id}

POST /notifications

DELETE /notifications/{id}

POST /notifications/send

POST /notifications/broadcast

GET /notifications/preferences

PUT /notifications/preferences

GET /notifications/templates

POST /notifications/templates

PUT /notifications/templates/{id}

GET /notifications/subscriptions

POST /notifications/subscriptions

GET /notifications/announcements

POST /notifications/announcements

GET /notifications/statistics

GET /notifications/reports

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secure webhook delivery

Template validation

Immutable audit history

---

# PERFORMANCE

Asynchronous Delivery

Distributed Workers

Message Queue Integration

Connection Pooling

Caching

Horizontal Scaling

High Availability

Automatic Failover

---

# TESTING

Unit Tests

Integration Tests

Template Tests

Delivery Tests

Retry Tests

Webhook Tests

Localization Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Notification Guide

Template Guide

Localization Guide

Webhook Guide

Preference Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Multi-channel Notification Delivery

✓ Template Management

✓ Localization

✓ User Preferences

✓ Subscription Management

✓ Retry Engine

✓ Delivery Tracking

✓ In-App Notification Center

✓ Announcements

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

External Marketing Platforms

CRM Messaging

Marketing Campaign Management

Customer Email Automation

Only implement the Enterprise Notification Center Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate notification routing engine.

Generate template rendering engine.

Generate delivery tracking.

Generate retry engine.

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

End Prompt 055.
