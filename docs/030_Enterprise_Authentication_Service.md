# AI Infrastructure Operating System (AI-IOS)

# Prompt 030

## Enterprise Authentication Service

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

---

# ROLE

You are the Principal Identity and Access Management Architect.

Implement the Enterprise Authentication Service.

Do NOT redesign the platform.

Implement the Authentication Service using all previously implemented frameworks.

---

# OBJECTIVE

Build a production-ready authentication service responsible for identity verification and session management across AI-IOS.

The service shall support

- Username / Password Authentication
- JWT Authentication
- Refresh Tokens
- OAuth2
- OpenID Connect (OIDC)
- SAML 2.0
- LDAP
- Active Directory
- Multi-Factor Authentication
- API Keys
- Service Accounts
- Session Management
- Device Management
- Token Revocation
- Password Reset
- Email Verification
- Account Lockout
- Audit Logging

---

# SERVICE LOCATION

services/authentication-service/

---

# DIRECTORY STRUCTURE

authentication-service/

app/

api/

controllers/

services/

models/

repositories/

schemas/

security/

authentication/

sessions/

devices/

tokens/

oauth/

oidc/

saml/

ldap/

activedirectory/

mfa/

apikeys/

service_accounts/

passwords/

verification/

audit/

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

users

user_credentials

sessions

refresh_tokens

access_tokens

api_keys

service_accounts

mfa_devices

password_history

password_reset_tokens

email_verification_tokens

login_history

trusted_devices

failed_logins

authentication_audit

Do NOT create RBAC tables here.

RBAC belongs to Prompt 032.

---

# AUTHENTICATION METHODS

Support

Username + Password

JWT

Refresh Token

API Key

OAuth2 Authorization Code

OAuth2 Client Credentials

OIDC

LDAP

Active Directory

SAML 2.0

Service Accounts

---

# JWT

Implement

Access Token

Refresh Token

Token Rotation

Token Revocation

Token Blacklist

Token Validation

Key Rotation

RS256 signing

Expiration Policies

---

# LOGIN

Support

Password Login

Remember Me

Trusted Device

Device Registration

Location Awareness

Risk Detection (framework hooks)

---

# SESSION MANAGEMENT

Support

Create Session

Refresh Session

Terminate Session

Terminate All Sessions

Idle Timeout

Absolute Timeout

Concurrent Session Limit

Session Audit

---

# PASSWORD POLICY

Enforce

Minimum Length

Complexity

Password History

Password Expiration

Reuse Prevention

Dictionary Validation

Argon2 Hashing

Breach Password Hook

---

# ACCOUNT SECURITY

Support

Failed Login Tracking

Progressive Delay

Temporary Lockout

Permanent Lockout

CAPTCHA Hook

Suspicious Activity Detection

---

# MULTI-FACTOR AUTHENTICATION

Support

TOTP

Recovery Codes

Trusted Devices

Backup Codes

Future

WebAuthn

FIDO2

SMS OTP

Email OTP

---

# DEVICE MANAGEMENT

Track

Device ID

Browser

Operating System

IP Address

Location (if available)

Last Login

Trusted Status

Device Revocation

---

# PASSWORD RESET

Generate Secure Reset Tokens

Expiration

Single Use

Audit

Email Integration

---

# EMAIL VERIFICATION

Generate Verification Token

Expiration

Resend

Verification Status

Audit

---

# API KEYS

Support

Personal API Keys

Organization API Keys

Expiration

Rotation

Scopes

Revocation

Usage Tracking

---

# SERVICE ACCOUNTS

Support

Machine Accounts

Token Authentication

Scoped Permissions

Rotation

Audit

---

# EVENTS

Publish

UserLoggedIn

UserLoggedOut

PasswordChanged

PasswordResetRequested

PasswordResetCompleted

EmailVerified

SessionCreated

SessionExpired

ApiKeyCreated

ApiKeyRevoked

MfaEnabled

MfaDisabled

AccountLocked

AccountUnlocked

Integrate with Prompt 020.

---

# NOTIFICATIONS

Integrate with Prompt 025

Send

Welcome Email

Verification Email

Password Reset

MFA Enabled

Login Alert

Suspicious Login

Account Locked

Password Changed

---

# TELEMETRY

Integrate with Prompt 024.

Trace

Login

Logout

Session Creation

Token Validation

Password Reset

MFA

LDAP Authentication

OAuth Login

---

# AUDIT

Audit

Every Login

Every Logout

Failed Login

Password Change

Session Revocation

Token Creation

Token Revocation

MFA Changes

API Key Usage

---

# REST APIs

Implement

POST /auth/login

POST /auth/logout

POST /auth/refresh

POST /auth/register

POST /auth/forgot-password

POST /auth/reset-password

POST /auth/verify-email

POST /auth/resend-verification

POST /auth/mfa/enable

POST /auth/mfa/disable

POST /auth/mfa/verify

GET /auth/profile

GET /auth/sessions

DELETE /auth/sessions/{id}

DELETE /auth/sessions

GET /auth/devices

DELETE /auth/devices/{id}

POST /auth/apikeys

GET /auth/apikeys

DELETE /auth/apikeys/{id}

POST /auth/oauth/login

POST /auth/saml/login

POST /auth/ldap/login

---

# SECURITY

Integrate Prompt 017.

RBAC hooks

Tenant validation

Rate limiting

CSRF protection

Security headers

Secret management

---

# PERFORMANCE

Async APIs

Connection pooling

Caching

Queue integration

Horizontal scalability

Stateless authentication

---

# TESTING

Unit Tests

Integration Tests

Security Tests

JWT Tests

OAuth Tests

LDAP Tests

MFA Tests

API Tests

Performance Tests

Coverage >=95%

---

# DOCUMENTATION

README

Authentication Guide

OAuth Guide

OIDC Guide

LDAP Guide

SAML Guide

MFA Guide

Developer Guide

API Reference

---

# ACCEPTANCE CRITERIA

✓ Authentication Service

✓ JWT

✓ Refresh Tokens

✓ Sessions

✓ OAuth2

✓ OIDC

✓ LDAP

✓ Active Directory

✓ MFA

✓ API Keys

✓ Service Accounts

✓ Password Reset

✓ Email Verification

✓ REST APIs

✓ Events

✓ Notifications

✓ Telemetry

✓ Audit

✓ Tests Passing

✓ Documentation Complete

---

# DO NOT IMPLEMENT

RBAC

Organizations

Projects

Inventory

Automation

Workflow Engine

Connector Logic

Only the Enterprise Authentication Service.

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

End Prompt 030.
