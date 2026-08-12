# Algorithm — Panchangam Calculation Methodology

> This document explains every calculation used in the Telugu Panchangam App.
> It is written for developers, traditional scholars, and anyone who wants to
> verify our methodology. All formulas are mathematically verifiable.

---

## Table of Contents

1. [Foundational Concepts](#foundational-concepts)
2. [Astronomical Foundation](#astronomical-foundation)
3. [Ayanamsa — The Sidereal Correction](#ayanamsa)
4. [The Five Panchanga Elements](#the-five-panchanga-elements)
   - [Tithi](#tithi)
   - [Nakshatra](#nakshatra)
   - [Yoga](#yoga)
   - [Karana](#karana)
   - [Vara](#vara)
5. [Calendar Context](#calendar-context)
   - [Samvatsaram](#samvatsaram)
   - [Masa](#masa)
   - [Paksha](#paksha)
   - [Ritu](#ritu)
   - [Ayana](#ayana)
6. [Celestial Timings](#celestial-timings)
7. [Inauspicious Periods](#inauspicious-periods)
8. [Festival Calculation](#festival-calculation)
9. [Nakshatra Finder](#nakshatra-finder)
10. [Validation Reference](#validation-reference)

---

## Foundational Concepts

### What is a Panchangam?

*Panchanga* (పంచాంగం) means **five limbs** in Sanskrit:

| # | Name | Telugu | Meaning |
|---|---|---|---|
| 1 | Tithi | తిథి | Lunar day — phase of the moon |
| 2 | Vara | వారం | Weekday |
| 3 | Nakshatra | నక్షత్రం | Lunar mansion — star the moon is in |
| 4 | Yoga | యోగం | Combined position of Sun and Moon |
| 5 | Karana | కరణం | Half of a Tithi |

All five are calculated from the **positions of the Sun and Moon** at the time of local sunrise on a given day. The Panchangam day runs from **sunrise to sunrise** — not midnight to midnight as in the Gregorian calendar.

### The Indian Day (Vara)

A Vedic day (Vara) begins at sunrise and ends at the next sunrise. This is critical:

```
Gregorian:   Jan 1 00:00 ──────── Jan 1 23:59 ── Jan 2 00:00 ...
Vedic:              Jan 1 sunrise ────────────── Jan 2 sunrise ...

Consequence: A Tithi that starts at 2 AM Gregorian belongs to the PREVIOUS
             Vedic day, because sunrise has not yet occurred.
```

### Tropical vs Sidereal Astronomy

Western astronomy uses the **tropical zodiac** — positions relative to the vernal equinox (the point where the Sun crosses the celestial equator in spring).

Indian astronomy uses the **sidereal zodiac** — positions relative to fixed stars (Nakshatras). The difference is the **Ayanamsa** — approximately 24° currently, growing at ~50.3 arcseconds per year.

```
Sidereal longitude = Tropical longitude − Ayanamsa
```

All positions in this app are **sidereal (nirayana)** after Lahiri Ayanamsa correction.

---

## Astronomical Foundation

### Julian Day Number

All calculations use the **Julian Day Number (JDN)** — a continuous count of days since January 1, 4713 BCE. This avoids the complexities of calendar systems across unlimited years.

```typescript
// Julian Day for noon UTC on a Gregorian date
function gregorianToJulianDay(year: number, month: number, day: number): number {
  const a = Math.floor((14 - month) / 12)
  const y = year + 4800 - a
  const m = month + 12 * a - 3
  return day + Math.floor((153 * m + 2) / 5) + 365 * y
    + Math.floor(y / 4) - Math.floor(y / 100)
    + Math.floor(y / 400) - 32045
}
```

### Sun and Moon Longitudes

We use **VSOP87** (Variations Séculaires des Orbites Planétaires, 1987) — the standard algorithm for planetary positions developed by Pierre Bretagnon and Gerard Francou at the Bureau des Longitudes, Paris.

### Why This App Has No Date Limit

VSOP87 is a set of mathematical series expansions describing planetary orbital motion. It has no concept of a "supported range" — it is pure mathematics that evaluates at any point in time. The series terms cover planetary positions to ±0.001° accuracy.

The Julian Day Number system, which underpins all our date calculations, counts continuously from **January 1, 4713 BCE** with no upper bound.

This means:

```
Any date in human history    → calculable
Any date in the future       → calculable
Ancient festival dates       → calculable (e.g. when did Ugadi fall in 500 CE?)
Genealogical research        → calculable (ancestor's birth Tithi in 1847)
Far future planning          → calculable (Ugadi in 2400)
```

**There is no imposed upper or lower year limit in this application.**

The only practical caveats are:

1. **Timezone data before ~1900** — IANA timezone history becomes sparse before 1900. For historical dates before 1900, sunrise calculations are astronomically accurate but local clock time may be uncertain. The app shows a soft notice for pre-1900 dates.

2. **Gregorian calendar adoption** — The Gregorian calendar was adopted on October 15, 1582. Dates before this were in the Julian calendar. The app uses the **proleptic Gregorian calendar** (extending Gregorian rules backwards) for consistency, which is standard practice in astronomical calculation.

3. **Library validation** — `@ishubhamx/panchangam-js` was tested against modern Panchangam data. The underlying VSOP87 math works for any date, but users researching very ancient dates should cross-reference against other sources.

The fundamental principle: **the sky has no expiry date, and neither does this app.**

The `@ishubhamx/panchangam-js` library implements VSOP87. We call it as:

```typescript
import { getPanchangam, Observer } from '@ishubhamx/panchangam-js'

const observer = new Observer(lat, lng, elevation)
const result = getPanchangam(new Date(dateString), observer, { timezoneOffset })

// result.sunLongitude  → tropical solar longitude in degrees
// result.moonLongitude → tropical lunar longitude in degrees
```

---

## Ayanamsa

The **Lahiri (Chitrapaksha) Ayanamsa** is the standard used by the Government of India, the Rashtriya Panchang, and all Telugu Panchangam publishers including Venkatrama & Co.

### Formula

```
Ayanamsa(year) = 23°15′00″ + (year − 285) × 50.3″
               converted to decimal degrees
```

At January 1, 2026:
```
Ayanamsa ≈ 23.25° + (2026 − 285) × (50.3 / 3600)°
         ≈ 23.25° + 1741 × 0.01397°
         ≈ 23.25° + 24.32°
         ≈ 23.92° (approximately 23°55′)
```

The library handles this automatically. We verify its output matches the Rashtriya Panchang published value for spot-check dates.

### Why Lahiri only?

Other ayanamsa systems (Raman, KP, True Chitra) exist but give different results for Nakshatra boundaries. We use Lahiri exclusively because:

1. It is the standard for all Telugu Panchangam publishers
2. It matches our Venkatrama validation data
3. Multiple ayanamsa options would confuse community users

---

## The Five Panchanga Elements

### Tithi

**Definition:** The time taken for the Moon's longitude to increase by 12° relative to the Sun.

```
Tithi number = floor((Moon longitude − Sun longitude) / 12°) + 1

If Moon lon < Sun lon, add 360° before subtracting.
Result is 1–30 (30 Tithis per lunar month)
```

**30 Tithis:**

| # | Name | Telugu | Paksha |
|---|---|---|---|
| 1 | Pratipada / Paadyami | పాడ్యమి | Shukla |
| 2 | Dwitiya / Vidiya | విదియ | Shukla |
| 3 | Tritiya / Tadiya | తదియ | Shukla |
| 4 | Chaturthi / Chavithi | చవితి | Shukla |
| 5 | Panchami | పంచమి | Shukla |
| 6 | Shashthi / Shashti | షష్టి | Shukla |
| 7 | Saptami | సప్తమి | Shukla |
| 8 | Ashtami | అష్టమి | Shukla |
| 9 | Navami | నవమి | Shukla |
| 10 | Dashami | దశమి | Shukla |
| 11 | Ekadashi | ఏకాదశి | Shukla |
| 12 | Dwadashi | ద్వాదశి | Shukla |
| 13 | Trayodashi | త్రయోదశి | Shukla |
| 14 | Chaturdashi | చతుర్దశి | Shukla |
| 15 | Purnima (Full Moon) | పౌర్ణమి | Shukla |
| 16 | Pratipada / Paadyami | పాడ్యమి | Krishna |
| 17 | Dwitiya / Vidiya | విదియ | Krishna |
| 18 | Tritiya / Tadiya | తదియ | Krishna |
| 19 | Chaturthi / Chavithi | చవితి | Krishna |
| 20 | Panchami | పంచమి | Krishna |
| 21 | Shashthi / Shashti | షష్టి | Krishna |
| 22 | Saptami | సప్తమి | Krishna |
| 23 | Ashtami | అష్టమి | Krishna |
| 24 | Navami | నవమి | Krishna |
| 25 | Dashami | దశమి | Krishna |
| 26 | Ekadashi | ఏకాదశి | Krishna |
| 27 | Dwadashi | ద్వాదశి | Krishna |
| 28 | Trayodashi | త్రయోదశి | Krishna |
| 29 | Chaturdashi | చతుర్దశి | Krishna |
| 30 | Amavasya (New Moon) | అమావాస్య | Krishna |

**Tithi duration varies** from 19 to 26 hours depending on the Moon's speed in its elliptical orbit. A Tithi may:
- Span two Gregorian days (common)
- Begin and end within one Gregorian day (rare)
- Be skipped entirely (Kshaya Tithi — very rare, especially at high latitudes)
- Occur twice in a Gregorian day (Vriddhi Tithi)

**End time calculation:**

```typescript
// Find when (Moon lon - Sun lon) next crosses the next multiple of 12°
// Binary search between current time and next sunrise
// Precision target: ±1 minute
```

---

### Nakshatra

**Definition:** The lunar mansion — one of 27 equal segments of the ecliptic, each 13°20′ (800′).

```
Nakshatra number = floor(Moon sidereal longitude / 13.333°) + 1
Result is 1–27
```

**27 Nakshatras:**

| # | Name | Telugu | Deity | Pada boundary |
|---|---|---|---|---|
| 1 | Ashwini | అశ్వని | Ashwins | 0°–13°20′ Aries |
| 2 | Bharani | భరణి | Yama | 13°20′–26°40′ Aries |
| 3 | Krittika | కృత్తిక | Agni | 26°40′ Aries–10° Taurus |
| 4 | Rohini | రోహిణి | Brahma | 10°–23°20′ Taurus |
| 5 | Mrigashira | మృగశిర | Soma | 23°20′ Taurus–6°40′ Gemini |
| 6 | Ardra | ఆర్ద్ర | Rudra | 6°40′–20° Gemini |
| 7 | Punarvasu | పునర్వసు | Aditi | 20° Gemini–3°20′ Cancer |
| 8 | Pushya | పుష్యమి | Brihaspati | 3°20′–16°40′ Cancer |
| 9 | Ashlesha | ఆశ్లేష | Nagas | 16°40′–30° Cancer |
| 10 | Magha | మఖ | Pitrs | 0°–13°20′ Leo |
| 11 | Purva Phalguni | పూర్వఫల్గుణి | Bhaga | 13°20′–26°40′ Leo |
| 12 | Uttara Phalguni | ఉత్తరఫల్గుణి | Aryaman | 26°40′ Leo–10° Virgo |
| 13 | Hasta | హస్త | Savitar | 10°–23°20′ Virgo |
| 14 | Chitra | చిత్ర | Tvashtr | 23°20′ Virgo–6°40′ Libra |
| 15 | Swati | స్వాతి | Vayu | 6°40′–20° Libra |
| 16 | Vishakha | విశాఖ | Indra-Agni | 20° Libra–3°20′ Scorpio |
| 17 | Anuradha | అనూరాధ | Mitra | 3°20′–16°40′ Scorpio |
| 18 | Jyeshtha | జ్యేష్ఠ | Indra | 16°40′–30° Scorpio |
| 19 | Mula | మూల | Nirrti | 0°–13°20′ Sagittarius |
| 20 | Purva Ashadha | పూర్వాషాఢ | Apas | 13°20′–26°40′ Sagittarius |
| 21 | Uttara Ashadha | ఉత్తరాషాఢ | Vishvedeva | 26°40′ Sag–10° Capricorn |
| 22 | Shravana | శ్రవణ | Vishnu | 10°–23°20′ Capricorn |
| 23 | Dhanishtha | ధనిష్ఠ | Ashta Vasus | 23°20′ Cap–6°40′ Aquarius |
| 24 | Shatabhisha | శతభిష | Varuna | 6°40′–20° Aquarius |
| 25 | Purva Bhadrapada | పూర్వభాద్ర | Ajaikapat | 20° Aqu–3°20′ Pisces |
| 26 | Uttara Bhadrapada | ఉత్తరభాద్ర | Ahirbudhnya | 3°20′–16°40′ Pisces |
| 27 | Revati | రేవతి | Pushan | 16°40′–30° Pisces |

**Pada (quarter):** Each Nakshatra is divided into 4 Padas of 3°20′ each. Total: 108 Padas = 108 beads on a mala.

```
Pada = floor((Moon lon mod 13.333°) / 3.333°) + 1
```

---

### Yoga

**Definition:** One of 27 divisions of the sum of Sun and Moon longitudes.

```
Yoga number = floor((Sun sidereal lon + Moon sidereal lon) / 13.333°) + 1
If sum > 360°, subtract 360° first.
Result is 1–27
```

**27 Yogas (auspicious/inauspicious classification):**

| # | Name | Telugu | Nature |
|---|---|---|---|
| 1 | Vishkambha | విష్కంభ | Inauspicious |
| 2 | Priti | ప్రీతి | Auspicious |
| 3 | Ayushman | ఆయుష్మాన్ | Auspicious |
| 4 | Saubhagya | సౌభాగ్య | Auspicious |
| 5 | Shobhana | శోభన | Auspicious |
| 6 | Atiganda | అతిగండ | Inauspicious |
| 7 | Sukarma | సుకర్మ | Auspicious |
| 8 | Dhriti | ధ్రుతి | Auspicious |
| 9 | Shula | శూల | Inauspicious |
| 10 | Ganda | గండ | Inauspicious |
| 11 | Vriddhi | వృద్ధి | Auspicious |
| 12 | Dhruva | ధ్రువ | Auspicious |
| 13 | Vyaghata | వ్యాఘాత | Inauspicious |
| 14 | Harshana | హర్షణ | Auspicious |
| 15 | Vajra | వజ్ర | Inauspicious |
| 16 | Siddhi | సిద్ధి | Auspicious |
| 17 | Vyatipata | వ్యతీపాత | Highly Inauspicious |
| 18 | Variyana | వరీయాన్ | Auspicious |
| 19 | Parigha | పరిఘ | Inauspicious |
| 20 | Shiva | శివ | Auspicious |
| 21 | Siddha | సిద్ధ | Auspicious |
| 22 | Sadhya | సాధ్య | Auspicious |
| 23 | Shubha | శుభ | Auspicious |
| 24 | Shukla | శుక్ల | Auspicious |
| 25 | Brahma | బ్రహ్మ | Auspicious |
| 26 | Aindra | ఐంద్ర | Auspicious |
| 27 | Vaidhriti | వైధృతి | Highly Inauspicious |

---

### Karana

**Definition:** Half of a Tithi. Two Karanas per Tithi = 60 Karanas per lunar month.

```
Karana number = floor((Moon lon − Sun lon) / 6°) mod 60 + 1
```

**11 Karanas (4 fixed + 7 movable):**

Fixed (occur once per month):
| Name | Telugu | When |
|---|---|---|
| Shakuni | శకుని | 2nd half of Krishna Chaturdashi |
| Chatushpada | చతుష్పాద | 1st half of Amavasya |
| Naga | నాగ | 2nd half of Amavasya |
| Kimstughna | కింస్తుఘ్న | 1st half of Shukla Pratipada |

Movable (repeat 8 times each in a month):
| # | Name | Telugu |
|---|---|---|
| 1 | Bava | బవ |
| 2 | Balava | బాలవ |
| 3 | Kaulava | కౌలవ |
| 4 | Taitila | తైతిల |
| 5 | Garija | గరజ |
| 6 | Vanija | వణిజ |
| 7 | Vishti (Bhadra) | విష్టి (భద్ర) |

**Note:** Vishti (Bhadra) Karana is considered highly inauspicious for auspicious activities. The app marks it clearly.

---

### Vara

**Definition:** The weekday, named after the ruling planet.

```
vara = julianDayNumber mod 7
```

| # | Name | Telugu | Planet |
|---|---|---|---|
| 0 | Ravivara (Sunday) | ఆదివారం | Sun (Ravi) |
| 1 | Somavara (Monday) | సోమవారం | Moon (Soma) |
| 2 | Mangalavara (Tuesday) | మంగళవారం | Mars (Mangala) |
| 3 | Budhavara (Wednesday) | బుధవారం | Mercury (Budha) |
| 4 | Guruvara (Thursday) | గురువారం | Jupiter (Guru) |
| 5 | Shukravara (Friday) | శుక్రవారం | Venus (Shukra) |
| 6 | Shanivara (Saturday) | శనివారం | Saturn (Shani) |

---

## Calendar Context

### Samvatsaram

The **60-year Jupiter cycle** (Brihaspati Mana). Jupiter takes ~11.86 years to orbit the Sun. In the Indian calendar, 60 solar years correspond almost exactly to 5 Jupiter orbits.

```
Samvatsara number = (year − epoch_year) mod 60
```

The current epoch starts from a traditional reference point. The Venkatrama calendar confirms:
- 2025–2026: **Viswavasu** (59th)
- 2026–2027: **Parabhava** (60th — last in cycle)
- 2027–2028: **Plavanga** (1st — cycle restarts)

**60 Samvatsara names** (stored in `src/data/samvatsaram.json`):

Prabhava, Vibhava, Shukla, Pramoda, Prajapati, Angirasa, Shrimukha, Bhava, Yuva, Dhatru, Ishvara, Bahudhanya, Pramathi, Vikrama, Vrusha, Chitrabhanu, Svabhanu, Tarana, Parthiva, Vyaya, Sarvajit, Sarvadhari, Virodhi, Vikrita, Khara, Nandana, Vijaya, Jaya, Manmatha, Durmukhi, Hevilambi, Vilambi, Vikari, Sharvari, Plava, Shubhakruta, Shobhakruta, Krodhi, Vishvavasu, Parabhava, Plavanga, Keelaka, Saumya, Sadharana, Virodhikruta, Paridhavi, Pramadicha, Ananda, Rakshasa, Nala, Pingala, Kalayukti, Siddharthi, Raudra, Durmathi, Dundubhi, Rudhirodgari, Raktakshi, Krodhana, Akshaya.

### Masa

The **Telugu lunar month** uses the **Amanta system** — a month runs from new moon (Amavasya) to the next new moon. This is the standard in Andhra Pradesh and Telangana (the Purnimanta system used in North India runs full moon to full moon).

```
Masa is determined by which Rashi the Sun occupies at the new moon
```

**12 Telugu Months:**

| # | Name | Telugu | Approx. Gregorian |
|---|---|---|---|
| 1 | Chaitra | చైత్రం | Mar–Apr |
| 2 | Vaisakha | వైశాఖం | Apr–May |
| 3 | Jyeshtha | జ్యేష్ఠం | May–Jun |
| 4 | Ashadha | ఆషాఢం | Jun–Jul |
| 5 | Shravana | శ్రావణం | Jul–Aug |
| 6 | Bhadrapada | భాద్రపదం | Aug–Sep |
| 7 | Ashvina | ఆశ్వీయుజం | Sep–Oct |
| 8 | Kartika | కార్తీకం | Oct–Nov |
| 9 | Margashirsha | మార్గశిరం | Nov–Dec |
| 10 | Pushya | పుష్యం | Dec–Jan |
| 11 | Magha | మాఘం | Jan–Feb |
| 12 | Phalguna | ఫాల్గుణం | Feb–Mar |

**Adhika Masa (Intercalary Month):** When two new moons fall within the same solar month (Sun in same Rashi), an extra month is inserted. Occurs approximately every 2.5–3 years. The repeated month is called Adhika (extra) — e.g., Adhika Ashadha.

### Paksha

```
Shukla Paksha: Tithis 1–15 (New Moon to Full Moon — waxing)
Krishna Paksha: Tithis 16–30 (Full Moon to New Moon — waning)
```

### Ritu (Season)

**6 Seasons of the Indian calendar:**

| # | Name | Telugu | Months |
|---|---|---|---|
| 1 | Vasanta (Spring) | వసంత | Chaitra–Vaisakha |
| 2 | Grishma (Summer) | గ్రీష్మ | Jyeshtha–Ashadha |
| 3 | Varsha (Monsoon) | వర్ష | Shravana–Bhadrapada |
| 4 | Sharada (Autumn) | శరద్ | Ashvina–Kartika |
| 5 | Hemanta (Winter) | హేమంత | Margashirsha–Pushya |
| 6 | Shishira (Late Winter) | శిశిర | Magha–Phalguna |

### Ayana (Solstice Period)

```
Uttarayana (Sun moves north): Makara Sankranti to Karka Sankranti (Jan–Jul)
Dakshinayana (Sun moves south): Karka Sankranti to Makara Sankranti (Jul–Jan)
```

---

## Celestial Timings

All celestial timings use the **SunCalc** library, which implements established algorithms for solar and lunar position.

```typescript
import SunCalc from 'suncalc'

const times = SunCalc.getTimes(date, lat, lng)
// times.sunrise  → Date object (UTC)
// times.sunset   → Date object (UTC)

const moonTimes = SunCalc.getMoonTimes(date, lat, lng)
// moonTimes.rise → Date object (UTC)
// moonTimes.set  → Date object (UTC)

const moonIllum = SunCalc.getMoonIllumination(date)
// moonIllum.fraction → 0.0 to 1.0 (0% to 100%)
// moonIllum.phase    → 0.0 to 1.0 (0 = new, 0.5 = full)
```

All times are converted from UTC to the local timezone using `date-fns-tz`.

---

## Inauspicious Periods

### Rahukalam, Gulika Kalam, Yamagandam

These are **not astronomical calculations** — they are traditional time divisions based on the weekday and local sunrise.

**Method:**
1. Calculate actual local sunrise and sunset times
2. Divide the daylight period into 8 equal slots
3. Each weekday assigns specific slots to each period

```
Slot duration = (Sunset − Sunrise) / 8

Slot 1: Sunrise + (0 × slot_duration) to Sunrise + (1 × slot_duration)
Slot 2: Sunrise + (1 × slot_duration) to Sunrise + (2 × slot_duration)
...
Slot 8: Sunrise + (7 × slot_duration) to Sunrise + (8 × slot_duration) = Sunset
```

**Weekday → Slot Assignments:**

| Day | Rahukalam | Gulika | Yamagandam |
|---|---|---|---|
| Sunday | 8th | 3rd | 1st |
| Monday | 2nd | 1st | 5th |
| Tuesday | 7th | 6th | 4th |
| Wednesday | 5th | 7th | 3rd |
| Thursday | 6th | 5th | 2nd |
| Friday | 3rd | 4th | 6th |
| Saturday | 1st | 2nd | 7th |

**Example — Monday, Melbourne:**
```
Sunrise: 07:32, Sunset: 19:45
Daylight: 12h 13min = 733 minutes
Slot duration: 733 / 8 = 91.6 minutes ≈ 1h 31m 36s

Rahukalam (2nd slot): 07:32 + 91.6min = 09:03 to 07:32 + 183.2min = 10:35
```

Note: Traditional charts list approximate times (e.g. "7:30 to 9:00") based on a fixed 6:00 AM sunrise. We use the *actual* local sunrise for accuracy, which is why our timings may differ slightly from printed calendars calculated for India.

---

## Festival Calculation

Festivals are calculated using two methods:

### Method 1: Algorithmic (Tithi-based)

Festivals defined by their Tithi, Masa, and Paksha. Calculated for any year.

```typescript
// Example: Ugadi
{
  name: { te: 'ఉగాది', en: 'Ugadi' },
  rule: { masa: 'Chaitra', paksha: 'Shukla', tithi: 1 }
}
// Find the date when Shukla Pratipada of Chaitra occurs at sunrise
```

**Tier 1 Festivals (all algorithmic):**

| Festival | Rule |
|---|---|
| Ugadi | Chaitra Shukla Pratipada |
| Sri Rama Navami | Chaitra Shukla Navami |
| Hanuman Jayanti | Chaitra Purnima |
| Varalakshmi Vratam | Friday before Shravana Purnima |
| Krishna Ashtami | Shravana Krishna Ashtami |
| Vinayaka Chaturthi | Bhadrapada Shukla Chaturthi |
| Vijayadasami | Ashvina Shukla Dasami |
| Deepavali | Kartika Amavasya |
| Karthika Purnima | Kartika Purnima |
| Maha Sivaratri | Magha Krishna Chaturdashi |
| Holi | Phalguna Purnima |
| All Ekadashi | Shukla 11 and Krishna 11 each month |
| All Amavasya | Each month |
| All Purnima | Each month |

### Method 2: Solar (Sankranti)

Makara Sankranti = the moment the Sun enters Capricorn (Makara Rashi).

```typescript
// Binary search for the moment Sun longitude crosses 270° (Makara entry)
// This gives the precise moment — the festival is the calendar day of this moment
// Bhogi = day before Sankranti
// Kanuma = day after Sankranti
```

### Method 3: Lookup Table

Regional festivals with complex rules stored in `src/data/festivals.json`:
- Bathukamma (9-day period in Bhadrapada)
- Bonalu (Ashadha/Shravana, Hyderabad specific)
- National holidays (fixed Gregorian dates)

---

## Nakshatra Finder

This feature identifies a person's **Janma Nakshatra** (birth star) from their birth date, time, and place.

```
Janma Nakshatra = Nakshatra the Moon occupied at the moment of birth
```

The calculation is identical to the daily Nakshatra calculation, except instead of using the sunrise time of the birth date, we use the **exact birth time and birth location**.

```typescript
function getJanmaNakshatra(
  birthDate: Date,
  birthLat: number,
  birthLng: number
): { nakshatra: NakshatraName; pada: 1 | 2 | 3 | 4; raasi: RaasiName }
```

**Tarabalam:** The relationship between today's Nakshatra and a person's Janma Nakshatra. Calculated by counting Nakshatras from the Janma Nakshatra to today's Nakshatra (cyclically).

```
tara = ((today_nakshatra_number - janma_nakshatra_number + 27) mod 27) + 1

Tara 1: Janma — Neutral
Tara 2: Sampat — Auspicious
Tara 3: Vipat — Inauspicious
Tara 4: Kshema — Auspicious
Tara 5: Pratyak — Inauspicious
Tara 6: Sadhana — Auspicious
Tara 7: Naidhana — Highly Inauspicious
Tara 8: Mitra — Auspicious
Tara 9: Parama Mitra — Highly Auspicious
```

**Important disclaimer shown in app:**
> "Nakshatra is calculated from the Moon's position at birth. This is time-based astronomy. The accuracy depends on the precision of the birth time provided. No predictive content is generated."

---

## Validation Reference

Our implementation is validated against the **Venkatrama & Co. 2026 printed calendar** (Eluru, Andhra Pradesh).

### Spot-check Assertions

```typescript
// From validation/regression.test.ts

// Ugadi 2026
expect(getPanchangam('2026-03-19', hyderabad)).toMatchObject({
  samvatsaram: { en: 'Parabhava' },  // New year starts
  tithi: { en: 'Pratipada' },
  paksha: 'shukla',
  masa: { en: 'Chaitra' }
})

// Maha Sivaratri 2026
expect(getPanchangam('2026-02-15', hyderabad)).toMatchObject({
  tithi: { en: 'Chaturdashi' },
  paksha: 'krishna',
  masa: { en: 'Magha' }
})

// Rahukalam on a Monday in Melbourne
const monday = getPanchangam('2026-03-23', melbourne)
expect(monday.rahukalam.start).toBe('08:02') // 2nd slot from sunrise 07:32
```

### Known Differences from Printed Calendars

1. **Rahukalam times** — We use actual local sunrise. Printed calendars often use a fixed 6:00 AM. Our times will differ by 1–2 hours for cities like Melbourne (sunrise at 7:30 AM).

2. **Tithi transitions near midnight** — When a Tithi ends between midnight and sunrise, the printed calendar shows the next Tithi. We show the Tithi at sunrise (correct per Vedic convention).

3. **Timezone** — All times shown in local city time. Printed Indian calendars use IST. A festival may fall on a different Gregorian date in Australia than in India.

---

*This document is the authoritative specification for the Telugu Panchangam calculation engine. For implementation questions, see the source code in `src/engine/`. For validation data, see `validation/`.*
