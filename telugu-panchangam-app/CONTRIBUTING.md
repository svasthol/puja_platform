# Contributing — Telugu Panchangam App

నమస్కారం! Welcome. We are glad you are here.

This is a community project built for the Telugu-speaking world. Every contribution — whether it is a bug report, a festival correction, a code improvement, or a translation — genuinely matters.

---

## Ways to Contribute

### 🐛 Report a Bug
Open an issue using the **Bug Report** template. Include the date, city, and what you expected vs what you saw.

### 📅 Report a Festival or Panchangam Error
Open an issue using the **Festival Correction** template. This is especially valuable — if you have access to a printed Venkatrama or other trusted Panchangam and see a discrepancy, please tell us. Include the date and the reference you are using.

### 💻 Write Code
See [Development Setup](#development-setup) below.

### 🌐 Improve Translations
All Telugu strings are in `src/data/` JSON files and `src/lib/i18n.ts`. If you see a Telugu translation that could be improved — more natural, more accurate, or using the correct regional spelling — please open a PR.

### 📖 Improve Documentation
Documentation PRs are always welcome. If anything in `ARCHITECTURE.md`, `ALGORITHM.md`, or `API.md` is unclear, please improve it.

### 🌆 Add a City
If your city is missing from the geocoding suggestions, open an issue. We will add it to the pre-loaded city list.

### ✨ Other Areas Added in v1.1.0
The following surfaces were added after the initial launch and are open
for contributions:

- **Significant Ekadashis** — `src/engine/significantEkadashis.ts`. Add or
  refine bilingual `significance` text, or extend the list with other
  regionally important Ekadashis (currently: Vaikunta, Nirjala, Devshayani,
  Prabodhini).
- **Keyboard shortcuts** — `src/hooks/useKeyboardShortcuts.ts` and
  `src/components/KeyboardShortcutsHelp.tsx`. Suggest new shortcuts via an
  issue first so we can keep the set small and conflict-free.
- **Location disclaimer copy** — `src/components/LocationDisclaimer.tsx`.
  Translation improvements welcome.
- **Bilingual reminder form** — strings live in `REMINDERS` and
  `TITHI_ANNIV` namespaces in `src/lib/i18n.ts`. PRs improving Telugu
  phrasing here are particularly valuable.
- **Print stylesheet** — `@media print` block in `src/app/globals.css`
  and `src/components/PrintableCalendar.tsx`. Test prints from real
  printers and report layout issues.
- **OG / social share images** — static `public/og-image.svg` and
  dynamic `src/app/[year]/[month]/{,[day]/}opengraph-image.tsx`.

---

## Development Setup

### Prerequisites

- Node.js 20.x (CI) or 24.x (local development)
- npm 9.x or later
- A Cloudflare account (free) for deployment testing
- Git

### Steps

```bash
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/telugu-panchangam-app
cd telugu-panchangam-app

# 2. Install dependencies
npm install

# 3. Copy the environment template
cp .env.example .env.local

# 4. Fill in .env.local
# OPENCAGE_API_KEY — get a free key at opencagedata.com (2,500 req/day free)
# Leave Cloudflare keys blank for local development — KV/D1 use local simulators

# 5. Start development server
npm run dev
# App runs at http://localhost:3000

# 6. Run tests (107 tests, ~50s)
npm test
```

### Running Validation Tests

The Venkatrama calendar images in `validation/venkatrama/` are our ground truth:

```bash
# Run all validation tests
npm test -- validation/regression.test.ts

# Run only the engine module tests
npm run test:engine

# Run only the Venkatrama regression assertions
npm run test:validation
```

### Running Mobile E2E Tests (Playwright)

We catch mobile layout regressions with Playwright across five viewports
(375, 390, 430, 768, 1280 px). All viewports run on chromium so the
one-time browser install is small.

```bash
# One-time setup — installs the chromium binary
npx playwright install chromium --with-deps

# Run the mobile-only subset (375 + 390 px) — fastest feedback
npm run test:e2e:mobile

# Run all five viewports
npm run test:e2e

# Open the last HTML report
npm run test:e2e:report
```

The dev server starts automatically via Playwright's `webServer` hook —
you do **not** need a separate `npm run dev` running.

CI runs the mobile e2e job on every push (`.github/workflows/ci.yml` →
`e2e` job). Screenshots and the HTML report are uploaded as artifacts
on failure.

---

## Project Structure for Contributors

```
src/engine/    ← The calculation core. Most impactful place to contribute.
src/data/      ← JSON data files — festival rules, Nakshatra names, etc.
src/lib/i18n.ts ← All UI strings in Telugu and English
validation/    ← Reference data and regression tests
docs/          ← Documentation (ALGORITHM.md is especially important)
```

---

## Pull Request Process

1. **Branch from `main`** with a descriptive name:
   - `fix/rahukalam-melbourne-dst`
   - `feat/add-adhika-masa-indicator`
   - `docs/clarify-ayanamsa-calculation`

2. **Write or update tests** for your change. PRs without tests for engine changes will not be merged.

3. **Run the full test suite** before submitting (all 107 tests must pass):
   ```bash
   npm test
   npm run typecheck
   npm run lint
   ```

4. **Fill in the PR template** — describe what changed and why.

5. **One PR, one concern.** Don't mix a bug fix and a new feature.

### PR Review Criteria

- Does it match the project mission? (visual, time-based, no astrology)
- Is it tested?
- Does it pass the Venkatrama validation tests?
- Is the code readable and documented?

---

## Festival Correction Guidelines

Festival accuracy is the most important form of contribution. If you believe a festival date is wrong:

1. Open an issue with the **Festival Correction** template
2. Provide:
   - The date the app shows
   - The date you believe is correct
   - Your reference source (Venkatrama, Eenadu, another trusted Panchangam)
   - The city/timezone relevant to your observation
3. If you can confirm the Venkatrama calendar agrees with your correction, mention this — it is the fastest path to a fix

---

## Translation Glossary

All UI strings live in `src/lib/i18n.ts`. They are organised into three
groups — please follow the same structure when adding new strings.

| Where | Used by | Notes |
|---|---|---|
| `UI` (flat record) | App-wide labels (Pancha Anga, sky timings, navigation) | Read with `t("key", lang)` or `UI.key[lang]` |
| `REMINDERS` namespace | The పితృ స్మరణ form (`AncestorReminder.tsx`) | Form labels, options, success/error states |
| `TITHI_ANNIV` namespace | The తిథి వార్షికం finder (`TithiAnniversary.tsx`) | Form, results, inline + annual reminder UIs |

**Conventions for Telugu translators:**

- Use **Andhra Pradesh / Telangana** spellings — this is our primary
  audience. We follow Venkatrama & Co. (Eluru) for traditional terms.
- Telugu numerals are NOT used — keep Arabic numerals (1, 2, 3) for
  dates, times, and counts so the UI stays consistent across languages.
- Diacritics matter — please double-check vowel marks (గుణింతాలు)
  before submitting.
- Tooltip content lives separately in `src/lib/tooltips.ts` — same
  bilingual structure, same conventions.
- Festival names live in `src/engine/festivals.ts`,
  `src/engine/festivalMatcher.ts` and (for the four sacred Ekadashis)
  `src/engine/significantEkadashis.ts`. Keep the names in all three
  in sync if you're correcting a name.

If you are uncertain about a phrasing choice, open an issue first so
we can discuss before you spend time on a PR.

---

## Code of Conduct

This project follows a simple principle: **be respectful**.

- Be patient with questions — not everyone has the same background
- Be constructive in code reviews
- Remember the goal: this project exists to serve the community, not to win arguments

Festival date disputes are common in the Telugu Panchangam tradition — different publishers sometimes give different dates. When in doubt, **the Venkatrama & Co. calendar (Eluru)** is our primary reference for AP/Telangana conventions.

---

## Recognition

All contributors are listed in `CONTRIBUTORS.md`. Significant contributions are highlighted in release notes.

---

ధన్యవాదాలు — Thank you for contributing.
