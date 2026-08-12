import type { BilingualName } from "./types";
import karanaData from "../data/karana.json";

export interface KaranaResult {
  name: BilingualName;
  number: number;
  endsAt: Date | null;
}

/** Map English karana names to our bilingual data */
const KARANA_MAP: Record<string, { te: string; en: string; number: number }> =
  {};

for (const k of [...karanaData.movable, ...karanaData.fixed]) {
  KARANA_MAP[k.en.toLowerCase()] = k;
}

// Also map common alternate names
KARANA_MAP["gara"] = KARANA_MAP["garija"];
KARANA_MAP["bhadra"] = KARANA_MAP["vishti"];

/**
 * Get bilingual Karana info from a karana name string (from panchangam-js).
 * panchangam-js returns string names like "Bava", "Balava", etc.
 */
export function getKaranaInfo(
  karanaName: string,
  karanaEndTime: Date | null
): KaranaResult {
  const entry = KARANA_MAP[karanaName.toLowerCase()];

  if (!entry) {
    // Fallback: return the English name as-is
    return {
      name: { te: karanaName, en: karanaName },
      number: 0,
      endsAt: karanaEndTime,
    };
  }

  return {
    name: { te: entry.te, en: entry.en },
    number: entry.number,
    endsAt: karanaEndTime,
  };
}

/**
 * Check if a karana is Vishti (Bhadra) — considered inauspicious.
 */
export function isVishtiKarana(karanaName: string): boolean {
  const lower = karanaName.toLowerCase();
  return lower === "vishti" || lower === "bhadra";
}
