# ADR 003 — Open Read-Only API, No Authentication Required

**Date:** March 2026
**Status:** Accepted

## Context

We needed to decide whether the public API requires authentication (API keys).

## Options Considered

1. **Open API** — no key, anyone can call it
2. **API key required** — register to get a key
3. **No public API** — web app only

## Decision

Open read-only API. No registration. No API key. Rate-limited by IP via Cloudflare.

## Reasons

- The app's mission is "free and for the people" — API keys create friction that contradicts this
- A developer building a temple website in Vijayawada should be able to embed a Panchangam widget with a single fetch call
- This is read-only astronomical data — not sensitive, not write-capable
- Abuse risk is low and mitigated by Cloudflare rate limiting (free, automatic)
- Other open-source community tools (OpenStreetMap, etc.) follow this model successfully
- API keys add maintenance burden: key rotation, abuse tracking, support requests

## Consequences

- Anyone can use the API without registration
- Rate limiting is enforced at the IP level by Cloudflare — no code required
- If demand grows significantly, rate limits can be tightened in Cloudflare dashboard
- Optional API keys for higher rate limits can be introduced in v2 if needed
