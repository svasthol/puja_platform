# API Reference — Telugu Panchangam App

> **Base URL:** `https://telugupanchangam.app/api`
> **Version:** v1
> **Authentication:** None required
> **Rate Limit:** 100 requests per minute per IP (enforced by Cloudflare)
> **Format:** JSON over HTTPS

The Telugu Panchangam API is **free and open** — no registration, no API keys, no usage tracking. You can use it in your own applications, websites, or tools.

---

## Table of Contents

1. [General Conventions](#general-conventions)
2. [GET /api/panchangam](#get-apipanchangam)
3. [GET /api/panchangam/month](#get-apipanchangammonth)
4. [GET /api/festivals](#get-apifestivals)
5. [GET /api/geocode](#get-apigeocode)
6. [GET /api/muhurtam](#get-apimuhurtam)
7. [GET /api/nakshatra](#get-apinakshatra)
8. [GET /api/reminders](#get-apireminders)
9. [POST /api/reminders](#post-apireminders)
10. [GET /api/reminders/unsubscribe](#get-apiremindersunsubscribe)
11. [Error Codes](#error-codes)
12. [Data Types](#data-types)
13. [Code Examples](#code-examples)
14. [Self-Hosting](#self-hosting)

---

## General Conventions

### Coordinates

- Latitude: decimal degrees, positive = North, negative = South
- Longitude: decimal degrees, positive = East, negative = West
- Precision: 5 decimal places (±1.1 metre accuracy — more than sufficient)

```
Melbourne:  lat=-37.81400  lng=144.96330
Hyderabad:  lat=17.38500   lng=78.48600
London:     lat=51.50740   lng=-0.12780
New York:   lat=40.71280   lng=-74.00600
```

### Timezones

Use IANA timezone strings: `Australia/Melbourne`, `Asia/Kolkata`, `America/New_York`

Get the timezone for any city from `/api/geocode`.

### Date Format

ISO 8601: `YYYY-MM-DD` (e.g. `2026-03-23`)

### Language Parameter

`lang=te` — Telugu script
`lang=en` — English (default if omitted)
`lang=both` — Both languages in response (default for all endpoints)

### Response Envelope

Every successful response:
```json
{
  "data": { ... },
  "source": "cache | engine",
  "computedAt": "2026-03-23T04:00:00.000Z"
}
```

Every error response:
```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": "Optional additional context"
}
```

---

## GET /api/panchangam

Returns the complete Panchangam for a single date and location.

### Request

```
GET /api/panchangam?date={date}&lat={lat}&lng={lng}&tz={timezone}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `date` | string | Yes | ISO date: `2026-03-23` |
| `lat` | number | Yes | Latitude: `-37.81400` |
| `lng` | number | Yes | Longitude: `144.96330` |
| `tz` | string | Yes | IANA timezone: `Australia/Melbourne` |
| `lang` | string | No | `te`, `en`, or `both` (default: `both`) |

### Example Request

```
GET /api/panchangam?date=2026-03-23&lat=-37.81400&lng=144.96330&tz=Australia/Melbourne
```

### Example Response

```json
{
  "data": {
    "date": "2026-03-23",
    "city": "Melbourne, Australia",
    "samvatsaram": {
      "te": "పరాభవ నామ సంవత్సరం",
      "en": "Parabhava Nama Samvatsaram",
      "number": 60
    },
    "masa": {
      "te": "చైత్ర మాసం",
      "en": "Chaitra Masa",
      "number": 1,
      "isAdhika": false
    },
    "paksha": {
      "te": "శుక్ల పక్షం",
      "en": "Shukla Paksha",
      "value": "shukla"
    },
    "ritu": {
      "te": "వసంత ఋతువు",
      "en": "Vasanta (Spring)"
    },
    "ayana": {
      "te": "ఉత్తరాయణం",
      "en": "Uttarayana"
    },
    "tithi": {
      "te": "పంచమి",
      "en": "Panchami",
      "number": 5,
      "endsAt": "2026-03-23T18:32:00+11:00",
      "nextTithi": {
        "te": "షష్టి",
        "en": "Shashthi",
        "number": 6
      }
    },
    "nakshatra": {
      "te": "కృత్తిక",
      "en": "Krittika",
      "number": 3,
      "pada": 2,
      "endsAt": "2026-03-23T20:15:00+11:00"
    },
    "yoga": {
      "te": "శుభ",
      "en": "Shubha",
      "number": 23,
      "isAuspicious": true,
      "endsAt": "2026-03-24T06:44:00+11:00"
    },
    "karana": {
      "te": "బవ",
      "en": "Bava",
      "number": 1,
      "endsAt": "2026-03-23T18:32:00+11:00"
    },
    "vara": {
      "te": "సోమవారం",
      "en": "Monday",
      "number": 1
    },
    "sunrise": "2026-03-23T07:32:00+11:00",
    "sunset": "2026-03-23T19:45:00+11:00",
    "moonrise": "2026-03-23T10:18:00+11:00",
    "moonset": "2026-03-23T23:52:00+11:00",
    "moonPhase": {
      "te": "శుక్ల పంచమి",
      "en": "Waxing Crescent",
      "illuminationPercent": 28.4,
      "phase": 0.094
    },
    "rahukalam": {
      "start": "2026-03-23T09:03:00+11:00",
      "end": "2026-03-23T10:35:00+11:00",
      "te": "రాహుకాలం",
      "en": "Rahukalam"
    },
    "gulikaKalam": {
      "start": "2026-03-23T07:32:00+11:00",
      "end": "2026-03-23T09:03:00+11:00",
      "te": "గులికకాలం",
      "en": "Gulika Kalam"
    },
    "yamagandam": {
      "start": "2026-03-23T13:09:00+11:00",
      "end": "2026-03-23T14:41:00+11:00",
      "te": "యమగండం",
      "en": "Yamagandam"
    },
    "festivals": [
      {
        "te": "శ్రీ పంచమి",
        "en": "Sri Panchami",
        "type": "regional",
        "tier": 2
      }
    ]
  },
  "source": "cache",
  "computedAt": "2026-03-20T04:00:00.000Z"
}
```

---

## GET /api/panchangam/month

Returns Panchangam for every day of a month. One API call instead of 30.

### Request

```
GET /api/panchangam/month?year={year}&month={month}&lat={lat}&lng={lng}&tz={tz}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `year` | number | Yes | Gregorian year: `2026` |
| `month` | number | Yes | Month: `1`–`12` |
| `lat` | number | Yes | Latitude |
| `lng` | number | Yes | Longitude |
| `tz` | string | Yes | IANA timezone |
| `lang` | string | No | `te`, `en`, or `both` |

### Example Request

```
GET /api/panchangam/month?year=2026&month=3&lat=-37.81400&lng=144.96330&tz=Australia/Melbourne
```

### Example Response

```json
{
  "data": {
    "year": 2026,
    "month": 3,
    "monthName": { "te": "మార్చి", "en": "March" },
    "samvatsaram": { "te": "పరాభవ", "en": "Parabhava" },
    "days": [
      {
        "date": "2026-03-01",
        "gregorianDay": 1,
        "tithi": { "te": "తదియ", "en": "Tritiya", "number": 3 },
        "nakshatra": { "te": "పుష్యమి", "en": "Pushya", "number": 8 },
        "moonPhase": { "illuminationPercent": 12.1, "phase": 0.04 },
        "festivals": [],
        "isEkadashi": false,
        "isAmavasya": false,
        "isPurnima": false
      }
    ]
  },
  "source": "cache",
  "computedAt": "2026-03-01T00:00:00.000Z"
}
```

Note: The month endpoint returns a **summary** (tithi, nakshatra, moon phase, festivals) for performance. Use `/api/panchangam` for the full 25-field Panchangam for a specific day.

---

## GET /api/festivals

Returns all festivals for a given year.

### Request

```
GET /api/festivals?year={year}&lat={lat}&lng={lng}&tz={tz}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `year` | number | Yes | Gregorian year: `2026` |
| `lat` | number | Yes | Latitude |
| `lng` | number | Yes | Longitude |
| `tz` | string | Yes | IANA timezone |

### Example Request

```
GET /api/festivals?year=2026&lat=17.385&lng=78.486&tz=Asia/Kolkata
```

### Example Response

```json
{
  "data": {
    "year": 2026,
    "count": 68,
    "festivals": [
      {
        "date": "2026-01-14",
        "te": "భోగి",
        "en": "Bhogi",
        "type": "solar",
        "tier": 1,
        "description": {
          "en": "Day before Makar Sankranti. Bonfire festival marking end of winter."
        }
      },
      {
        "date": "2026-01-15",
        "te": "మకర సంక్రాంతి",
        "en": "Makar Sankranti",
        "type": "solar",
        "tier": 1,
        "description": {
          "en": "Sun enters Capricorn. Harvest festival. One of the most important Telugu festivals."
        }
      },
      {
        "date": "2026-03-19",
        "te": "ఉగాది",
        "en": "Ugadi — Telugu New Year",
        "type": "tithi",
        "tier": 1,
        "teluguYear": { "te": "పరాభవ నామ సంవత్సరం", "en": "Parabhava Nama Samvatsaram" }
      }
    ]
  },
  "source": "cache",
  "computedAt": "2026-01-01T00:00:00.000Z"
}
```

---

## GET /api/geocode

Converts a city name to coordinates and timezone. Proxied — the OpenCage API key is never exposed to the client.

### Request

```
GET /api/geocode?q={city_name}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `q` | string | Yes | City name: `Melbourne` or `Hyderabad, India` |

### Example Request

```
GET /api/geocode?q=Hyderabad%2C%20India
```

### Example Response

```json
{
  "data": {
    "displayName": "Hyderabad, Telangana, India",
    "lat": 17.38500,
    "lng": 78.48600,
    "timezone": "Asia/Kolkata",
    "country": "India",
    "state": "Telangana"
  },
  "source": "cache"
}
```

---

## GET /api/muhurtam

Returns auspicious time windows within a date range for a location.

### Request

```
GET /api/muhurtam?from={date}&days={days}&lat={lat}&lng={lng}&tz={tz}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `from` | string | Yes | Start date: `2026-04-01` |
| `days` | number | No | Number of days to search (default: 7, max: 30) |
| `lat` | number | Yes | Latitude |
| `lng` | number | Yes | Longitude |
| `tz` | string | Yes | IANA timezone |

### What counts as auspicious

A time window is auspicious when:
- Yoga is auspicious (not Vishkambha, Atiganda, Shula, Ganda, Vyaghata, Vajra, Vyatipata, Parigha, or Vaidhriti)
- Not during Rahukalam, Gulika Kalam, or Yamagandam
- Not during Vishti (Bhadra) Karana

### Example Response

```json
{
  "data": {
    "from": "2026-04-01",
    "to": "2026-04-07",
    "windows": [
      {
        "date": "2026-04-02",
        "dayTe": "గురువారం",
        "dayEn": "Thursday",
        "start": "2026-04-02T09:15:00+11:00",
        "end": "2026-04-02T11:45:00+11:00",
        "tithi": { "te": "పంచమి", "en": "Panchami" },
        "nakshatra": { "te": "రోహిణి", "en": "Rohini" },
        "yoga": { "te": "సౌభాగ్య", "en": "Saubhagya" },
        "quality": "good"
      }
    ]
  }
}
```

---

## GET /api/nakshatra

Returns Janma Nakshatra from birth details.

### Request

```
GET /api/nakshatra?date={date}&time={time}&lat={lat}&lng={lng}&tz={tz}&today_lat={lat}&today_lng={lng}&today_tz={tz}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `date` | string | Yes | Birth date: `1985-04-14` |
| `time` | string | Yes | Birth time (24h): `06:30` |
| `lat` | number | Yes | Birth place latitude |
| `lng` | number | Yes | Birth place longitude |
| `tz` | string | Yes | Birth place timezone |
| `today_lat` | number | No | Current location lat (for Tarabalam) |
| `today_lng` | number | No | Current location lng (for Tarabalam) |
| `today_tz` | string | No | Current timezone (for Tarabalam) |

### Example Response

```json
{
  "data": {
    "janmaNakshatra": {
      "te": "పునర్వసు",
      "en": "Punarvasu",
      "number": 7,
      "pada": 2
    },
    "janmaRaasi": {
      "te": "మిథున",
      "en": "Mithuna (Gemini)"
    },
    "moonLongitude": 83.4,
    "tarabalam": {
      "te": "మిత్ర తార",
      "en": "Mitra Tara",
      "number": 8,
      "isAuspicious": true,
      "description": {
        "en": "Auspicious. Suitable for important activities."
      }
    },
    "disclaimer": "Nakshatra is calculated from the Moon's astronomical position at birth. Accuracy depends on the precision of birth time. No predictive content is provided."
  }
}
```

---

## GET /api/reminders

Returns upcoming Amavasya and Ekadashi dates for a location.

### Request

```
GET /api/reminders?lat={lat}&lng={lng}&tz={tz}&count={count}
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lat` | number | Yes | Latitude |
| `lng` | number | Yes | Longitude |
| `tz` | string | Yes | IANA timezone |
| `count` | number | No | Number of upcoming dates (default: 6, max: 12) |

---

## POST /api/reminders

Creates an email reminder for Amavasya, Ekadashi, or a Tithi anniversary date.

### Request Body (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | Yes | Email address for reminder |
| `name` | string | Yes | Ancestor or person name |
| `city_name` | string | Yes | City name for display |
| `lat` | number | Yes | Latitude |
| `lng` | number | Yes | Longitude |
| `tz` | string | Yes | IANA timezone |
| `tithi_types` | string[] | Yes | Types to remind: `["amavasya"]`, `["ekadashi"]`, etc. |
| `reminder_type` | string | No | `amavasya`, `ekadashi`, or `tithi_anniversary` (default: `amavasya`) |
| `remind_days_before` | number | No | Days before the event (0–2, default: 0) |
| `remind_time` | string | No | Preferred reminder time |
| `personal_note` | string | No | Personal note (max 300 chars) |

Sends a bilingual confirmation email via Resend. Stores reminder in Cloudflare D1.

---

## GET /api/reminders/unsubscribe

One-click email unsubscribe. Returns an HTML page confirming cancellation.

---

## POST /api/cron/send-reminders

**Internal endpoint — not part of the public API.** Fired by a daily
cron scheduler (currently a GitHub Actions workflow at
`.github/workflows/daily-reminders.yml`) to actually deliver the
reminder emails users have signed up for.

### Authentication

Required header:

```
Authorization: Bearer $CRON_SECRET
```

`CRON_SECRET` lives in Cloudflare Pages production secrets and (the
same value) in the GitHub Actions secret of the same name. Generate
with `openssl rand -hex 32`.

### Behaviour

For each `active = 1` row in the `reminders` table:

1. Compute today's date in the user's IANA timezone (`tz` column).
2. Compute `target_date = today + remind_days_before`.
3. Calculate the panchangam for `target_date` at the user's lat/lng.
4. **For monthly reminders** (`reminder_type = 'amavasya' | 'ekadashi'`),
   match against the user's `tithi_types` opt-in list. Fires on the
   first matching tithi (Amavasya = 30, Shukla Ekadashi = 11, Krishna
   Ekadashi = 26, Purnima = 15).
5. **For tithi anniversaries** (`reminder_type = 'tithi_anniversary'`),
   match the exact stored `(masa, paksha, tithi)` triple. **Adhika
   masas are skipped** — anniversaries always fall in the regular
   month.
6. If matched, send a bilingual email via Resend (`reminderEmail` or
   `anniversaryReminderEmail` template), then mark `last_sent_date`
   so the row is skipped on a second invocation the same day.
7. If not matched, leave the row untouched.

### Idempotency

The `last_sent_date` column ensures each reminder fires at most once
per calendar day even if the cron is invoked multiple times. The
schedule (00:30 UTC) is best-effort — GitHub Actions cron has up to
~15 minutes of jitter — but that's fine because the route is safe
to retry.

### Response

```json
{
  "ok": true,
  "scanned": 12,
  "sent": 3,
  "skipped_already_sent": 1,
  "no_match": 8,
  "errors": 0,
  "details": [
    { "id": "abc-123", "email": "user@example.com", "result": "sent", "kind": "amavasya" },
    { "id": "def-456", "email": "other@example.com", "result": "no_match" }
  ]
}
```

Returns `401 UNAUTHORIZED` if the Bearer token is missing or wrong.

---

## Error Codes

| Code | HTTP Status | Meaning |
|---|---|---|
| `INVALID_DATE` | 400 | Invalid date format — use `YYYY-MM-DD` |
| `INVALID_COORDS` | 400 | Latitude or longitude out of range |
| `INVALID_TIMEZONE` | 400 | Unrecognised IANA timezone string |
| `MISSING_PARAM` | 400 | Required parameter not provided |
| `GEOCODE_NOT_FOUND` | 404 | City not found in geocoding service |
| `RATE_LIMITED` | 429 | Exceeded 100 requests/minute per IP |
| `ENGINE_ERROR` | 500 | Calculation engine error (please report) |

---

## Data Types

```typescript
interface DayPanchangam {
  date: string                    // "2026-03-23"
  samvatsaram: BilingualName & { number: number }
  masa: BilingualName & { number: number; isAdhika: boolean }
  paksha: { te: string; en: string; value: 'shukla' | 'krishna' }
  ritu: BilingualName
  ayana: BilingualName
  tithi: BilingualName & { number: number; endsAt: string; nextTithi: BilingualName }
  nakshatra: BilingualName & { number: number; pada: 1|2|3|4; endsAt: string }
  yoga: BilingualName & { number: number; isAuspicious: boolean; endsAt: string }
  karana: BilingualName & { number: number; endsAt: string }
  vara: BilingualName & { number: number }
  sunrise: string                 // ISO 8601 with timezone
  sunset: string
  moonrise: string
  moonset: string
  moonPhase: { te: string; en: string; illuminationPercent: number; phase: number }
  rahukalam: TimePeriod
  gulikaKalam: TimePeriod
  yamagandam: TimePeriod
  festivals: Festival[]
}

interface BilingualName {
  te: string    // Telugu script
  en: string    // English
}

interface TimePeriod {
  start: string   // ISO 8601
  end: string
  te: string
  en: string
}

interface Festival {
  date?: string   // included in /api/festivals, omitted in /api/panchangam
  te: string
  en: string
  type: 'tithi' | 'solar' | 'lookup' | 'fixed'
  tier: 1 | 2 | 3
  description?: { en: string }
}
```

---

## Code Examples

### Fetch today's Panchangam (JavaScript)

```javascript
const response = await fetch(
  'https://telugupanchangam.app/api/panchangam' +
  '?date=2026-03-23&lat=-37.814&lng=144.963&tz=Australia/Melbourne'
)
const { data } = await response.json()

console.log(`Tithi: ${data.tithi.en} (${data.tithi.te})`)
console.log(`Nakshatra: ${data.nakshatra.en} until ${data.nakshatra.endsAt}`)
console.log(`Rahukalam: ${data.rahukalam.start} – ${data.rahukalam.end}`)
```

### Embed in a website (HTML)

```html
<div id="panchangam"></div>
<script>
async function loadPanchangam() {
  const today = new Date().toISOString().split('T')[0]
  const res = await fetch(
    `https://telugupanchangam.app/api/panchangam?date=${today}&lat=17.385&lng=78.486&tz=Asia/Kolkata`
  )
  const { data } = await res.json()
  document.getElementById('panchangam').innerHTML = `
    <p>తిథి: ${data.tithi.te} | Tithi: ${data.tithi.en}</p>
    <p>నక్షత్రం: ${data.nakshatra.te} | Nakshatra: ${data.nakshatra.en}</p>
  `
}
loadPanchangam()
</script>
```

### Python

```python
import httpx
from datetime import date

response = httpx.get(
    "https://telugupanchangam.app/api/panchangam",
    params={
        "date": date.today().isoformat(),
        "lat": 17.385,
        "lng": 78.486,
        "tz": "Asia/Kolkata"
    }
)
data = response.json()["data"]
print(f"Tithi: {data['tithi']['en']} ({data['tithi']['te']})")
print(f"Nakshatra: {data['nakshatra']['en']}")
```

### React component

```tsx
import { useEffect, useState } from 'react'

interface Panchangam { tithi: { te: string; en: string }; nakshatra: { te: string; en: string } }

export function TodayPanchangam({ lat, lng, tz }: { lat: number; lng: number; tz: string }) {
  const [data, setData] = useState<Panchangam | null>(null)

  useEffect(() => {
    const today = new Date().toISOString().split('T')[0]
    fetch(`https://telugupanchangam.app/api/panchangam?date=${today}&lat=${lat}&lng=${lng}&tz=${tz}`)
      .then(r => r.json())
      .then(r => setData(r.data))
  }, [lat, lng, tz])

  if (!data) return <p>Loading...</p>
  return (
    <div>
      <p>తిథి: {data.tithi.te} — {data.tithi.en}</p>
      <p>నక్షత్రం: {data.nakshatra.te} — {data.nakshatra.en}</p>
    </div>
  )
}
```

---

## Self-Hosting

Want to run your own instance? The entire app is open source under MIT.

```bash
# Clone the repository
git clone https://github.com/suhasatluri/telugu-panchangam-app

# Install dependencies
npm install

# Copy environment template
cp .env.example .env.local

# Add your own API keys to .env.local:
# OPENCAGE_API_KEY=your_key_here

# Run locally
npm run dev

# Deploy to your own Cloudflare account
npm run deploy
```

Full self-hosting guide in `DEPLOYMENT.md`.

---

*This API is free to use. If you build something with it, please consider contributing back — a GitHub star, a festival correction, or a translation improvement all help the community.*
