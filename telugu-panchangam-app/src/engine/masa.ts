import type { BilingualName } from "./types";
import masaData from "../data/masa.json";

export interface MasaResult {
  name: BilingualName;
  number: number;
  isAdhika: boolean;
}

/**
 * Get bilingual Masa info from panchangam-js masa output.
 * panchangam-js returns { index: 0-11, name: string, isAdhika: boolean }
 * with calendarType: 'amanta' for Telugu (new moon to new moon).
 */
export function getMasaInfo(
  masaIndex: number,
  isAdhika: boolean
): MasaResult {
  const entry = masaData[masaIndex];

  if (!entry) {
    throw new Error(`Invalid masa index: ${masaIndex}`);
  }

  const prefix = isAdhika ? "Adhika " : "";
  const tePrefix = isAdhika ? "అధిక " : "";

  return {
    name: {
      te: tePrefix + entry.te,
      en: prefix + entry.en,
    },
    number: entry.number,
    isAdhika,
  };
}

/** Ritu (season) names — bilingual */
const RITU_DATA: Record<string, BilingualName> = {
  Vasant: { te: "వసంత ఋతువు", en: "Vasanta (Spring)" },
  Vasanta: { te: "వసంత ఋతువు", en: "Vasanta (Spring)" },
  Grishma: { te: "గ్రీష్మ ఋతువు", en: "Grishma (Summer)" },
  Varsha: { te: "వర్ష ఋతువు", en: "Varsha (Monsoon)" },
  Sharad: { te: "శరద్ ఋతువు", en: "Sharada (Autumn)" },
  Sharada: { te: "శరద్ ఋతువు", en: "Sharada (Autumn)" },
  Hemant: { te: "హేమంత ఋతువు", en: "Hemanta (Winter)" },
  Hemanta: { te: "హేమంత ఋతువు", en: "Hemanta (Winter)" },
  Shishir: { te: "శిశిర ఋతువు", en: "Shishira (Late Winter)" },
  Shishira: { te: "శిశిర ఋతువు", en: "Shishira (Late Winter)" },
};

/**
 * Get bilingual Ritu (season) name from panchangam-js ritu string.
 */
export function getRituInfo(rituName: string): BilingualName {
  return RITU_DATA[rituName] ?? { te: rituName, en: rituName };
}

/** Ayana names — bilingual */
const AYANA_DATA: Record<string, BilingualName> = {
  Uttarayana: { te: "ఉత్తరాయణం", en: "Uttarayana" },
  Dakshinayana: { te: "దక్షిణాయనం", en: "Dakshinayana" },
};

/**
 * Get bilingual Ayana name from panchangam-js ayana string.
 */
export function getAyanaInfo(ayanaName: string): BilingualName {
  return AYANA_DATA[ayanaName] ?? { te: ayanaName, en: ayanaName };
}
