import type { BilingualName } from "./types";
import tithiData from "../data/tithi.json";

export interface TithiResult {
  name: BilingualName;
  number: number;
  paksha: "shukla" | "krishna";
  endsAt: Date | null;
  nextTithi: BilingualName & { number: number };
}

/**
 * Get bilingual Tithi info from a 0-indexed tithi number (from panchangam-js).
 * panchangam-js returns 0-29: 0=Shukla Pratipada, 14=Purnima, 15=Krishna Pratipada, 29=Amavasya
 */
export function getTithiInfo(
  tithiIndex: number,
  tithiEndTime: Date | null
): TithiResult {
  // Convert 0-indexed to 1-indexed (our data is 1-30)
  const number = tithiIndex + 1;
  const entry = tithiData[tithiIndex];

  if (!entry) {
    throw new Error(`Invalid tithi index: ${tithiIndex}`);
  }

  const paksha: "shukla" | "krishna" =
    number <= 15 ? "shukla" : "krishna";

  // Next tithi (wraps around)
  const nextIndex = (tithiIndex + 1) % 30;
  const nextEntry = tithiData[nextIndex];

  return {
    name: { te: entry.te, en: entry.en },
    number,
    paksha,
    endsAt: tithiEndTime,
    nextTithi: {
      te: nextEntry.te,
      en: nextEntry.en,
      number: nextIndex + 1,
    },
  };
}

/**
 * Check if a tithi number (1-30) represents an Ekadashi.
 */
export function isEkadashi(tithiNumber: number): boolean {
  return tithiNumber === 11 || tithiNumber === 26;
}

/**
 * Check if a tithi number (1-30) represents Amavasya.
 */
export function isAmavasya(tithiNumber: number): boolean {
  return tithiNumber === 30;
}

/**
 * Check if a tithi number (1-30) represents Purnima.
 */
export function isPurnima(tithiNumber: number): boolean {
  return tithiNumber === 15;
}
