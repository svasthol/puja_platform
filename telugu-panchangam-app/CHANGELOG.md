# Changelog — Telugu Panchangam App

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.2.0] — 2026-04-07: Custom domain + verified email

### Changed
- **App is now live at https://telugupanchangam.app** (was
  https://telugu-panchangam-app.pages.dev). The Cloudflare Pages
  preview hostname still works as a fallback.
- **Reminder emails sent from `reminders@telugupanchangam.app`**.
  Domain is verified in Resend with DKIM, SPF and DMARC all passing
  — emails should now land in inbox reliably instead of spam.
- All internal URL references updated: `src/lib/constants.ts` (new),
  `src/app/layout.tsx` `metadataBase` and `openGraph.url`,
  `src/app/[year]/[month]/{,[day]/}opengraph-image.tsx`,
  `src/app/[year]/[month]/[day]/page.tsx` `generateMetadata`,
  `src/components/PrintableCalendar.tsx` print footer,
  `src/components/TeluguBirthday.tsx` share message,
  `public/og-image.svg`, `README.md`, `API.md`, `.env.example`.
- `public/og-image.png` regenerated from the updated SVG with sharp
  (now a real PNG with the new domain baked into the social card).

### Added
- `src/lib/constants.ts` — single source of truth for `APP_URL`,
  `APP_HOST`, `REPORT_EMAIL`, `REMINDER_FROM_EMAIL` and `GITHUB_REPO`
  so a future domain change is one edit instead of grep-and-replace.

### Infrastructure
- Domain: telugupanchangam.app (registrar: Porkbun)
- DNS: Cloudflare Pages custom domain
- Email: Resend with verified domain (DKIM ✅ SPF ✅ DMARC ✅)
- Production secrets — all four now set on Cloudflare Pages:
  `OPENCAGE_API_KEY`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`,
  `CRON_SECRET` (`openssl rand -hex 32`, also stored in local
  `.env.local` for the cron worker auth check)
- End-to-end reminder pipeline verified live: `POST /api/reminders`
  on telugupanchangam.app returns `200` with a real reminder id and
  unsubscribe token, and the bilingual confirmation email is
  delivered to inbox via `reminders@telugupanchangam.app`

---

## [Unreleased]

### Added
- **New `/about` route — interactive engine explainer.** Five sections
  walking visitors through how the Panchangam is actually computed:
  hero with a pure-CSS solar system animation, six-step engine player
  with Next/Back controls and per-step formulas, click-to-expand
  accordion for the five Panchanga elements (Tithi / Nakshatra / Yoga
  / Karana / Vara) now with full bilingual `what / how / example`
  content from the new `ABOUT_ANGAS` namespace, a live calculator that
  hits `/api/panchangam` for the user's saved city to prove the math
  is real, and a six-card "Why this is different" grid. New
  `src/app/about/page.tsx` (server, generateMetadata for SEO/OG) +
  `src/components/AboutPage.tsx` (~430 lines client) (commit `31308e6`).
- **`/about` accordion fully bilingual.** The accordion's expanded
  paragraphs were the only English-only surface left on the page.
  New `ABOUT_ANGAS` export in `i18n.ts` carries `what / how / example`
  for each of the five elements in both Telugu and English (30 new
  strings). Examples render in `font-mono` so the worked numerical
  content (`Moon at 85°, Sun at 19° → tithi 6 (Shashthi)`,
  `JDN 2461136 mod 7 = 2 → Tuesday`) reads cleanly. The translations
  live in `i18n.ts` so future translators can find them without
  grepping the component (commit `da05d2f`).
- **`public/sitemap.xml`** — six URLs (`/`, `/about`, `/festivals`,
  `/muhurtam`, `/nakshatra`, `/reminders`) with appropriate priorities
  and changefreqs (commit `31308e6`).
- **`public/robots.txt`** — `Allow: /`, blocks `/api/cron/` from
  crawlers, links the sitemap (commit `31308e6`).
- **Three new integration points** for `/about`: italic "How it works?"
  link in the AppHeader nav row, "See how it works →" accent link in
  the CityWelcome modal so first-time visitors have a path before
  picking a city, and `/` keyboard shortcut. The KeyboardShortcutsHelp
  modal now lists `/` → "How it works" so the shortcut is discoverable
  (commit `31308e6`).
- **`POST /api/cron/send-reminders`** — daily reminder cron worker.
  Reads every active row from D1, computes today's panchangam (or
  today + `remind_days_before`) at the user's city in their local
  timezone, and sends a bilingual email via Resend if the day matches
  the user's chosen tithi types (Amavasya / Ekadashi / Purnima) or
  the stored anniversary tithi triple. Idempotent within a calendar
  day via the new `last_sent_date` column. Authenticated by
  `Authorization: Bearer $CRON_SECRET`.
- **`src/engine/reminderMatcher.ts`** — pure matching logic
  (`matchReminder`, `addDaysISO`, `todayInTimezone`) extracted so the
  cron worker is fully unit-testable without D1 / Resend / edge
  runtime. 16 new tests cover Amavasya / Ekadashi / Purnima opt-ins,
  multi-opt-in priority, tithi-anniversary exact match, Adhika masa
  rejection, paksha/null guards, day arithmetic across month and
  year boundaries, and timezone-aware "today" computation.
- **`migrations/003_reminder_sent_tracking.sql`** — adds
  `last_sent_date` and `last_sent_kind` columns to the reminders
  table plus an index, applied to production D1.
- **`.github/workflows/daily-reminders.yml`** — GitHub Actions cron
  schedule (00:30 UTC daily, also `workflow_dispatch` for manual
  runs) that POSTs to the cron route with the Bearer token. Used
  instead of Cloudflare Cron Triggers because Pages does not natively
  support them.

### Fixed
- **The పితృ స్మరణ pipeline is now complete end-to-end.** Before
  this commit, users could sign up via `POST /api/reminders` and
  the row was stored in D1, but **no scheduled job ever read those
  rows and sent the reminder on the right Tithi**. The cron worker
  now closes that loop. 127 unit tests passing (was 109).
- **`POST /api/reminders` was silently dropping 8 columns** on every
  insert. The INSERT statement bound 15 values but the table has
  22+ columns. `tithi_masa_number`, `tithi_paksha`, `tithi_number`,
  `tithi_description`, `origin_lat`, `origin_lng`, `origin_tz` and
  `original_date` were never persisted for ANY anniversary signup
  since the feature shipped. The route schema accepted them; the
  INSERT just didn't bind them. Fixed by extending the bind list
  to all 22 columns (commit `ca6aa42`).
- **`TithiAnniversary.sendReminder()` never sent the identifying
  triple.** The component had `tithiIdentity.{masaNumber, paksha,
  tithiNumber}` in state but the POST body only included
  `tithi_description` (free text). Even after fixing the INSERT,
  the route would still receive nulls. Now the POST passes the
  triple from `tithiIdentity`. (commit `ca6aa42`)
- **`reminderMatcher` used the wrong tithi number convention.**
  The matcher I shipped earlier in this Unreleased block declared
  `StoredReminder.tithi_number` as the absolute 1-30 number, but
  `TithiIdentity`, the API zod schema (`max(15)`) and the entire
  upstream codebase use paksha-relative 1-15. Krishna paksha rows
  would have stored e.g. `10` and the matcher would have looked
  for absolute `10` instead of absolute `25`. Now the matcher
  derives the absolute target from paksha + relative number:
  `absolute = paksha === "shukla" ? n : n + 15`. Two new
  regression tests cover the positive and negative Krishna case
  (commit `ca6aa42`).

### Added
- **`TeluguBirthday` now has a "🎂 Set Birthday Reminder" card.**
  Users could previously find their Telugu birthday for the next
  5 years but had no way to subscribe to a yearly reminder. The
  cron worker fully supported the `kind=tithi_anniversary` path —
  the UI was simply missing. Inline email + days-before + confirm
  flow matching the TithiAnniversary pattern. POSTs the same
  identifying triple so the cron can find the day each year
  (commit `ca6aa42`).


These fixes ship between v1.1.1 and the next tagged release. They are
follow-ups to the mobile hotfix discovered while iterating on CI.

### Added
- **జన్మ తిథి Telugu Birthday Finder** — third tab on `/reminders`
  alongside Monthly Reminders and Tithi Anniversary. Reuses the
  anniversary engine but with birthday framing: "Date of birth",
  "City of birth", "Find My Birthday", "Your Telugu birthday each year".
  Birth tithi card at the top of results, "Share my Telugu birthday"
  button copies a formatted message ready for WhatsApp/SMS. Bilingual
  `TELUGU_BIRTHDAY` namespace in `i18n.ts` (commit `3d2ffb1`).
- `CitySearchInline` reusable component — minimal inline geocode
  typeahead with Cancel button, used to override the saved city in
  the anniversary and birthday forms (commit `f721255`).
- Calendar grid: mobile festival display now uses **dots only** (up to
  3 dots + `+` overflow marker) instead of truncating festival names
  to "Han…". Tablet/desktop unchanged. Faint accent tint on festival
  days. "Tap any day to see festivals" hint above the weekday header
  on mobile (commit `1d09847`).

### Fixed
- **`/api/reminders/anniversary` was timing out** on Cloudflare's
  10 ms edge CPU budget for 25-year requests. Three changes:
  1. Replaced `estimateMasaStart` with `estimateMasaMidpoint`, an
     empirical Gregorian midpoint table for each Telugu masa.
  2. Narrowed scan window from 75 days → 41 days centred on the
     midpoint (~45 % less CPU work per year).
  3. KV cache (24 h TTL) on the route — first uncached hit ~1.5 s,
     subsequent identical hits return `X-Cache: HIT` instantly.
  4. Default span trimmed from 10 → 5 years.
  Vijayawada / 1989-09-14 / Next 25 years now succeeds (commit `3d2ffb1`).
- TithiAnniversary and TeluguBirthday "Your current city" field is now
  **editable inline**. Click `[Change]` / `[మార్చండి]` → geocode
  typeahead expands → selecting a city updates only the local form
  state. `localStorage` is never touched, so the app's saved city is
  unchanged when the user navigates away. Bilingual disclaimer
  explains the override scope (commit `f721255`).
- AppHeader title `<Link>` was rendering at 38.5 px (two stacked text
  lines, no padding) — below the 44 px touch-target floor. Bumped to
  `min-h-[44px] py-1 justify-center` (commit `1b9e717`).
- AppHeader nav `<Link>`s (Festivals / Muhurtam / Nakshatra / Reminders)
  were rendering at 18 px (`text-xs` with no padding) — caught by the
  e2e touch-target test once the previous offenders were fixed. Bumped
  to `inline-flex items-center min-h-[40px] py-2`. Visual layout
  unchanged (commit `0f61d24`).
- CityWelcome modal now has `role="dialog"`, `aria-modal="true"` and
  `data-testid="city-welcome"`. The e2e CityWelcome tests were
  accidentally clicking the AppHeader's `CitySearch` button (which
  also displays "Melbourne" when localStorage is empty) instead of the
  modal's quick-select button. Tests now scope locators with
  `getByTestId("city-welcome")`. Bonus: the keyboard-shortcuts hook
  now correctly disables shortcuts while CityWelcome is showing
  (commit `0f61d24`).
- **Anniversary calendar-year semantics** for masas 11/12 (Magha and
  Phalguna). The legacy `estimateMasaStart` used samvatsaram-relative
  year semantics: a Magha-born user asking for "2026" got Jan 2027
  (Parabhava's Magha) instead of Jan 2026 (Krodhi's Magha). Dropped
  `nextYear: true` from `MASA_MIDPOINT`. The `year` argument now
  consistently means the Gregorian calendar year and the samvatsaram
  label correctly reflects whichever samvatsaram contains that
  Gregorian date. New regression test in `reminders.test.ts`
  (commit `a4af8d1`).
- **Anniversary scan window widened** from 41 → 51 days (±25 from
  midpoint). The Metonic cycle drifts the actual masa start by up to
  ±15 days year-to-year and the tighter window missed late-edge years
  (Magha 2027 ends Feb 26, outside a window ending Feb 18). 108 tests
  pass with the new window (commit `a4af8d1`).
- **TeluguBirthday + TithiAnniversary three-state `daysFromNow`
  styling.** Both finders previously only styled future + zero
  states; past dates from the current year fell through to nothing.
  Now: `=== 0` → 🎂/🪔 gold "Today" badge, `> 0` → "in N days" in
  auspicious green, `< 0` → "N days ago" in muted italic. Past
  birthdays/anniversaries from the current calendar year are still
  shown — they're still legitimate entries for that year, just
  already happened (commits `a4af8d1`, `3f6e78f`).
- **Geocode now returns cities, not addresses.** OpenCage was returning
  street addresses, neighbourhoods and POIs ("Banjara Hills,
  Hyderabad", "12 Main Road, Hyderabad"). The route now filters
  results to city-level `_type` values (`city`, `town`, `village`,
  `municipality`, `county`, `state_district`), rebuilds the display
  name from `components` as "City, State, Country" instead of using
  `r.formatted`, deduplicates, and asks OpenCage for `min_confidence=3`
  to trim noise server-side. Falls back to all results if no city
  match (commit `3f6e78f`).
- **Anniversary KV cache key bumped to `anniversary-v2:`** to
  invalidate entries computed with the buggy samvatsaram-relative
  semantics and the narrower 41-day window. Without an algorithm
  version in the key those entries would persist for 24h and serve
  stale data (commit `3f6e78f`).
- `next.config.mjs`: skip `setupDevPlatform` when `process.env.CI` is set
  and wrap the import in `try/catch`. Stops Playwright e2e from crashing
  in CI with `Cannot find module 'wrangler'` (commit `6efaa1f`).
- `playwright.config.ts`: dropped `devices['iPhone …']` / `iPad Mini`
  spreads — they silently switched the engine to webkit. All five
  viewports now share a `mobileChromium` base built from
  `devices['Desktop Chrome']` so CI only needs `playwright install
  chromium` (commit `03446ca`).
- `e2e/mobile.spec.ts` city-welcome locator: replaced the invalid mixed
  CSS / `text=` selector with `.or()` chaining over `getByRole` /
  `getByText` (commit `03446ca`).
- LanguageToggle and CitySearch: bumped to `py-2 min-h-[44px]`. The
  Telugu glyph "తె" pushes the rendered height of `py-1.5` buttons to
  ~38.5 px, below the 44 px accessibility target. NavBar Month/Day
  tabs bumped to `py-2 min-h-[40px]` (commit `57a6938`).
- AngaCard now exposes `data-testid="anga-card"`. The Pancha Anga
  layout test uses `cards.nth(0)` / `cards.nth(1)` instead of the
  fragile `:has-text("TITHI")` selector that was matching parent
  containers and reporting a false 102 px row gap (commit `57a6938`).

### Docs
- CHANGELOG split into accurate `[1.0.0]`, `[1.1.0]`, `[1.1.1]` sections
  matching the actual git tags (commit `79307bf`).
- ARCHITECTURE.md: new "Testing" section covering Jest unit/regression
  and Playwright e2e layers, including the CI guard and viewport list
  (commit `79307bf`).
- CONTRIBUTING.md: new "Running Mobile E2E Tests (Playwright)"
  subsection (commit `79307bf`).

---

## [1.1.1] — 2026-04-06: Mobile hotfix

### Fixed
- AppHeader nav links: wrapped in a horizontally scrollable container with
  `flex-shrink-0` on each link and a trailing spacer so the last link
  (పితృ స్మరణ) is fully reachable on 375 px screens. The `?` button is
  now pinned outside the scroll region.
- DayDetail share button: replaced absolute positioning with a flex row
  (`<h1 flex-1>` + `<button flex-shrink-0>`). Share label is hidden below
  the `sm` breakpoint and the button has a 44 px touch target. No more
  overlap with the date heading on narrow phones.
- `next.config.mjs`: `setupDevPlatform` is now skipped when `process.env.CI`
  is set and the import is wrapped in `try/catch`. Stops Playwright e2e
  from crashing in CI with `Cannot find module 'wrangler'`.

### Added
- `.scrollbar-hide` cross-browser CSS utility in `globals.css`
- Playwright e2e suite (`@playwright/test`) with five viewports: 375, 390,
  430, 768, 1280 px, all running on chromium so CI only needs
  `playwright install chromium`
- `e2e/mobile.spec.ts` covering: date/share overlap, 2-column Pancha Anga,
  Telugu visibility, nav scroll, primary touch targets ≥ 40 px,
  CityWelcome first-visit prompt, screenshot capture
- `playwright.config.ts` with a `mobileChromium` shared base
- `package.json` scripts: `test:e2e`, `test:e2e:mobile`,
  `test:e2e:report`, `test:e2e:screenshots`
- GitHub Actions: new `e2e` job that runs after the unit-test job, installs
  chromium with deps, and uploads screenshots + HTML report as artifacts
  on failure

---

## [1.1.0] — 2026-04-06: UX improvements + polish

### Added
- LocationDisclaimer component — soft informational banner explaining that Tithi
  transitions may fall on different Gregorian dates than printed Indian Panchangams
  for users in non-Indian timezones; shown on day, month, festival pages and
  CityWelcome confirmation
- isNonIndianTimezone() and getOffsetDescription() helpers in engine/timezone.ts
- PrintableCalendar component + @media print styles — Venkatrama-style A4/Letter
  month print with Telugu Tithis, moon phases, festival names, city footer
- Print button on month view (🖨️ ముద్రించు)
- Full bilingual support on the reminder form: REMINDERS and TITHI_ANNIV i18n
  namespaces; AncestorReminder and TithiAnniversary use i18n for every label,
  placeholder, option, button and status message
- RemindersHeader client component for bilingual page title and intro
- Static OG image (1200×630, Lotus Dawn, Telugu script, feature pills)
- Dynamic OG images for day and month pages via next/og (edge runtime)
- Full OpenGraph + Twitter card metadata in root layout (locale, alternateLocale,
  siteName, robots, icons, metadataBase)
- generateMetadata for day pages — split into server page.tsx + DayPageClient
- useKeyboardShortcuts hook — ←/→ navigation, T M D F U N R S P ? shortcuts;
  disabled when typing in form fields and when a modal is open (except Escape)
- KeyboardShortcutsHelp bilingual modal with two-column key badges
- Toast component for share confirmation
- Subtle desktop-only ⌨️ hint button in NavBar
- Significant Ekadashi distinction: Vaikunta (Mukkoti), Nirjala, Devshayani,
  Prabodhini — bilingual significance text, gold styling on calendar grid,
  festival tracker and day detail
- significantEkadashis.ts shared module (avoids festivals/festivalMatcher cycle)
- Festival type: isSignificantEkadashi and significance fields
- 6 new engine tests for significant Ekadashis (107 tests total)
- PWA app icons: icon.svg master, real PNG icon-192/512, apple-icon-180,
  favicon-32 and favicon.ico generated with sharp
- manifest.json: full icon set with maskable purpose, screenshots, PWA shortcuts
  (Today / Festivals / Reminders)
- Tooltips on Pancha Anga cards — tap/hover any element for a bilingual explanation
- "What is Panchangam?" LearnModal — accessible from header, explains all 5 elements
- CityWelcome full-screen prompt — guides first-time visitors to select their city
- ErrorState and LoadingState reusable components — consistent UI for all async states
- Custom error page (error.tsx) and 404 page (not-found.tsx)
- src/lib/tooltips.ts — centralised tooltip content for all Panchanga elements

### Changed
- Regular Ekadashis demoted from tier 1 to tier 2; the four sacred Ekadashis
  promoted to tier 1 with custom names
- Sunrise tooltip mentions timezone-driven date differences
- Day page is now a server component with generateMetadata; client logic moved
  to DayPageClient

### Fixed
- Graceful error and loading states across all pages — no more raw error messages
- City selection prompt appears on first visit instead of defaulting silently
- Reminder form is fully bilingual — Telugu users can complete the form without
  reading a single English word
- PWA install icons are now real PNGs (not SVG-as-PNG placeholders), so Android
  and iOS Safari render the home-screen icon correctly

---

## [1.0.0] — 2026-04-06: Public launch milestone

The initial public release. Cuts a stable point at the end of Phase 5,
just before the v1.1.0 UX wave. See the per-phase entries below for the
detailed feature history.

### Highlights
- VSOP87 calculation engine — pure functions, no date limits
- 12 calendar/festival/finder pages (Today, month, day, festivals,
  muhurtam, nakshatra, reminders, tithi anniversary)
- Bilingual Telugu + English throughout (i18n module)
- Cloudflare Pages edge deployment with D1 cache and KV
- 75+ engine tests including 26 Venkatrama regression assertions
- Public API — free, no key required, 7 endpoints
- PWA manifest + service worker (icons later replaced with real PNGs in v1.1.0)
- Live at https://telugupanchangam.app

---

## [0.5.0] — 2026-03-31: Phase 5

### Added
- PWA manifest (manifest.json) with Lotus Dawn theme colours
- Service worker (sw.js) — cache-first for geocoding, network-first for panchangam/festivals
- ServiceWorkerRegistration client component
- Apple mobile web app meta tags in layout
- @cloudflare/next-on-pages adapter for Cloudflare Pages deployment
- `export const runtime = 'edge'` on all API routes and root layout
- D1 cache layer in /api/panchangam (read + write-through)
- D1 persistence for /api/reminders POST (reminder storage)
- src/lib/cloudflare.ts — getDB() and getKV() helpers for Cloudflare bindings
- GitHub Actions deploy workflow (.github/workflows/deploy.yml)
- Cloudflare Pages project created and first production deployment
- nodejs_compat_v2 compatibility flag for full Node.js API support
- .npmrc with legacy-peer-deps=true for build compatibility

### Fixed
- API routes now read env vars via getEnvVar() (Cloudflare request context) instead of process.env
- City search works worldwide — OPENCAGE_API_KEY secret set on CF Pages production
- Reminders route reads RESEND_API_KEY and RESEND_FROM_EMAIL from CF context

### Changed
- next.config.mjs: dynamic import of setupDevPlatform (dev only)
- wrangler.toml: pages_build_output_dir, nodejs_compat_v2 flag
- README + API.md: live URL updated to telugupanchangam.app

---

## [0.4.0] — 2026-03-31: Phase 4

### Added
- Nakshatra Finder — Janma Nakshatra from exact birth date, time, and city
- Raasi (zodiac sign) mapping for all 27 Nakshatras × 4 Padas
- Tarabalam daily indicator (9 Tara qualities: Janma through Parama Mitra)
- `/api/nakshatra` API route with zod validation + disclaimer
- `/nakshatra` page with birth details form, 3-card result layout
- MoonPhase SVG enhanced with glow filter (intensity scales with illumination)
- MoonPhase now supports bilingual phase label below the moon visual
- Nakshatra link added to AppHeader quick links

---

## [0.3.0] — 2026-03-31: Phase 3

### Added
- Festival engine — `getFestivalsForYear()` scans all 365 days of any year
- Per-day festival matcher — `matchFestivalsForDay()` wired into `calculateDayPanchangam()`
- Tier 1 festivals: Ugadi, Sri Rama Navami, Hanuman Jayanti, Sankranti cluster, Sivaratri, Krishna Janmashtami, Vinayaka Chaturthi, Vijayadasami, Deepavali, Karthika Purnima, Holi, Akshaya Tritiya, Varalakshmi Vratam, all Ekadashis/Amavasyas/Purnimas
- Tier 2 festivals: Bathukamma (9-day), Bonalu, Karthika Somavaram, Nagula Chavithi
- Tier 3 festivals: Republic Day, Independence Day, Gandhi Jayanti, Telangana/AP Formation Days, Christmas
- Next-tithi matching for Ugadi (March 19) and Maha Sivaratri (Feb 15) — matches Venkatrama
- Festival badges on CalendarGrid — tiered colour dots (gold/accent/muted) with overflow count
- `/festivals` page — year nav, filter pills (All/Major/Regional/Ekadashi/Amavasya), next festival banner
- `/api/festivals` API route
- Muhurtam engine — `getMuhurtamWindows()` with Nakshatra/Yoga/Tithi quality rules, Rahukalam/Yamagandam exclusion
- `/muhurtam` page — date picker, day range selector, quality-badged window cards
- `/api/muhurtam` API route
- Festival + Muhurtam + Reminders quick links added to AppHeader

---

## [0.2.0] — 2026-03-25: Phase 2

### Added
- Month calendar view — 7-column grid, Sunday to Saturday
- Telugu Tithi names on each day cell (font-noto-telugu)
- Moon phase emoji icon per day
- Amavasya (dark bg), Purnima (gold bg), Ekadashi (green tint) highlighting
- Festival badges on relevant days
- Day detail view — full Panchangam for any date
- All 5 Pancha Anga cards with staggered entrance animations
- SVG moon phase visual with pulse animation, illumination bar
- Rahukalam, Gulika Kalam, Yamagandam with danger-coloured left border
- Navigation bar — prev/next day/month, Month/Day tabs, Today button, date jump input
- Telugu/English language toggle (persisted in localStorage)
- City search with typeahead (OpenCage geocoding, server-side proxy)
- Lotus Dawn theme — full Tailwind CSS implementation
- CSS-only animations: fadeUp, slideIn, moonPulse, todayPulse, hover states
- Hover tooltips on calendar day cells (full tithi in Telugu + English)
- API routes: /api/panchangam, /api/panchangam/month, /api/geocode
- i18n strings for all UI labels (Telugu + English)
- పితృ స్మరణ (Ancestor Remembrance) feature:
  - Upcoming Amavasyas list with Mahalaya/Somavati badges
  - Reminder form: name, email, tithi types, personal note
  - Confirmation email via Resend (bilingual, Lotus Dawn themed)
  - One-click unsubscribe page
  - engine/reminders.ts: getUpcomingAmavasyas/Ekadashis
  - emailTemplates.ts: 3 bilingual HTML email templates
  - API: POST /api/reminders, GET /api/reminders, GET /api/reminders/unsubscribe
- Google Fonts: Noto Sans Telugu, Playfair Display, Lora

---

## [0.1.0] — 2026-03-24: Phase 1

### Added
- GitHub repository — public, MIT licence
- Project scaffold — Next.js 14, TypeScript, Tailwind CSS
- Full documentation set: CLAUDE.md, ARCHITECTURE.md, ALGORITHM.md, API.md, DEPLOYMENT.md, CONTRIBUTING.md
- Calculation engine (src/engine/): 13 modules wrapping @ishubhamx/panchangam-js
  - Tithi, Nakshatra, Yoga, Karana, Vara with bilingual Telugu/English names
  - Samvatsaram (60-year Jupiter cycle) mapper
  - Telugu Masa (Amanta lunar month) calculator including Adhika Masa
  - Ritu (season) and Ayana (solstice period) calculation
  - Rahukalam, Gulika Kalam, Yamagandam from weekday + actual local sunrise
  - Sunrise/sunset/moonrise/moonset via SunCalc
  - Moon phase calculation and naming (Telugu + English)
  - Timezone-agnostic ISO 8601 formatting
- Bilingual data files: tithi.json, nakshatra.json, yoga.json, karana.json, masa.json, samvatsaram.json
- Venkatrama 2026 regression test suite — 26 assertions validated against printed calendar
- 75 total tests across 9 suites — all passing
