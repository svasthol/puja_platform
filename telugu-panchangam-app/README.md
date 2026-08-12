<div align="center">

# తెలుగు పంచాంగం
## Telugu Panchangam App

*Visual. Time-based. Free forever. For the community.*

[![MIT Licence](https://img.shields.io/badge/licence-MIT-orange.svg)](LICENSE)
[![Cloudflare Pages](https://img.shields.io/badge/deployed-Cloudflare%20Pages-orange)](https://telugupanchangam.app)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**[Live App](https://telugupanchangam.app)** · **[API Docs](API.md)** · **[Report a Bug](https://github.com/suhasatluri/telugu-panchangam-app/issues)**

</div>

---

## What Is This?

A free, open-source Telugu Panchangam calendar for any city in the world, for any date — past, present, or future. The sky has no expiry date, and neither does this app.

**It is not an astrology app.** It shows the sky as it is — sunrise, sunset, moonrise, moonset, moon phases — alongside the five traditional Panchanga elements that generations of Telugu families have used to mark their days.

No ads. No login. No subscriptions. Free forever.

---

## Features

| Feature | Status | Description |
|---|---|---|
| 📅 Daily Panchangam | ✅ Live | Tithi, Nakshatra, Yoga, Karana, Vara with precise end times |
| 🌅 Sky Timings | ✅ Live | Sunrise, sunset, moonrise, moonset — city-specific |
| 🌗 Moon Phase | ✅ Live | SVG visual, Telugu + English name, illumination % |
| 🗓️ Month Calendar | ✅ Live | Venkatrama-style grid, moon phases, Telugu Tithi names |
| 🙏 పితృ స్మరణ | ✅ Live | Ancestor remembrance — Amavasya and Ekadashi reminders |
| 🕐 తిథి వార్షికం | ✅ Live | Death anniversary Tithi finder — any year |
| 🌍 Any City | ✅ Live | Sunrise-anchored timings for any city worldwide |
| 🔤 Telugu + English | ✅ Live | Full bilingual toggle, Noto Sans Telugu throughout |
| 🎉 Festival Tracker | ✅ Live | 40+ Telugu festivals for any year — Ugadi, Sankranti, Deepavali and more |
| 🕐 Muhurtam Finder | ✅ Live | Auspicious windows within any date range, excluding Rahukalam |
| ⭐ Nakshatra Finder | ✅ Live | Janma Nakshatra + Raasi + Tarabalam from birth date, time, city |
| 💡 Tooltips | ✅ Live | Tap any Panchanga element for a bilingual explanation |
| 🏠 City Welcome | ✅ Live | Guided city selection for first-time visitors |
| 🛡️ Error Handling | ✅ Live | Graceful error and loading states across all pages |
| 📱 PWA | ✅ Live | Installable on Android and iPhone, works offline |
| 🔌 Public API | ✅ Live | Free, no key required — 7 endpoints, embed in your website |
| 🖨️ Print Calendar | ✅ Live | Clean Venkatrama-style month print, fits A4/Letter |
| ⌨️ Keyboard Shortcuts | ✅ Live | ←/→ navigation, T M D F U N R S P ? |
| 🌍 Location Disclaimer | ✅ Live | Explains timezone-driven date differences for non-Indian cities |
| ✨ Significant Ekadashis | ✅ Live | Vaikunta, Nirjala, Devshayani, Prabodhini highlighted with bilingual significance |
| 📲 Social OG Images | ✅ Live | WhatsApp/Twitter previews, dynamic per-day cards |

---

## Quick Start

### Use the App
Visit [telugupanchangam.app](https://telugupanchangam.app)

### Use the API

```bash
# Today's Panchangam for Melbourne
curl "https://telugupanchangam.app/api/panchangam?date=2026-03-31&lat=-37.8136&lng=144.9631&tz=Australia/Melbourne"
```

Full API documentation: [API.md](API.md)

### Run Locally

```bash
git clone https://github.com/suhasatluri/telugu-panchangam-app.git
cd telugu-panchangam-app
npm install
cp .env.example .env.local
# Add your OpenCage API key to .env.local
npm run dev
# Open http://localhost:3000
```

### Deploy Your Own Instance

See [DEPLOYMENT.md](DEPLOYMENT.md) for full Cloudflare Pages setup instructions.

---

## Tech Stack

```
Next.js 14 (App Router + TypeScript)
Tailwind CSS — Lotus Dawn theme
@ishubhamx/panchangam-js — calculation engine (MIT)
suncalc — sunrise/moonrise/phase
Cloudflare Pages + Workers + D1 + KV
```

---

## Documentation

| Document | Description |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Master project brief — start here |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and decisions |
| [ALGORITHM.md](ALGORITHM.md) | Complete Panchangam calculation methodology |
| [API.md](API.md) | Full API reference |
| [DEPLOYMENT.md](DEPLOYMENT.md) | How to deploy your own instance |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [decisions/](decisions/) | Architecture Decision Records |

---

## Accuracy

The calculation engine is validated against the **Venkatrama & Co. published calendar (Eluru)**, January–June 2026 — one of the most trusted Telugu Panchangam publishers for over a century.

Additional validation: 200 consecutive days cross-referenced against Drik Panchang with 100% accuracy.

If you find a discrepancy between this app and your trusted local Panchangam, please [open an issue](https://github.com/suhasatluri/telugu-panchangam-app/issues/new?template=festival_correction.md) — accuracy is the most important thing we maintain.

---

## Contributing

Contributions are welcome from developers, traditional scholars, Telugu speakers, and community members. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards.

### Your first contribution in 5 minutes

The easiest entry points if you've never contributed before:

1. **Spotted a wrong festival date?** Open a [Festival Correction issue](https://github.com/suhasatluri/telugu-panchangam-app/issues/new?template=festival_correction.yml) — no code needed. If your correction matches Venkatrama & Co., it gets fixed fast.
2. **Improving a Telugu translation?** All UI strings live in [`src/lib/i18n.ts`](src/lib/i18n.ts). Edit the `te:` value next to any string and open a PR.
3. **Adding a city?** If your city is missing from the geocoding suggestions, open a [Bug issue](https://github.com/suhasatluri/telugu-panchangam-app/issues/new?template=bug_report.yml) and we'll add it.
4. **Fixing a bug or adding a feature?** Browse the [`good first issue`](https://github.com/suhasatluri/telugu-panchangam-app/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) label, fork the repo, and follow the [Development Setup](CONTRIBUTING.md#development-setup) section.

### Roadmap

The high-level direction is tracked in [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`. Big themes for the next phase:

- More Telugu festivals (regional / temple-specific) and family Vratam reminders
- Multi-language reminder emails (Tamil, Kannada, Hindi)
- Offline-first PWA with full year pre-cached
- An iOS / Android wrapper for app stores
- A "Family Calendar" mode that aggregates multiple users' Tithi anniversaries

If any of these excite you, comment on the relevant CHANGELOG line or open a Discussion.

---

## Licence

MIT — see [LICENSE](LICENSE).

Free to use, fork, embed, and build upon. If you build something with it, we would love to know.

---

## Acknowledgements

- **Venkatrama & Co., Eluru** — the gold standard of Telugu Panchangam publishing since 1841
- **@ishubhamx** — for the open-source panchangam-js calculation library
- **The Telugu diaspora worldwide** — for keeping the tradition alive

---

<div align="center">

*తెలుగు వారందరికీ అంకితం*

*Dedicated to all Telugu people, everywhere.*

</div>
