import type { BilingualName } from "./types";
import yogaData from "../data/yoga.json";

export interface YogaResult {
  name: BilingualName;
  number: number;
  isAuspicious: boolean;
  endsAt: Date | null;
}

const INAUSPICIOUS_YOGAS = new Set([
  "inauspicious",
  "highly_inauspicious",
]);

/**
 * Get bilingual Yoga info from a 0-indexed yoga number (from panchangam-js).
 * panchangam-js returns 0-26: 0=Vishkambha, 26=Vaidhriti
 */
export function getYogaInfo(
  yogaIndex: number,
  yogaEndTime: Date | null
): YogaResult {
  const entry = yogaData[yogaIndex];

  if (!entry) {
    throw new Error(`Invalid yoga index: ${yogaIndex}`);
  }

  return {
    name: { te: entry.te, en: entry.en },
    number: yogaIndex + 1,
    isAuspicious: !INAUSPICIOUS_YOGAS.has(entry.nature),
    endsAt: yogaEndTime,
  };
}
