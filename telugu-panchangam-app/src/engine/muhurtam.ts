import { calculateDayPanchangam } from "./panchangam";
import type { Location, BilingualName } from "./types";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

export interface MuhurtamWindow {
  date: string;
  start: string; // ISO timestamp with tz offset
  end: string;
  durationMinutes: number;
  tithi: BilingualName;
  nakshatra: BilingualName;
  yoga: BilingualName;
  quality: "excellent" | "good" | "neutral";
  reason: string;
}

// ─────────────────────────────────────────────
// Auspicious classification sets
// ─────────────────────────────────────────────

/** Auspicious Nakshatras for Muhurtam */
const AUSPICIOUS_NAKSHATRAS = new Set([
  4,  // Rohini
  5,  // Mrigashira
  7,  // Punarvasu
  8,  // Pushya
  10, // Magha
  12, // Uttara Phalguni
  13, // Hasta
  14, // Chitra
  15, // Swati
  17, // Anuradha
  21, // Uttara Ashadha
  22, // Shravana
  23, // Dhanishtha
  24, // Shatabhisha
  26, // Uttara Bhadrapada
  27, // Revati
]);

/** Inauspicious Yoga numbers (1-indexed) */
const INAUSPICIOUS_YOGAS = new Set([
  1,  // Vishkambha
  6,  // Atiganda
  9,  // Shula
  10, // Ganda
  13, // Vyaghata
  15, // Vajra
  17, // Vyatipata
  19, // Parigha
  27, // Vaidhriti
]);

/** Avoided Tithis for auspicious events (1-indexed, absolute numbering) */
const AVOIDED_TITHIS = new Set([
  8,  // Shukla Ashtami
  14, // Shukla Chaturdashi
  15, // Purnima (sometimes avoided)
  23, // Krishna Ashtami
  29, // Krishna Chaturdashi
  30, // Amavasya
]);

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function addDays(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

/** Parse ISO time string to epoch ms */
function parseIsoMs(iso: string): number {
  return new Date(iso).getTime();
}

/** Check if two time ranges overlap */
function overlaps(
  s1: number, e1: number,
  s2: number, e2: number
): boolean {
  return s1 < e2 && e1 > s2;
}

/** Subtract a range from another, returning remaining segments */
function subtractRange(
  start: number,
  end: number,
  cutStart: number,
  cutEnd: number
): Array<[number, number]> {
  if (cutStart >= end || cutEnd <= start) return [[start, end]];
  const result: Array<[number, number]> = [];
  if (start < cutStart) result.push([start, cutStart]);
  if (cutEnd < end) result.push([cutEnd, end]);
  return result;
}

// ─────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────

/**
 * Find auspicious Muhurtam windows for a range of days.
 *
 * Strategy:
 * For each day, the "window" is sunrise to sunset (the auspicious daytime).
 * We classify the entire daytime based on the ruling Nakshatra, Yoga, and Tithi,
 * then carve out Rahukalam and Yamagandam to produce the clean windows.
 */
export function getMuhurtamWindows(
  fromDate: string,
  days: number,
  lat: number,
  lng: number,
  tz: string
): MuhurtamWindow[] {
  const location: Location = { lat, lng, tz };
  const windows: MuhurtamWindow[] = [];

  for (let i = 0; i < days; i++) {
    const dateStr = addDays(fromDate, i);

    let p;
    try {
      p = calculateDayPanchangam(dateStr, location);
    } catch {
      continue;
    }

    const nakshatraAuspicious = AUSPICIOUS_NAKSHATRAS.has(p.nakshatra.number);
    const yogaAuspicious = !INAUSPICIOUS_YOGAS.has(p.yoga.number);
    const tithiAvoided = AVOIDED_TITHIS.has(p.tithi.number);

    // Determine quality
    let quality: "excellent" | "good" | "neutral";
    const reasons: string[] = [];

    if (nakshatraAuspicious && yogaAuspicious && !tithiAvoided) {
      quality = "excellent";
      reasons.push(`${p.nakshatra.en} Nakshatra`);
      reasons.push(`${p.yoga.en} Yoga`);
      reasons.push(`${p.tithi.en} Tithi`);
    } else if ((nakshatraAuspicious || yogaAuspicious) && !tithiAvoided) {
      quality = "good";
      if (nakshatraAuspicious) reasons.push(`${p.nakshatra.en} Nakshatra`);
      if (yogaAuspicious) reasons.push(`${p.yoga.en} Yoga`);
    } else {
      quality = "neutral";
      reasons.push(`${p.nakshatra.en}, ${p.yoga.en}`);
    }

    // Skip neutral days entirely — only show excellent and good
    if (quality === "neutral") continue;

    // Build daytime range: sunrise to sunset
    const sunriseMs = parseIsoMs(p.sunrise);
    const sunsetMs = parseIsoMs(p.sunset);

    if (isNaN(sunriseMs) || isNaN(sunsetMs) || sunsetMs <= sunriseMs) continue;

    // Carve out Rahukalam and Yamagandam
    const rahuStartMs = parseIsoMs(p.rahukalam.start);
    const rahuEndMs = parseIsoMs(p.rahukalam.end);
    const yamaStartMs = parseIsoMs(p.yamagandam.start);
    const yamaEndMs = parseIsoMs(p.yamagandam.end);

    let segments: Array<[number, number]> = [[sunriseMs, sunsetMs]];

    // Subtract Rahukalam
    const afterRahu: Array<[number, number]> = [];
    for (const seg of segments) {
      if (overlaps(seg[0], seg[1], rahuStartMs, rahuEndMs)) {
        afterRahu.push(...subtractRange(seg[0], seg[1], rahuStartMs, rahuEndMs));
      } else {
        afterRahu.push(seg);
      }
    }
    segments = afterRahu;

    // Subtract Yamagandam
    const afterYama: Array<[number, number]> = [];
    for (const seg of segments) {
      if (overlaps(seg[0], seg[1], yamaStartMs, yamaEndMs)) {
        afterYama.push(...subtractRange(seg[0], seg[1], yamaStartMs, yamaEndMs));
      } else {
        afterYama.push(seg);
      }
    }
    segments = afterYama;

    // Emit windows that are at least 30 minutes
    for (const [segStart, segEnd] of segments) {
      const durationMin = Math.round((segEnd - segStart) / 60000);
      if (durationMin < 30) continue;

      windows.push({
        date: dateStr,
        start: new Date(segStart).toISOString(),
        end: new Date(segEnd).toISOString(),
        durationMinutes: durationMin,
        tithi: { te: p.tithi.te, en: p.tithi.en },
        nakshatra: { te: p.nakshatra.te, en: p.nakshatra.en },
        yoga: { te: p.yoga.te, en: p.yoga.en },
        quality,
        reason: reasons.join(", "),
      });
    }
  }

  return windows;
}
