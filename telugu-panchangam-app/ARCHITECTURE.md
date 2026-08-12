# Architecture — Telugu Panchangam App

> **Last updated:** March 2026
> **Status:** v1.0 — Initial architecture

---

## Table of Contents

1. [Overview](#overview)
2. [System Layers](#system-layers)
3. [Request Flow](#request-flow)
4. [Calculation Engine](#calculation-engine)
5. [Caching Strategy](#caching-strategy)
6. [API Design](#api-design)
7. [Frontend Architecture](#frontend-architecture)
8. [Data Flow Diagrams](#data-flow-diagrams)
9. [Performance Targets](#performance-targets)
10. [Security Model](#security-model)
11. [Scalability Considerations](#scalability-considerations)

---

## Overview

The Telugu Panchangam App is a **stateless, edge-first web application** built on Cloudflare's global network. All Panchangam calculations are performed by a pure TypeScript engine with no dependency on external Panchangam APIs. Results are cached at the edge for instant repeat lookups.

### Core Design Principles

**1. Edge-first.** Every calculation request is served from the Cloudflare edge node nearest to the user. A user in Melbourne gets their Panchangam from Sydney. A user in London gets it from London. Latency is minimal.

**2. Pure calculation engine.** No external Panchangam API is used. The engine computes everything from Sun and Moon positions using VSOP87 planetary theory. This gives coverage for any date — VSOP87 has no expiry date — with no API rate limits, no API costs, and no dependency that could break the app.

**3. Open by default.** The API requires no authentication. Any developer can call it. Rate limiting is enforced by Cloudflare at the infrastructure level, not in application code.

**4. Bilingual throughout.** Every data structure carries both Telugu (`te`) and English (`en`) fields. No component ever has to guess — it receives pre-labelled data.

---

## System Layers

```
┌─────────────────────────────────────────────────────────────┐
│  CLIENT (Browser / PWA)                                     │
│  Next.js 14 App Router — React Server Components           │
│  Tailwind CSS — Lotus Dawn theme                            │
│  Noto Sans Telugu + Playfair Display + Lora fonts           │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│  CLOUDFLARE EDGE                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Cloudflare Pages (static assets + SSR)             │   │
│  │  Cloudflare Workers (API routes via Next.js)        │   │
│  │  Cloudflare KV  (fast key-value cache)              │   │
│  │  Cloudflare D1  (SQLite — festival data + cache)    │   │
│  │  Cloudflare Analytics (no cookies, no scripts)      │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │ (only on cache miss)
┌──────────────────────────▼──────────────────────────────────┐
│  CALCULATION ENGINE (runs inside the Worker)                │
│  @ishubhamx/panchangam-js (VSOP87 astronomical core)        │
│  + Telugu layer (Samvatsaram, Masa, festivals, i18n)        │
│  + suncalc (sunrise/moonrise/phase)                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ (only for geocoding)
┌──────────────────────────▼──────────────────────────────────┐
│  EXTERNAL SERVICES                                          │
│  OpenCage Geocoding API — city name → lat/lng/timezone      │
│  (proxied — key never exposed to client)                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Daily Panchangam Request

```
User opens app (Melbourne, today)
         │
         ▼
Browser → Cloudflare Edge (Sydney node)
         │
         ▼
Check Cloudflare KV cache
  key: "panchangam:2026-03-23:-37.81400:144.96330:Australia/Melbourne"
         │
    ┌────┴────┐
  HIT        MISS
    │           │
    ▼           ▼
Return      Run engine:
cached      1. Get Julian Day for date
JSON        2. Calculate Sun longitude (VSOP87)
            3. Apply Lahiri Ayanamsa correction
            4. Calculate Moon longitude (VSOP87)
            5. Derive Tithi (Moon - Sun / 12°)
            6. Derive Nakshatra (Moon lon / 13.33°)
            7. Derive Yoga ((Sun + Moon) / 13.33°)
            8. Derive Karana (half Tithi)
            9. Get sunrise/sunset via SunCalc
            10. Calculate Rahukalam (weekday × sunrise)
            11. Calculate Gulika + Yamagandam
            12. Get moon phase + illumination
            13. Check festival rules for this date
            14. Map Samvatsaram + Masa + Paksha
            15. Translate all values to TE + EN
                │
                ▼
          Store result in KV (TTL: 30 days)
                │
                ▼
          Return DayPanchangam JSON
```

### Month View Request

```
User navigates to March 2026
         │
         ▼
Single API call: GET /api/panchangam/month?year=2026&month=3&lat=...&lng=...
         │
         ▼
Check D1 cache for all 31 days
         │
    Batch calculate any missing days (parallel Workers)
         │
         ▼
Return MonthData[] — 31 DayPanchangam objects
```

---

## Calculation Engine

The engine is the most critical component. It lives in `src/engine/` and is a set of pure TypeScript functions with no side effects.

### Dependency

```
@ishubhamx/panchangam-js
  └── Uses Swiss Ephemeris-compatible algorithms
  └── Verified against 200 days of Drik Panchang data
  └── Accuracy: 100% for dates tested
  └── Performance: ~5ms per calculation on standard hardware
  └── Licence: MIT
```

We build our Telugu-specific layer **on top of** this library:

```
Our Engine Layer (Telugu-specific)
  ├── Samvatsaram names (60-year cycle, Telugu + English)
  ├── Telugu Masa names (Amanta system)
  ├── Ritu (season) names
  ├── Ayana (sun direction) calculation
  ├── Festival rules (algorithmic + lookup)
  ├── All Telugu/English translations
  └── Rahukalam/Gulika/Yamagandam (weekday-based)

@ishubhamx/panchangam-js (astronomical core)
  ├── Sun longitude (VSOP87)
  ├── Moon longitude (VSOP87)
  ├── Tithi calculation
  ├── Nakshatra calculation
  ├── Yoga calculation
  ├── Karana calculation
  ├── Lahiri Ayanamsa
  └── Julian Day conversion
```

### Key Algorithms

See `ALGORITHM.md` for the full mathematical specification. Summary:

| Element | Formula | Notes |
|---|---|---|
| Tithi | `(Moon lon − Sun lon) / 12°` | 30 Tithis per month |
| Nakshatra | `Moon lon / 13°20′` | 27 Nakshatras × 800′ |
| Yoga | `(Sun lon + Moon lon) / 13°20′` | 27 Yogas |
| Karana | Half of each Tithi | 11 Karanas |
| Ayanamsa | Lahiri correction | ~24° currently |
| Samvatsaram | Jupiter's 60-year cycle | From fixed epoch |
| Rahukalam | Weekday × daylight slot | 8 equal slots, sunrise-anchored |

### Ayanamsa Policy

**Only Lahiri (Chitrapaksha) Ayanamsa is supported in v1.** This is the standard used by all Telugu Panchangam publishers including Venkatrama & Co. It is hardcoded — not a configurable parameter. Other ayanamsa systems (Raman, KP, True Chitra) are out of scope for v1.

---

## Caching Strategy

### Two-Layer Cache

```
Layer 1: Cloudflare KV (key-value)
  Purpose:   Single-day Panchangam lookups
  Key:       "panchangam:{date}:{lat_5dp}:{lng_5dp}:{tz}"
  TTL:       30 days (data doesn't change once calculated)
  Latency:   ~1ms (in-process at edge)
  Free tier: 100,000 reads/day, 1,000 writes/day, 1GB storage

Layer 2: Cloudflare D1 (SQLite)
  Purpose:   Month views, festival data, popular cities pre-cache
  Tables:    panchangam_cache, festivals, popular_cities
  Latency:   ~2ms (same edge network)
  Free tier: 5GB storage, 100,000 reads/day
```

### Cache Key Design

```typescript
// Single day
`panchangam:${date}:${lat.toFixed(5)}:${lng.toFixed(5)}:${tz}`
// e.g. "panchangam:2026-03-23:-37.81400:144.96330:Australia/Melbourne"

// Month (stored as single D1 row with JSONB)
`month:${year}:${month}:${lat.toFixed(3)}:${lng.toFixed(3)}:${tz}`

// Festival year
`festivals:${year}:te` or `festivals:${year}:en`
```

### Pre-computation Strategy

On first deploy, a one-time script pre-computes and caches:
- Current year ± 2 years for Melbourne (default city)
- All festival dates for current year ± 5 years
- Popular Telugu cities: Hyderabad, Vijayawada, Visakhapatnam, Tirupati, Warangal

This ensures the first user in each city gets cached results, not a calculation delay.

---

## API Design

All endpoints are at `/api/`. They are public — no authentication required. Cloudflare rate limiting: 100 requests/minute per IP.

### Endpoint Summary

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/panchangam` | GET | Single day Panchangam |
| `/api/panchangam/month` | GET | Full month (30/31 days) |
| `/api/festivals` | GET | Festivals for a year |
| `/api/geocode` | GET | City → lat/lng/timezone |
| `/api/muhurtam` | GET | Auspicious time windows |
| `/api/nakshatra` | GET | Janma Nakshatra from birth details |
| `/api/reminders` | GET/POST | Upcoming Amavasya/Ekadashi list + create reminder |
| `/api/reminders/unsubscribe` | GET | One-click email unsubscribe |

Full specification in `API.md`.

### Response Shape Consistency

Every successful response:
```typescript
{ data: T, source: 'cache' | 'engine', computedAt: string }
```

Every error:
```typescript
{ error: string, code: string, details?: string }
```

---

## Frontend Architecture

### Page Structure

```
app/
  page.tsx                    ← Today's Panchangam (default city)
  [year]/[month]/page.tsx     ← Month view
  [year]/[month]/[day]/page.tsx ← Day detail (full Panchanga)
  error.tsx                   ← Error boundary — catches runtime errors
  not-found.tsx               ← Custom 404 page
```

### Component Hierarchy

```
<RootLayout>
  ├── <Header>
  │   ├── <LogoMarkup>       ← Telugu + English
  │   ├── <CitySearch>       ← OpenCage-powered typeahead
  │   ├── <LanguageToggle>   ← te / en — stored in localStorage
  │   └── <TimeNav>          ← Date navigator (any date)
  │
  ├── <DayDetail>            ← Today view / Day detail view
  │   ├── <SamvatContextBar> ← Samvatsaram, Masa, Paksha, Ritu, Ayana
  │   ├── <PanchaAngaGrid>   ← 5 cards: Tithi, Nakshatra, Yoga, Karana, Vara
  │   ├── <CelestialTimings> ← Sunrise, Sunset, Moonrise, Moonset
  │   ├── <MoonPhase>        ← SVG animated moon + illumination %
  │   └── <InauspiciousPeriods> ← Rahukalam, Gulika, Yamagandam
  │
  ├── <CalendarGrid>          ← Month view
  │   ├── <CalendarHeader>
  │   ├── <WeekdayRow>
  │   └── <DayCell[]>         ← Tithi, moon phase icon, festival badge
  │
  ├── <CityWelcome>           ← Full-screen first-visit city selector
  │
  ├── <FestivalTracker>       ← Year view of all festivals
  │
  ├── <MuhurtamFinder>        ← Date range → auspicious windows
  │
  ├── <NakshatraFinder>       ← Birth details → Janma Nakshatra
  │
  ├── <Tooltip>               ← Hover/tap tooltips on Panchanga elements
  │
  ├── <LearnModal>            ← "What is Panchangam?" bilingual explainer
  │
  ├── <ErrorState>            ← Reusable error display with retry
  │
  └── <LoadingState>          ← Reusable loading skeleton
```

### Error Handling

The app uses a layered error handling strategy:

```
error.tsx (root error boundary)
  └── Catches unhandled runtime errors → renders ErrorState with retry button

not-found.tsx (404 handler)
  └── Custom 404 page with navigation back to home

<ErrorState> (reusable component)
  └── Used within pages/components for API errors, graceful fallback

<LoadingState> (reusable component)
  └── Consistent loading skeleton across all async data fetches
```

First-time visitors without a saved city see `<CityWelcome>` — a full-screen guided city selector — instead of silently defaulting.

### Language Handling

The language context is provided at root layout level:

```typescript
// src/lib/i18n.ts exports all strings in both languages
// Components receive lang prop: 'te' | 'en'
// Telugu text always uses className="font-noto-telugu"
// User preference stored in localStorage key: 'panchangam-lang'
```

### PWA Configuration

```
Offline cache strategy:
  Static assets:    Cache-first (fonts, images, JS bundles)
  Today's data:     Stale-while-revalidate (24hr TTL)
  Current month:    Cache-first with background refresh
  Historical data:  Network-only (no offline)

Install prompt: Shown after 3 visits to the home page
```

---

## Data Flow Diagrams

### City Search Flow

```
User types "Melbourne"
       │
       ▼
Debounce 300ms
       │
       ▼
GET /api/geocode?q=Melbourne
       │
       ▼
Check KV cache: "geocode:melbourne"
  HIT → return cached result
  MISS → call OpenCage API (key stays on server)
       │
       ▼
Store in KV (TTL: 365 days — city locations don't change)
       │
       ▼
Return { name, lat, lng, timezone }
       │
       ▼
Update URL params + localStorage + trigger Panchangam fetch
```

### Language Toggle Flow

```
User clicks TE/EN toggle
       │
       ▼
Update localStorage: 'panchangam-lang' = 'te' | 'en'
       │
       ▼
React context updates
       │
       ▼
All components re-render with new lang prop
       │
No API call needed — all data already has both TE + EN fields
```

---

## Performance Targets

| Metric | Target | Strategy |
|---|---|---|
| First Contentful Paint | < 1.5s | SSR, font preload |
| API response (cached) | < 10ms | Cloudflare KV |
| API response (uncached) | < 200ms | Engine ~5ms + edge overhead |
| Month view load | < 300ms | Batch D1 query |
| Telugu font load | < 200ms | Subset to required codepoints |
| Lighthouse score | > 90 | Core Web Vitals optimisation |
| Bundle size (initial) | < 150kb gzipped | Code splitting, lazy imports |

### Cloudflare Workers CPU Limit

Free tier Workers have a 10ms CPU time limit per request. The engine is expected to complete in ~5ms. We benchmark this in Phase 1:

```bash
# Phase 1 benchmark script
npm run benchmark:engine

# Expected output:
# Single calculation:  4.8ms avg (3.1ms min, 8.2ms max)
# Month calculation:   142ms total (4.7ms × 30, parallel)
# Status: WITHIN LIMIT ✓
```

If any calculation exceeds 10ms, the fallback is to serve from D1 pre-computed cache. The engine becomes a background job, not a real-time responder.

---

## Testing

The project has two independent test layers, both gated in CI.

### Unit + regression (Jest)

- **Runner:** Jest with `ts-jest`
- **Roots:** `src/` and `validation/` only (configured in `jest.config.js`)
- **Suites:**
  - Engine module tests co-located with each module (`src/engine/*.test.ts`)
  - Venkatrama regression assertions in `validation/regression.test.ts`
- **Run:**
  ```bash
  npm test                # all tests
  npm run test:engine     # engine modules only
  npm run test:validation # Venkatrama ground-truth assertions
  ```
- **Current count:** 107 tests across 12 suites. Every PR must keep this
  green — Venkatrama assertions are the project's accuracy guarantee.

### End-to-end (Playwright)

- **Runner:** `@playwright/test`, chromium-only
- **Config:** `playwright.config.ts` defines five viewports and a single
  shared `mobileChromium` base built from `devices['Desktop Chrome']` plus
  `isMobile`/`hasTouch`. We deliberately avoid `devices['iPhone …']` and
  `devices['iPad …']` because those switch the engine to webkit and would
  require an extra `playwright install webkit` step in CI.
- **Tests:** `e2e/mobile.spec.ts` covers:
  - DayDetail share button does not overlap the date heading
  - Pancha Anga renders as 2 columns below 640 px
  - Telugu text is visible and not zero-width
  - Nav links are scrollable so the last (పితృ స్మరణ) is reachable
  - Primary touch targets (width > 60 px) are ≥ 40 px tall
  - CityWelcome first-visit prompt fires when localStorage is empty
  - Screenshot capture for visual reference
- **Viewports:** 375, 390, 430, 768, 1280 px
- **Run:**
  ```bash
  npx playwright install chromium --with-deps  # one-time setup
  npm run test:e2e:mobile                       # 375 + 390
  npm run test:e2e                              # all five viewports
  npm run test:e2e:report                       # open last HTML report
  ```
- **CI:** the `e2e` job in `.github/workflows/ci.yml` runs after the unit
  test job. On failure it uploads `e2e/screenshots/` and `playwright-report/`
  as artifacts (7-day retention).
- **Dev-server hook:** Playwright's `webServer` runs `npm run dev`. In CI
  the `setupDevPlatform` import in `next.config.mjs` is skipped (it would
  otherwise try to load `wrangler`, which isn't in `node_modules`).

---

## Security Model

### What is sensitive

| Data | Classification | Treatment |
|---|---|---|
| OpenCage API key | Secret | Server-only env var, never sent to client |
| Cloudflare API token | Secret | CI/CD only, never in code |
| User city preference | Non-sensitive | localStorage, never sent to server |
| User language preference | Non-sensitive | localStorage |
| Janma Nakshatra inputs | Personal | Computed client-side where possible, not stored |

### API Security

- **No authentication** — intentional, by design (see `decisions/003-open-api-no-keys.md`)
- **Rate limiting** — Cloudflare WAF rule: 100 req/min per IP
- **Input validation** — all params validated with zod before processing
- **No user data stored** — city + date are ephemeral query params
- **HTTPS only** — enforced by Cloudflare, no HTTP fallback

### Dependency Security

- Dependabot enabled — weekly dependency update PRs
- `npm audit` runs in CI — blocks merge if high/critical vulnerabilities
- Only MIT/Apache licensed dependencies — checked in CI

---

## Scalability Considerations

### Current Architecture Limits

| Component | Free Tier Limit | When to upgrade |
|---|---|---|
| Cloudflare Workers | 100,000 req/day | > 70,000 daily users |
| Cloudflare KV reads | 100,000/day | > 70,000 daily users |
| Cloudflare D1 reads | 100,000/day | > 70,000 daily users |
| OpenCage geocoding | 2,500/day | Cached aggressively — unlikely to hit |

### Growth Path

```
v1 (0–70k DAU):    Current architecture — free, zero cost
v2 (70k–500k DAU): Cloudflare Workers Paid ($5/mo) — 10M req/day
v3 (500k+ DAU):    Consider pre-computation job for all city/year combos
```

The app is **stateless by design**. Scaling requires no architectural changes — just upgrading the Cloudflare plan. No database migrations, no server provisioning.

---

## Architecture Decision Records

All significant decisions are documented in the `decisions/` folder:

- `001-calculation-engine.md` — Why we built our own engine instead of using an API
- `002-cloudflare-d1-vs-supabase.md` — Why Cloudflare D1 over Supabase
- `003-open-api-no-keys.md` — Why the API requires no authentication
- `004-lotus-dawn-theme.md` — Design theme selection rationale

---

*This document is maintained by the project maintainer. If you find it out of date, please open an issue.*
