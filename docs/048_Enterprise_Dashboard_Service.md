# AI Infrastructure Operating System (AI-IOS)

# Prompt 048

## Enterprise Dashboard Service

Reference Documents

Prompt 000
Prompt 001
...
Prompt 047

---

# ROLE

You are the Principal Enterprise Dashboard Architect.

Implement the Enterprise Dashboard Service.

Use every previously implemented platform framework.

Do NOT redesign the platform.

Implement a production-ready enterprise dashboard and visualization platform.

---

# OBJECTIVE

Build a centralized Dashboard Service responsible for real-time visualization of enterprise infrastructure, automation, monitoring, validation, alerts, workflows, AI insights, compliance, and operational health.

The Dashboard Service SHALL provide customizable, interactive, multi-tenant dashboards with real-time updates, drill-down navigation, topology visualization, and role-based access.

---

# SERVICE LOCATION

services/dashboard-service/

---

# DIRECTORY STRUCTURE

dashboard-service/

app/

api/

controllers/

services/

repositories/

models/

schemas/

dashboards/

widgets/

layouts/

themes/

filters/

topology/

charts/

maps/

realtime/

websocket/

sse/

favorites/

sharing/

templates/

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

dashboards

dashboard_layouts

dashboard_widgets

dashboard_widget_settings

dashboard_templates

dashboard_filters

dashboard_views

dashboard_shares

dashboard_favorites

dashboard_permissions

dashboard_themes

dashboard_statistics

dashboard_history

dashboard_audit

---

# DASHBOARD TYPES

Executive Dashboard

Operations Dashboard

Infrastructure Dashboard

Monitoring Dashboard

Validation Dashboard

Automation Dashboard

Workflow Dashboard

Alert Dashboard

Compliance Dashboard

Security Dashboard

Capacity Dashboard

Performance Dashboard

Inventory Dashboard

AI Insights Dashboard

Custom Dashboard

---

# WIDGET TYPES

Metric Card

Gauge

Line Chart

Bar Chart

Area Chart

Pie Chart

Donut Chart

Heatmap

Topology Graph

Status Matrix

Timeline

Alert Feed

Event Feed

Table

Tree View

Markdown Widget

AI Insight Widget

Custom Widget

---

# DASHBOARD BUILDER

Support

Drag and Drop

Resizable Widgets

Grid Layout

Responsive Layout

Saved Layouts

Versioning

Undo / Redo

Preview

Widget Library

Template Library

---

# FILTERING

Support

Organization

Project

Environment

Asset Group

Labels

Tags

Date Range

Severity

Status

Custom Filters

Saved Filters

---

# REAL-TIME UPDATES

Support

WebSockets

Server-Sent Events

Automatic Refresh

Incremental Updates

Live Streaming

Presence Awareness

Connection Recovery

---

# TOPOLOGY VISUALIZATION

Integrate Prompt 036.

Support

Neo4j Graph Visualization

Infrastructure Relationships

Dependency Graphs

Application Topology

Service Maps

Cluster Maps

Blast Radius View

Interactive Navigation

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

Reporting

AI Assistant

Compliance

Incident Management

Administration

---

# AI INSIGHTS

Integrate Prompt 046.

Display

Health Summary

Risk Analysis

Capacity Forecast

Operational Recommendations

Root Cause Summary

Anomaly Highlights

Natural Language Insights

---

# SHARING

Support

Private Dashboards

Organization Dashboards

Project Dashboards

Read-only Links

Role-based Sharing

Export Layout

Import Layout

---

# THEMES

Support

Light Theme

Dark Theme

Custom Themes

Branding

Corporate Logos

Color Palettes

Accessibility Options

---

# ANALYTICS

Collect

Dashboard Views

Widget Usage

Load Time

Most Viewed Dashboards

Most Used Widgets

Refresh Frequency

User Engagement

---

# EVENTS

Publish

DashboardCreated

DashboardUpdated

DashboardDeleted

WidgetAdded

WidgetRemoved

LayoutChanged

DashboardShared

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate Prompt 025.

Notify

Dashboard Shared

Layout Updated

Widget Failure

Real-time Connection Lost

Refresh Failure

---

# TELEMETRY

Integrate Prompt 024.

Trace

Dashboard Loading

Widget Rendering

Topology Rendering

Real-time Streaming

API Calls

Filter Execution

---

# AUDIT

Audit

Dashboard Creation

Dashboard Updates

Sharing

Permissions

Theme Changes

Widget Changes

Administrative Operations

---

# REST APIs

Implement

GET /dashboards

GET /dashboards/{id}

POST /dashboards

PUT /dashboards/{id}

DELETE /dashboards/{id}

GET /dashboards/templates

POST /dashboards/templates

GET /dashboards/widgets

POST /dashboards/widgets

GET /dashboards/layouts

POST /dashboards/layouts

POST /dashboards/share

GET /dashboards/statistics

---

# SECURITY

Integrate Prompt 017.

Integrate Prompt 032.

Enforce

Organization isolation

Project isolation

RBAC authorization

Secure dashboard sharing

Audit all dashboard operations

---

# PERFORMANCE

Widget Caching

Lazy Loading

Virtual Scrolling

Incremental Rendering

WebSocket Scaling

Horizontal Scaling

High Availability

---

# TESTING

Unit Tests

Integration Tests

Widget Tests

Layout Tests

Real-time Tests

Topology Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Dashboard Guide

Widget Guide

Topology Guide

Real-time Guide

Sharing Guide

REST API Reference

Developer Guide

Operations Guide

Architecture Notes

---

# ACCEPTANCE CRITERIA

✓ Dashboard Builder

✓ Widget Library

✓ Layout Engine

✓ Real-time Updates

✓ Topology Visualization

✓ AI Insight Widgets

✓ Dashboard Sharing

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

BI Platform

External Visualization Tools

Business-specific Dashboards

Only implement the Enterprise Dashboard Service.

---

# OUTPUT

Generate every required file.

Generate complete production-ready implementation.

Generate database migrations.

Generate OpenAPI documentation.

Generate dashboard builder.

Generate widget framework.

Generate topology visualization.

Generate real-time update engine.

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

End Prompt 048.
