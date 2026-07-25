# AI Infrastructure Operating System (AI-IOS)

# Prompt 047

## Enterprise Reporting Service

Reference Documents

Prompt 000
Prompt 001
Prompt 002
...
Prompt 046

---

# ROLE

You are the Principal Enterprise Reporting Architect.

Implement the Enterprise Reporting Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise reporting platform.

---

# OBJECTIVE

Build a centralized Reporting Service responsible for generating, scheduling, exporting, archiving, distributing, and auditing enterprise reports.

The Reporting Service SHALL aggregate data from every platform service and provide operational, analytical, executive, compliance, and AI-generated reports.

This service SHALL become the single reporting engine across AI-IOS.

---

# SERVICE LOCATION

services/reporting-service/

---

# DIRECTORY STRUCTURE

reporting-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

reports/

templates/

designer/

scheduler/

renderer/

export/

archive/

distribution/

email/

pdf/

excel/

csv/

json/

analytics/

filters/

parameters/

ai/

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

report_templates

report_categories

report_jobs

report_schedules

report_parameters

report_executions

report_exports

report_archives

report_distribution

report_recipients

report_statistics

report_history

report_favorites

report_audit

---

# REPORT CATEGORIES

Infrastructure

Inventory

Discovery

Configuration

Automation

Workflow

Validation

Monitoring

Alerting

Compliance

Security

Incident

Capacity

Availability

Performance

Executive

Operational

Financial

Custom

---

# REPORT TYPES

Tabular

Summary

Executive

Trend

Historical

Comparison

Compliance

Analytical

Dashboard Export

AI Summary

Custom

---

# REPORT DESIGNER

Support

Visual Templates

Custom Templates

Reusable Sections

Charts

Tables

Filters

Parameters

Widgets

Branding

Logos

Themes

Preview

Versioning

---

# REPORT TEMPLATES

Support

Executive Summary

Infrastructure Health

Validation Report

Monitoring Report

Automation Report

Compliance Report

Security Report

Inventory Report

Capacity Report

Availability Report

Incident Report

Operational Report

Custom Templates

---

# DATA SOURCES

Inventory

Discovery

Configuration Management

Automation

Workflow Runtime

Validation

Monitoring

Alerting

AI Assistant

Compliance

Incident Management

Administration

Custom APIs

---

# FILTERING

Support

Organization

Project

Environment

Tags

Labels

Asset Groups

Date Range

Custom Filters

Saved Filters

---

# EXPORT FORMATS

Support

PDF

Excel (XLSX)

CSV

JSON

Markdown

HTML

XML

---

# PDF FEATURES

Support

Headers

Footers

Page Numbers

Table of Contents

Charts

Images

Company Branding

Digital Signature

Password Protection

---

# SCHEDULING

Support

One-Time

Hourly

Daily

Weekly

Monthly

Cron

Time Zones

Retry

Failure Notifications

---

# DISTRIBUTION

Support

Download

Email

Webhook

Shared Links

API

Object Storage

Secure Expiration Links

---

# AI REPORTING

Integrate Prompt 046.

Support

Executive Summary

Natural Language Summary

Trend Explanation

Root Cause Summary

Recommendations

Risk Analysis

---

# ARCHIVE

Support

Version History

Retention Policies

Immutable Archive

Search

Restore

Download

---

# ANALYTICS

Collect

Generated Reports

Execution Time

Popular Reports

Export Types

Template Usage

Schedule Usage

Download Count

Distribution Statistics

---

# EVENTS

Publish

ReportCreated

ReportGenerated

ReportFailed

ReportScheduled

ReportDelivered

ReportDownloaded

ReportArchived

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Report Ready

Report Failed

Scheduled Report Complete

Distribution Failure

Archive Completed

---

# TELEMETRY

Integrate Prompt 024.

Trace

Rendering

Export

Distribution

Scheduling

Archive

Template Rendering

---

# AUDIT

Audit

Template Changes

Report Generation

Exports

Downloads

Distribution

Schedule Changes

Administrative Operations

---

# REST APIs

Implement

GET /reports

GET /reports/{id}

POST /reports

PUT /reports/{id}

DELETE /reports/{id}

POST /reports/generate

POST /reports/schedule

GET /reports/templates

POST /reports/templates

GET /reports/history

GET /reports/statistics

GET /reports/archive

POST /reports/export

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Integrate Prompt 035.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secure report access

Protected exports

Audit every report action

---

# PERFORMANCE

Async Rendering

Parallel Report Generation

Queue Integration

Template Cache

Large Dataset Streaming

Horizontal Scaling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Template Tests

Export Tests

Scheduler Tests

Distribution Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Reporting Guide

Template Guide

Scheduler Guide

Export Guide

Distribution Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Report Designer

✓ Report Templates

✓ Scheduling

✓ Export Engine

✓ Distribution

✓ Archive

✓ AI Summaries

✓ Analytics

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

Dashboard UI

Business-specific reports

BI integrations outside platform scope

Only implement the Enterprise Reporting Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate report designer.

Generate rendering engine.

Generate export engine.

Generate scheduler.

Generate archive management.

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

End Prompt 047.
