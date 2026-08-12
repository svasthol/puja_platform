import { calculateDayPanchangam } from "./panchangam";
import type { Festival, Location } from "./types";
import { getSignificantEkadashi } from "./significantEkadashis";

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

/** Add days to a YYYY-MM-DD string */
function addDays(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days);
  const ny = dt.getFullYear();
  const nm = String(dt.getMonth() + 1).padStart(2, "0");
  const nd = String(dt.getDate()).padStart(2, "0");
  return `${ny}-${nm}-${nd}`;
}

/** Format YYYY-MM-DD */
function fmtDate(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** Get weekday (0=Sun) for a date string */
function getWeekday(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).getDay();
}

// ─────────────────────────────────────────────
// Tier 3 — Fixed Gregorian holidays
// ─────────────────────────────────────────────

function getFixedFestivals(year: number): Festival[] {
  return [
    {
      date: fmtDate(year, 1, 26),
      te: "గణతంత్ర దినోత్సవం",
      en: "Republic Day",
      type: "fixed",
      tier: 3,
    },
    {
      date: fmtDate(year, 6, 2),
      te: "తెలంగాణ అవతరణ దినం",
      en: "Telangana Formation Day",
      type: "fixed",
      tier: 3,
    },
    {
      date: fmtDate(year, 8, 15),
      te: "స్వాతంత్ర్య దినోత్సవం",
      en: "Independence Day",
      type: "fixed",
      tier: 3,
    },
    {
      date: fmtDate(year, 10, 2),
      te: "గాంధీ జయంతి",
      en: "Gandhi Jayanti",
      type: "fixed",
      tier: 3,
    },
    {
      date: fmtDate(year, 11, 1),
      te: "ఆంధ్రప్రదేశ్ అవతరణ దినం",
      en: "AP Formation Day",
      type: "fixed",
      tier: 3,
    },
    {
      date: fmtDate(year, 12, 25),
      te: "క్రిస్మస్",
      en: "Christmas",
      type: "fixed",
      tier: 3,
    },
  ];
}

// ─────────────────────────────────────────────
// Lunar festival matching rules
// ─────────────────────────────────────────────

interface LunarRule {
  masa: number; // 1=Chaitra .. 12=Phalguna
  tithi: number; // 1-30 (absolute: 1-15 shukla, 16-30 krishna)
  te: string;
  en: string;
  tier: 1 | 2;
  isHighlight?: boolean;
  /** If set, also match when nextTithi equals this tithi and sunrise tithi = prevTithi */
  matchNextTithi?: boolean;
  prevTithi?: number;
  /** For masa-boundary festivals (Ugadi), the sunrise masa to check instead */
  prevMasa?: number;
}

/**
 * Lunar festival rules — masa + tithi to match.
 * Tithi numbering: 1=Shukla Pratipada .. 15=Purnima, 16=Krishna Pratipada .. 30=Amavasya
 *
 * Some festivals use matchNextTithi because the traditional observance date is
 * the day when the target tithi begins during the day (not necessarily at sunrise).
 */
const LUNAR_RULES: LunarRule[] = [
  // ── Chaitra (1) ──
  // Ugadi: observed on the day Pratipada begins (sunrise tithi may be Phalguna Amavasya)
  { masa: 1, tithi: 1, te: "ఉగాది", en: "Ugadi", tier: 1, isHighlight: true, matchNextTithi: true, prevTithi: 30, prevMasa: 12 },
  { masa: 1, tithi: 9, te: "శ్రీ రామ నవమి", en: "Sri Rama Navami", tier: 1, isHighlight: true },
  { masa: 1, tithi: 15, te: "హనుమాన్ జయంతి", en: "Hanuman Jayanti", tier: 1 },

  // ── Vaisakha (2) ──
  { masa: 2, tithi: 3, te: "అక్షయ తృతీయ", en: "Akshaya Tritiya", tier: 1 },

  // ── Ashadha (4) ──
  { masa: 4, tithi: 11, te: "ఆషాఢ శుక్ల ఏకాదశి (తొలి)", en: "Ashadha Shukla Ekadashi (Toli)", tier: 2 },

  // ── Shravana (5) ──
  { masa: 5, tithi: 23, te: "శ్రీ కృష్ణ జన్మాష్టమి", en: "Krishna Janmashtami", tier: 1, isHighlight: true },

  // ── Bhadrapada (6) ──
  { masa: 6, tithi: 4, te: "వినాయక చవితి", en: "Vinayaka Chaturthi", tier: 1, isHighlight: true },

  // ── Ashvina (7) ──
  { masa: 7, tithi: 10, te: "విజయదశమి", en: "Vijayadasami", tier: 1, isHighlight: true },

  // ── Kartika (8) ──
  { masa: 8, tithi: 30, te: "దీపావళి", en: "Deepavali", tier: 1, isHighlight: true },
  { masa: 8, tithi: 15, te: "కార్తీక పౌర్ణమి", en: "Karthika Purnima", tier: 1 },
  { masa: 8, tithi: 4, te: "నాగుల చవితి", en: "Nagula Chavithi", tier: 2 },

  // ── Magha (11) ──
  // Sivaratri: observed on the night when Chaturdashi prevails (sunrise tithi = Trayodashi)
  { masa: 11, tithi: 29, te: "మహా శివరాత్రి", en: "Maha Sivaratri", tier: 1, isHighlight: true, matchNextTithi: true, prevTithi: 28 },

  // ── Phalguna (12) ──
  { masa: 12, tithi: 15, te: "హోలీ", en: "Holi", tier: 1 },
];

// ─────────────────────────────────────────────
// Makara Sankranti (Solar — Sun enters Capricorn)
// ─────────────────────────────────────────────

/**
 * Makara Sankranti is when the Sun enters sidereal Capricorn (Makara).
 * This typically falls on January 14 or 15. We check Jan 13-16 and
 * pick the day where Sun longitude crosses 270 degrees (Lahiri ayanamsa adjusted).
 *
 * For simplicity and reliability, we use the well-known pattern:
 * Sankranti is Jan 14 in most years, Jan 15 in some leap-adjacent years.
 * We verify by checking the panchangam's ayana field shift.
 */
function getSankrantiFestivals(year: number, location: Location): Festival[] {
  const festivals: Festival[] = [];

  // Sankranti is almost always Jan 14; occasionally Jan 15
  // Check both days and pick the one where Uttarayana begins
  let sankrantiDate = fmtDate(year, 1, 14);

  // Verify by checking if ayana is Uttarayana on the 14th
  try {
    const p14 = calculateDayPanchangam(fmtDate(year, 1, 14), location);
    const p13 = calculateDayPanchangam(fmtDate(year, 1, 13), location);

    // If ayana changed between 13th and 14th, Sankranti is on 14th
    // If not, check 15th
    if (p14.ayana.en === p13.ayana.en) {
      const p15 = calculateDayPanchangam(fmtDate(year, 1, 15), location);
      if (p15.ayana.en !== p14.ayana.en) {
        sankrantiDate = fmtDate(year, 1, 15);
      }
    }
  } catch {
    // Fallback to Jan 14
  }

  const bhogiDate = addDays(sankrantiDate, -1);
  const kanumaDate = addDays(sankrantiDate, 1);

  festivals.push(
    {
      date: bhogiDate,
      te: "భోగి",
      en: "Bhogi",
      type: "solar",
      tier: 1,
    },
    {
      date: sankrantiDate,
      te: "మకర సంక్రాంతి",
      en: "Makara Sankranti",
      type: "solar",
      tier: 1,
      description: { en: "Sun enters Makara (Capricorn)" },
    },
    {
      date: kanumaDate,
      te: "కనుమ",
      en: "Kanuma",
      type: "solar",
      tier: 1,
    }
  );

  return festivals;
}

// ─────────────────────────────────────────────
// Varalakshmi Vratam — Friday before Shravana Purnima
// ─────────────────────────────────────────────

function findVaralakshmiVratam(
  year: number,
  location: Location,
  dayMap: Map<string, ReturnType<typeof calculateDayPanchangam>>
): Festival | null {
  // Find Shravana Purnima first — Masa 5, Tithi 15
  let purnimaDate: string | null = null;

  for (const [date, p] of Array.from(dayMap)) {
    if (p.masa.number === 5 && !p.masa.isAdhika && p.tithi.number === 15) {
      purnimaDate = date;
      break;
    }
  }

  if (!purnimaDate) return null;

  // Walk backwards to find the Friday before
  let candidate = addDays(purnimaDate, -1);
  for (let i = 0; i < 7; i++) {
    if (getWeekday(candidate) === 5) {
      // Friday
      return {
        date: candidate,
        te: "వరలక్ష్మీ వ్రతం",
        en: "Varalakshmi Vratam",
        type: "tithi",
        tier: 1,
      };
    }
    candidate = addDays(candidate, -1);
  }

  return null;
}

// ─────────────────────────────────────────────
// Bathukamma — 9 days from Bhadrapada Amavasya to Ashvina Dasami (approx)
// ─────────────────────────────────────────────

function findBathukamma(
  dayMap: Map<string, ReturnType<typeof calculateDayPanchangam>>
): Festival[] {
  const festivals: Festival[] = [];

  // Find Bhadrapada Amavasya (Masa 6, Tithi 30)
  let startDate: string | null = null;
  for (const [date, p] of Array.from(dayMap)) {
    if (p.masa.number === 6 && !p.masa.isAdhika && p.tithi.number === 30) {
      startDate = date;
      break;
    }
  }

  if (!startDate) return festivals;

  // Bathukamma starts next day (Ashvina Shukla Pratipada) and runs ~9 days
  const bathukammaStart = addDays(startDate, 1);
  festivals.push({
    date: bathukammaStart,
    te: "బతుకమ్మ ప్రారంభం",
    en: "Bathukamma Begins",
    type: "tithi",
    tier: 2,
    description: { en: "9-day Telangana flower festival" },
  });

  // Saddula Bathukamma is on the 9th day (Ashvina Shukla Navami, before Dasara)
  const saddula = addDays(bathukammaStart, 8);
  festivals.push({
    date: saddula,
    te: "సద్దుల బతుకమ్మ",
    en: "Saddula Bathukamma",
    type: "tithi",
    tier: 2,
  });

  return festivals;
}

// ─────────────────────────────────────────────
// Bonalu — First Sunday of Ashada masa
// ─────────────────────────────────────────────

function findBonalu(
  dayMap: Map<string, ReturnType<typeof calculateDayPanchangam>>
): Festival | null {
  // Find first day of Ashadha masa (4), then find the first Sunday
  for (const [date, p] of Array.from(dayMap)) {
    if (p.masa.number === 4 && !p.masa.isAdhika) {
      // Walk from this date to find the first Sunday
      let candidate = date;
      for (let i = 0; i < 35; i++) {
        const cp = dayMap.get(candidate);
        if (cp && cp.masa.number === 4 && getWeekday(candidate) === 0) {
          return {
            date: candidate,
            te: "బోనాలు",
            en: "Bonalu",
            type: "tithi",
            tier: 2,
            description: { en: "Telangana festival honouring Mahakali" },
          };
        }
        candidate = addDays(candidate, 1);
      }
      break;
    }
  }
  return null;
}

// ─────────────────────────────────────────────
// Karthika Somavaram — every Monday in Kartika masa
// ─────────────────────────────────────────────

function findKarthikaSomavaralu(
  dayMap: Map<string, ReturnType<typeof calculateDayPanchangam>>
): Festival[] {
  const festivals: Festival[] = [];
  let count = 0;

  for (const [date, p] of Array.from(dayMap)) {
    if (p.masa.number === 8 && !p.masa.isAdhika && getWeekday(date) === 1) {
      count++;
      festivals.push({
        date,
        te: `కార్తీక సోమవారం (${count})`,
        en: `Karthika Somavaram (${count})`,
        type: "tithi",
        tier: 2,
      });
    }
  }

  return festivals;
}

// ─────────────────────────────────────────────
// Recurring: Ekadashis, Amavasyas, Purnimas
// ─────────────────────────────────────────────

function getRecurringFestivals(
  dayMap: Map<string, ReturnType<typeof calculateDayPanchangam>>
): Festival[] {
  const festivals: Festival[] = [];
  const seenEkadashi = new Set<string>();
  const seenAmavasya = new Set<string>();
  const seenPurnima = new Set<string>();

  for (const [date, p] of Array.from(dayMap)) {
    // Ekadashi: tithi 11 (Shukla) or 26 (Krishna)
    if ((p.tithi.number === 11 || p.tithi.number === 26) && !seenEkadashi.has(date)) {
      seenEkadashi.add(date);
      const pakshaLabel = p.paksha.value === "shukla" ? "Shukla" : "Krishna";
      const significant = getSignificantEkadashi(p.masa.number, p.paksha.value);
      if (significant) {
        festivals.push({
          date,
          te: significant.te,
          en: significant.en,
          type: "tithi",
          tier: 1,
          isSignificantEkadashi: true,
          significance: significant.significance,
        });
      } else {
        festivals.push({
          date,
          te: `${p.masa.te} ${p.paksha.te.replace(" పక్షం", "")} ఏకాదశి`,
          en: `${p.masa.en} ${pakshaLabel} Ekadashi`,
          type: "tithi",
          tier: 2,
        });
      }
    }

    // Amavasya: tithi 30
    if (p.tithi.number === 30 && !seenAmavasya.has(date)) {
      seenAmavasya.add(date);
      festivals.push({
        date,
        te: `${p.masa.te} అమావాస్య`,
        en: `${p.masa.en} Amavasya`,
        type: "tithi",
        tier: 1,
      });
    }

    // Purnima: tithi 15
    if (p.tithi.number === 15 && !seenPurnima.has(date)) {
      seenPurnima.add(date);
      festivals.push({
        date,
        te: `${p.masa.te} పౌర్ణమి`,
        en: `${p.masa.en} Purnima`,
        type: "tithi",
        tier: 1,
      });
    }
  }

  return festivals;
}

// ─────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────

/**
 * Get all festivals for a given year at a specific location.
 * Walks through every day of the year, calculates panchangam,
 * and matches against festival rules.
 */
export function getFestivalsForYear(
  year: number,
  lat: number,
  lng: number,
  tz: string
): Festival[] {
  const location: Location = { lat, lng, tz };
  const festivals: Festival[] = [];

  // Build a map of date → panchangam for the entire year
  // We need a buffer before Jan 1 and after Dec 31 because
  // lunar months don't align with Gregorian months
  const startDate = fmtDate(year, 1, 1);
  const totalDays = isLeapYear(year) ? 366 : 365;

  const dayMap = new Map<string, ReturnType<typeof calculateDayPanchangam>>();
  let current = startDate;
  for (let i = 0; i < totalDays; i++) {
    try {
      dayMap.set(current, calculateDayPanchangam(current, location));
    } catch {
      // Skip days that fail calculation (shouldn't happen)
    }
    current = addDays(current, 1);
  }

  // 1. Fixed Gregorian holidays (Tier 3)
  festivals.push(...getFixedFestivals(year));

  // 2. Solar festivals (Sankranti cluster)
  festivals.push(...getSankrantiFestivals(year, location));

  // 3. Lunar festivals — match rules against dayMap
  const matchedFestivals = new Set<string>(); // prevent duplicate festival names
  for (const [date, p] of Array.from(dayMap)) {
    for (const rule of LUNAR_RULES) {
      if (matchedFestivals.has(rule.en)) continue;

      // Direct match: sunrise tithi matches
      const directMatch =
        p.masa.number === rule.masa &&
        !p.masa.isAdhika &&
        p.tithi.number === rule.tithi;

      // Next-tithi match: target tithi begins during this day
      let nextTithiMatch = false;
      if (rule.matchNextTithi && rule.prevTithi !== undefined) {
        const masaToCheck = rule.prevMasa ?? rule.masa;
        nextTithiMatch =
          p.masa.number === masaToCheck &&
          !p.masa.isAdhika &&
          p.tithi.number === rule.prevTithi &&
          p.tithi.nextTithi.number === rule.tithi;
      }

      if (directMatch || nextTithiMatch) {
        matchedFestivals.add(rule.en);
        festivals.push({
          date,
          te: rule.te,
          en: rule.en,
          type: "tithi",
          tier: rule.tier,
        });
      }
    }
  }

  // 4. Varalakshmi Vratam (special — Friday before Shravana Purnima)
  const varalakshmi = findVaralakshmiVratam(year, location, dayMap);
  if (varalakshmi) festivals.push(varalakshmi);

  // 5. Bathukamma (Telangana — 9 days)
  festivals.push(...findBathukamma(dayMap));

  // 6. Bonalu (first Sunday of Ashadha)
  const bonalu = findBonalu(dayMap);
  if (bonalu) festivals.push(bonalu);

  // 7. Karthika Somavaram (every Monday in Kartika)
  festivals.push(...findKarthikaSomavaralu(dayMap));

  // 8. Recurring: Ekadashis, Amavasyas, Purnimas
  festivals.push(...getRecurringFestivals(dayMap));

  // Sort by date
  festivals.sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));

  return festivals;
}

/**
 * Get festivals for a specific date from a pre-computed year list.
 */
export function getFestivalsForDate(
  dateStr: string,
  allFestivals: Festival[]
): Festival[] {
  return allFestivals.filter((f) => f.date === dateStr);
}

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}
