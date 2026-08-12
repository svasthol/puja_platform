import type { BilingualName } from "./types";
import samvatsaramData from "../data/samvatsaram.json";

export interface SamvatsaramResult {
  name: BilingualName;
  number: number;
}

/**
 * Get the Samvatsaram (Telugu year name) for a given Gregorian date.
 *
 * The Telugu new year (Ugadi) falls on Chaitra Shukla Pratipada, typically in March/April.
 * Before Ugadi, the previous year's Samvatsaram applies.
 *
 * We use the samvatsara name from the panchangam-js library's samvat field,
 * but provide our own bilingual mapping.
 *
 * The 60-year cycle reference:
 * - 2025-2026 (Ugadi to Ugadi): Vishvavasu (39th)
 * - 2026-2027: Parabhava (40th)
 *
 * Mapping: (gregorianYear - 1987) mod 60 gives the 0-indexed position.
 * 1987 was Prabhava (1st), so 1987 → index 0.
 */
export function getSamvatsaram(
  samvatsaraName: string
): SamvatsaramResult {
  // Try to find by English name from panchangam-js
  const entry = samvatsaramData.find(
    (s) => s.en.toLowerCase() === samvatsaraName.toLowerCase()
  );

  if (entry) {
    return {
      name: { te: entry.te, en: entry.en },
      number: entry.number,
    };
  }

  // Fallback: return name as-is
  return {
    name: { te: samvatsaraName, en: samvatsaraName },
    number: 0,
  };
}

/**
 * Get Samvatsaram by calculating from year and month.
 * Before Ugadi (roughly before April), use previous year's samvatsaram.
 */
export function getSamvatsaramForDate(
  year: number,
  month: number
): SamvatsaramResult {
  // The Telugu new year starts around March/April (Chaitra Shukla Pratipada)
  // For months Jan-March, use previous year's cycle
  const effectiveYear = month <= 3 ? year - 1 : year;

  // 1987 was Prabhava (index 0)
  const index = ((effectiveYear - 1987) % 60 + 60) % 60;
  const entry = samvatsaramData[index];

  return {
    name: { te: entry.te, en: entry.en },
    number: entry.number,
  };
}
