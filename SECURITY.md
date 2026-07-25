# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AI-IOS, please report it privately
rather than opening a public issue. Email the security team through official
company channels with:

- A description of the vulnerability and its potential impact
- Steps to reproduce, including affected service(s) and version(s)
- Any proof-of-concept code, if available

You should expect an initial acknowledgement within 3 business days. We ask
that you give us a reasonable period to investigate and remediate before any
public disclosure.

## Supported Versions

While AI-IOS is under active initial development (pre-1.0), only the `main`
branch receives security fixes.

## Security Principles

AI-IOS follows Zero Trust and Least Privilege by design. See
[`docs/017_Enterprise_Security_Framework.md.txt`](docs/017_Enterprise_Security_Framework.md.txt)
for the platform's authentication, authorization, secrets, and encryption
architecture. Every dependency change is scanned with `pip-audit` (Python) and
`pnpm audit` (Node); every commit is scanned for secrets via pre-commit hooks.
