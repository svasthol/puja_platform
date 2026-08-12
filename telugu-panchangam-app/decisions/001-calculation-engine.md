# ADR 001 — Pure JS Calculation Engine, No External Panchangam API

**Date:** March 2026
**Status:** Accepted

## Context

We needed a Panchangam calculation approach for any date — past, present, or future — for any city worldwide. The key insight: this is pure mathematics. Planetary positions follow deterministic equations. There is no inherent limit.

## Options Considered

1. **External Panchangam API** (Drik Panchang, ProKerala etc.)
2. **Pure JS calculation engine** based on VSOP87 planetary theory
3. **Hybrid** — API for recent years, engine for historical/future dates

## Decision

Pure JS calculation engine using `@ishubhamx/panchangam-js` as the astronomical foundation, with a Telugu-specific layer on top.

## Reasons

- External APIs cover only a narrow band of recent years — they cannot serve genealogical research, historical study, or far-future planning
- API rate limits and availability would break the app for users without our control
- API costs would eventually end the free promise
- Open source requires open, verifiable calculations — not a black-box API
- **VSOP87 is pure mathematics with no date limit.** The sky has no expiry date, and neither does this app. Planetary orbits are calculable for any date in human history or the future
- The Julian Day Number system counts continuously from 4713 BCE with no upper bound
- `@ishubhamx/panchangam-js` is MIT-licensed, verified against 200 days of Drik Panchang with 100% accuracy
- Benchmarks: ~5ms per calculation — within Cloudflare Workers free tier limit

## Consequences

- **Any date — any century — is supported** without any external dependency
- Engine is entirely auditable: developers and traditional scholars can read and verify every formula
- Must validate carefully against Venkatrama calendar for modern dates
- Pre-1900 dates carry a soft timezone caveat (IANA timezone history is sparse before ~1900)
- Pre-1582 dates use the proleptic Gregorian calendar, which is standard astronomical practice
- Ancient historical dates (e.g. a scholar researching when Ugadi fell in 500 CE) are fully supported

## The Principle

> The sky has no expiry date. A tool that honours the tradition should not have one either.
