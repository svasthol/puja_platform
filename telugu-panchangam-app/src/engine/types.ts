/** Bilingual name — Telugu + English */
export interface BilingualName {
  te: string;
  en: string;
}

/** Time period with bilingual label */
export interface TimePeriod {
  start: string; // ISO 8601 with timezone
  end: string;
  te: string;
  en: string;
}

/** Festival entry */
export interface Festival {
  date?: string;
  te: string;
  en: string;
  type: "tithi" | "solar" | "lookup" | "fixed";
  tier: 1 | 2 | 3;
  description?: { en: string };
  /** True for the four most sacred Ekadashis (Vaikunta, Nirjala, Devshayani, Prabodhini) */
  isSignificantEkadashi?: boolean;
  /** Bilingual explanation shown for significant Ekadashis */
  significance?: { te: string; en: string };
}

/** Complete single-day Panchangam */
export interface DayPanchangam {
  date: string; // YYYY-MM-DD
  samvatsaram: BilingualName & { number: number };
  masa: BilingualName & { number: number; isAdhika: boolean };
  paksha: { te: string; en: string; value: "shukla" | "krishna" };
  ritu: BilingualName;
  ayana: BilingualName;
  tithi: BilingualName & {
    number: number;
    endsAt: string;
    nextTithi: BilingualName & { number: number };
  };
  nakshatra: BilingualName & {
    number: number;
    pada: 1 | 2 | 3 | 4;
    endsAt: string;
  };
  yoga: BilingualName & {
    number: number;
    isAuspicious: boolean;
    endsAt: string;
  };
  karana: BilingualName & { number: number; endsAt: string };
  vara: BilingualName & { number: number };
  sunrise: string;
  sunset: string;
  moonrise: string;
  moonset: string;
  moonPhase: {
    te: string;
    en: string;
    illuminationPercent: number;
    phase: number;
  };
  rahukalam: TimePeriod;
  gulikaKalam: TimePeriod;
  yamagandam: TimePeriod;
  festivals: Festival[];
}

/** Location with timezone */
export interface Location {
  lat: number;
  lng: number;
  tz: string;
}
