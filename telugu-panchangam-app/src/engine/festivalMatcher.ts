import type { DayPanchangam, Festival } from "./types";
import { getSignificantEkadashi } from "./significantEkadashis";

/**
 * Match festivals for a single day based on its panchangam data.
 * This is the lightweight per-day matcher used by the calendar grid and day view.
 *
 * Some festivals match on sunrise tithi, others match on the tithi that begins
 * during the day (nextTithi). For example:
 * - Ugadi: Pratipada begins during the day when sunrise tithi is still Amavasya
 * - Sivaratri: observed on the night when Chaturdashi prevails
 */

interface LunarRule {
  masa: number;
  tithi: number;
  te: string;
  en: string;
  tier: 1 | 2;
  /** If true, also match when nextTithi equals this tithi (for festivals observed
   *  when the tithi begins during the day, not necessarily at sunrise) */
  matchNextTithi?: boolean;
  /** For matchNextTithi: the previous tithi that should be active at sunrise */
  prevTithi?: number;
}

const LUNAR_RULES: LunarRule[] = [
  // Ugadi: Chaitra Shukla Pratipada — observed on the day Pratipada begins
  // At sunrise tithi may still be Phalguna Amavasya, but Pratipada starts during the day
  { masa: 1, tithi: 1, te: "ఉగాది", en: "Ugadi", tier: 1, matchNextTithi: true, prevTithi: 30 },
  { masa: 1, tithi: 9, te: "శ్రీ రామ నవమి", en: "Sri Rama Navami", tier: 1 },
  { masa: 1, tithi: 15, te: "హనుమాన్ జయంతి", en: "Hanuman Jayanti", tier: 1 },
  { masa: 2, tithi: 3, te: "అక్షయ తృతీయ", en: "Akshaya Tritiya", tier: 1 },
  { masa: 5, tithi: 23, te: "శ్రీ కృష్ణ జన్మాష్టమి", en: "Krishna Janmashtami", tier: 1 },
  { masa: 6, tithi: 4, te: "వినాయక చవితి", en: "Vinayaka Chaturthi", tier: 1 },
  { masa: 7, tithi: 10, te: "విజయదశమి", en: "Vijayadasami", tier: 1 },
  { masa: 8, tithi: 30, te: "దీపావళి", en: "Deepavali", tier: 1 },
  { masa: 8, tithi: 15, te: "కార్తీక పౌర్ణమి", en: "Karthika Purnima", tier: 1 },
  { masa: 8, tithi: 4, te: "నాగుల చవితి", en: "Nagula Chavithi", tier: 2 },
  // Sivaratri: observed on the night when Chaturdashi prevails
  // At sunrise the tithi is Trayodashi, Chaturdashi starts during the day/evening
  { masa: 11, tithi: 29, te: "మహా శివరాత్రి", en: "Maha Sivaratri", tier: 1, matchNextTithi: true, prevTithi: 28 },
  { masa: 12, tithi: 15, te: "హోలీ", en: "Holi", tier: 1 },
];

interface FixedRule {
  month: number;
  day: number;
  te: string;
  en: string;
  tier: 1 | 2 | 3;
  type: "solar" | "fixed";
}

const FIXED_RULES: FixedRule[] = [
  { month: 1, day: 13, te: "భోగి", en: "Bhogi", tier: 1, type: "solar" },
  { month: 1, day: 14, te: "మకర సంక్రాంతి", en: "Makara Sankranti", tier: 1, type: "solar" },
  { month: 1, day: 15, te: "కనుమ", en: "Kanuma", tier: 1, type: "solar" },
  { month: 1, day: 26, te: "గణతంత్ర దినోత్సవం", en: "Republic Day", tier: 3, type: "fixed" },
  { month: 6, day: 2, te: "తెలంగాణ అవతరణ దినం", en: "Telangana Formation Day", tier: 3, type: "fixed" },
  { month: 8, day: 15, te: "స్వాతంత్ర్య దినోత్సవం", en: "Independence Day", tier: 3, type: "fixed" },
  { month: 10, day: 2, te: "గాంధీ జయంతి", en: "Gandhi Jayanti", tier: 3, type: "fixed" },
  { month: 11, day: 1, te: "ఆంధ్రప్రదేశ్ అవతరణ దినం", en: "AP Formation Day", tier: 3, type: "fixed" },
  { month: 12, day: 25, te: "క్రిస్మస్", en: "Christmas", tier: 3, type: "fixed" },
];

export function matchFestivalsForDay(p: DayPanchangam): Festival[] {
  const festivals: Festival[] = [];
  const [, monthStr, dayStr] = p.date.split("-");
  const gregMonth = parseInt(monthStr, 10);
  const gregDay = parseInt(dayStr, 10);

  // Lunar rules — check both sunrise tithi and next-tithi transitions
  for (const rule of LUNAR_RULES) {
    // Direct match: sunrise tithi matches the rule
    const directMatch =
      p.masa.number === rule.masa &&
      !p.masa.isAdhika &&
      p.tithi.number === rule.tithi;

    // Next-tithi match: the target tithi begins during this day
    // (sunrise tithi is the previous one, nextTithi is the target)
    let nextTithiMatch = false;
    if (rule.matchNextTithi && rule.prevTithi !== undefined) {
      // For Ugadi: prevTithi=30 (Amavasya), current masa may still be Phalguna(12)
      // but nextTithi is Pratipada(1) of Chaitra(1)
      if (rule.en === "Ugadi") {
        // Special case: Ugadi spans the masa boundary (Phalguna→Chaitra)
        nextTithiMatch =
          p.masa.number === 12 &&
          !p.masa.isAdhika &&
          p.tithi.number === rule.prevTithi &&
          p.tithi.nextTithi.number === rule.tithi;
      } else {
        nextTithiMatch =
          p.masa.number === rule.masa &&
          !p.masa.isAdhika &&
          p.tithi.number === rule.prevTithi &&
          p.tithi.nextTithi.number === rule.tithi;
      }
    }

    if (directMatch || nextTithiMatch) {
      festivals.push({
        te: rule.te,
        en: rule.en,
        type: "tithi",
        tier: rule.tier,
      });
    }
  }

  // Fixed date rules
  for (const rule of FIXED_RULES) {
    if (gregMonth === rule.month && gregDay === rule.day) {
      festivals.push({
        te: rule.te,
        en: rule.en,
        type: rule.type,
        tier: rule.tier,
      });
    }
  }

  // Ekadashi — significant ones get special name + tier 1 + significance text
  if (p.tithi.number === 11 || p.tithi.number === 26) {
    const significant = getSignificantEkadashi(p.masa.number, p.paksha.value);
    if (significant) {
      festivals.push({
        te: significant.te,
        en: significant.en,
        type: "tithi",
        tier: 1,
        isSignificantEkadashi: true,
        significance: significant.significance,
      });
    } else {
      const pakshaLabel = p.paksha.value === "shukla" ? "Shukla" : "Krishna";
      festivals.push({
        te: "ఏకాదశి",
        en: `${pakshaLabel} Ekadashi`,
        type: "tithi",
        tier: 2,
      });
    }
  }

  // Amavasya (if not already Deepavali which is also Amavasya)
  if (p.tithi.number === 30 && !festivals.some((f) => f.en === "Deepavali")) {
    festivals.push({
      te: "అమావాస్య",
      en: "Amavasya",
      type: "tithi",
      tier: 1,
    });
  }

  // Purnima (if not already a named purnima festival)
  if (
    p.tithi.number === 15 &&
    !festivals.some(
      (f) =>
        f.en === "Karthika Purnima" ||
        f.en === "Holi" ||
        f.en === "Hanuman Jayanti"
    )
  ) {
    festivals.push({
      te: "పౌర్ణమి",
      en: "Purnima",
      type: "tithi",
      tier: 1,
    });
  }

  return festivals;
}
