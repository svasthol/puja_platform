# Security Policy

Thank you for taking the time to report a security issue responsibly.

## Supported Versions

Only the latest tagged release receives security fixes. The live deployment
at [telugupanchangam.app](https://telugupanchangam.app) always tracks `main`,
so a fix merged to `main` ships within minutes.

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security problems.**

Instead, email the details to:

> **accuracy@telugupanchangam.app**

Include as much of the following as you can:

- A description of the vulnerability
- Steps to reproduce it
- The affected URL or endpoint
- Your assessment of the impact
- (Optional) A suggested fix

You will receive an acknowledgement within **72 hours**. We will work with
you on a coordinated disclosure timeline before any public discussion.

## Scope

In scope:

- The live application at https://telugupanchangam.app
- The public API at https://telugupanchangam.app/api/*
- The source code in this repository (engine, API routes, frontend)
- Any leaked secrets in the git history (please report — we audit, but
  fresh eyes catch what tooling misses)

Out of scope:

- Denial-of-service attacks against the live deployment
- Issues that require physical access to a user's device
- Social engineering of contributors or maintainers
- Vulnerabilities in third-party dependencies that have already been
  disclosed upstream and have a fix available — open a regular PR instead

## What we consider sensitive

The app stores **no PII** beyond the bare minimum needed for reminder
emails (name, email address, city). Reminders are stored in Cloudflare D1.
No authentication tokens, no passwords, no payment data.

If you find an issue that exposes any of the above to a third party, that
is a serious bug and we treat it as priority zero.

## Acknowledgement

Reporters of valid security issues will be credited in the release notes
of the fix, unless they prefer to remain anonymous.

Thank you for helping keep the Telugu community safe online.

— Suhas Atluri
