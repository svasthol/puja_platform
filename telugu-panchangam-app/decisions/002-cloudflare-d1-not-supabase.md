# ADR 002 — Cloudflare D1 + KV Instead of Supabase

**Date:** March 2026
**Status:** Accepted

## Context

We needed a database for caching computed Panchangam results.

## Options Considered

1. **Supabase** (PostgreSQL, separate service)
2. **Cloudflare D1 + KV** (SQLite + key-value, built into Cloudflare)
3. **No cache** (recalculate every request)

## Decision

Cloudflare D1 for persistent cache, Cloudflare KV for hot path (recent dates).

## Reasons

- Already deploying on Cloudflare — D1 and KV are co-located at the same edge node
- D1 cache queries respond in ~2ms vs ~50-100ms for a separate Supabase server
- Simpler architecture — one fewer external service to manage
- Simpler for contributors — no Supabase account required to run locally
- Cloudflare free tier is generous: 5GB D1, 1GB KV, 100K D1 reads/day
- No egress fees on Cloudflare's internal network

## Consequences

- Cache is tied to Cloudflare infrastructure
- Migration to another platform requires replacing D1/KV with an equivalent
- The engine itself remains platform-agnostic — only the cache layer changes
