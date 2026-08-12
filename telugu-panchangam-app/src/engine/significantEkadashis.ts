/**
 * The four most sacred Ekadashis in the Telugu tradition.
 * Kept in a standalone module so both the per-day matcher
 * (festivalMatcher.ts) and the full-year scanner (festivals.ts)
 * can share the same lookup without creating an import cycle.
 *
 * Telugu masa numbering:
 *   1=Chaitra, 2=Vaishakha, 3=Jyeshtha, 4=Ashadha, 5=Shravana,
 *   6=Bhadrapada, 7=Ashvina, 8=Kartika, 9=Margashira, 10=Pushya,
 *   11=Magha, 12=Phalguna.
 */

export interface SignificantEkadashi {
  te: string;
  en: string;
  significance: { te: string; en: string };
}

export const SIGNIFICANT_EKADASHIS: Record<string, SignificantEkadashi> = {
  "9-shukla": {
    te: "వైకుంఠ ఏకాదశి (ముక్కోటి)",
    en: "Vaikunta Ekadashi (Mukkoti)",
    significance: {
      te: "సంవత్సరంలో అత్యంత పవిత్రమైన ఏకాదశి. వైకుంఠ ద్వారం తెరుచుకుంటుంది. ఈ రోజు ఉపవాసం 24 ఏకాదశులకు సమానం.",
      en: "The most sacred Ekadashi of the year. The gates of Vaikunta open. Fasting on this day equals observing all 24 Ekadashis.",
    },
  },
  "3-shukla": {
    te: "నిర్జలా ఏకాదశి",
    en: "Nirjala Ekadashi",
    significance: {
      te: "నీళ్ళు కూడా తాగకుండా ఉపవాసం ఉండే అత్యంత కఠినమైన ఏకాదశి. ఈ ఒక్క ఏకాదశి 24 ఏకాదశులకు సమానమని చెప్పబడింది.",
      en: "The most austere Ekadashi — fasting without even water. Said to equal the merit of all 24 Ekadashis.",
    },
  },
  "4-shukla": {
    te: "దేవశయని ఏకాదశి",
    en: "Devshayani Ekadashi",
    significance: {
      te: "విష్ణువు నిద్రపోయే రోజు. చాతుర్మాస్య ప్రారంభం. ఈ రోజు నుండి 4 నెలలు శుభకార్యాలు చేయరు.",
      en: "The day Lord Vishnu goes to sleep. Marks the start of Chaturmas — 4 months when auspicious activities are avoided.",
    },
  },
  "8-shukla": {
    te: "ప్రబోధిని ఏకాదశి (ఉత్థాన)",
    en: "Prabodhini Ekadashi (Utthana)",
    significance: {
      te: "విష్ణువు నిద్ర లేచే రోజు. చాతుర్మాస్య సమాప్తి. వివాహాలకు అత్యంత శుభప్రదమైన సమయం ప్రారంభమవుతుంది.",
      en: "Lord Vishnu awakens. Marks the end of Chaturmas. The most auspicious period for weddings begins.",
    },
  },
};

export function getSignificantEkadashi(
  masaNumber: number,
  paksha: "shukla" | "krishna"
): SignificantEkadashi | undefined {
  return SIGNIFICANT_EKADASHIS[`${masaNumber}-${paksha}`];
}
