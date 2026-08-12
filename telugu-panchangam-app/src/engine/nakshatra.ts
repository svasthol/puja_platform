import { getPanchangam as getCorePanchangam } from "@ishubhamx/panchangam-js";
import type { BilingualName } from "./types";
import { createObserver } from "./astronomy";
import { localToUtc, getTimezoneOffsetMinutes } from "./timezone";
import nakshatraData from "../data/nakshatra.json";

export interface NakshatraResult {
  name: BilingualName;
  number: number;
  pada: 1 | 2 | 3 | 4;
  endsAt: Date | null;
}

export interface TarabalamResult {
  todaysNakshatra: BilingualName;
  taraNumber: number; // 1-9
  taraName: string;
  quality:
    | "highly_auspicious"
    | "auspicious"
    | "neutral"
    | "inauspicious"
    | "highly_inauspicious";
  te: string;
  en: string;
}

export interface JanmaNakshatraResult {
  nakshatraNumber: number;
  nakshatra: BilingualName;
  pada: 1 | 2 | 3 | 4;
  raasi: BilingualName;
  deity: string;
  tarabalam?: TarabalamResult;
}

/**
 * Get bilingual Nakshatra info from a 0-indexed nakshatra number (from panchangam-js).
 * panchangam-js returns 0-26: 0=Ashwini, 26=Revati
 */
export function getNakshatraInfo(
  nakshatraIndex: number,
  pada: number,
  nakshatraEndTime: Date | null
): NakshatraResult {
  const entry = nakshatraData[nakshatraIndex];

  if (!entry) {
    throw new Error(`Invalid nakshatra index: ${nakshatraIndex}`);
  }

  // Clamp pada to 1-4 (panchangam-js returns 0-3)
  const padaValue = Math.max(1, Math.min(4, pada + 1)) as 1 | 2 | 3 | 4;

  return {
    name: { te: entry.te, en: entry.en },
    number: nakshatraIndex + 1,
    pada: padaValue,
    endsAt: nakshatraEndTime,
  };
}

// ─────────────────────────────────────────────
// Raasi (Zodiac Sign) mapping
// ─────────────────────────────────────────────

interface RaasiInfo {
  te: string;
  en: string;
}

const RAASI_LIST: RaasiInfo[] = [
  { te: "మేషం", en: "Mesha (Aries)" },
  { te: "వృషభం", en: "Vrishabha (Taurus)" },
  { te: "మిథునం", en: "Mithuna (Gemini)" },
  { te: "కర్కాటకం", en: "Karka (Cancer)" },
  { te: "సింహం", en: "Simha (Leo)" },
  { te: "కన్య", en: "Kanya (Virgo)" },
  { te: "తుల", en: "Tula (Libra)" },
  { te: "వృశ్చికం", en: "Vrischika (Scorpio)" },
  { te: "ధనస్సు", en: "Dhanu (Sagittarius)" },
  { te: "మకరం", en: "Makara (Capricorn)" },
  { te: "కుంభం", en: "Kumbha (Aquarius)" },
  { te: "మీనం", en: "Meena (Pisces)" },
];

/**
 * Map Nakshatra (1-27) + Pada (1-4) to Raasi (0-11).
 * Each Nakshatra has 4 padas, each pada = one navamsa = 3°20'.
 * 108 padas / 9 padas per raasi = 12 raasis.
 * Pada index = (nakshatra-1)*4 + (pada-1), raasi = floor(padaIndex / 9).
 */
function getRaasi(nakshatraNumber: number, pada: 1 | 2 | 3 | 4): RaasiInfo {
  const padaIndex = (nakshatraNumber - 1) * 4 + (pada - 1);
  const raasiIndex = Math.floor(padaIndex / 9);
  return RAASI_LIST[raasiIndex] ?? RAASI_LIST[0];
}

// ─────────────────────────────────────────────
// Tarabalam (Star compatibility for the day)
// ─────────────────────────────────────────────

interface TaraEntry {
  name: string;
  te: string;
  quality: TarabalamResult["quality"];
}

const TARA_TABLE: TaraEntry[] = [
  { name: "Janma Tara", te: "జన్మ తార", quality: "neutral" },
  { name: "Sampat Tara", te: "సంపత్ తార", quality: "auspicious" },
  { name: "Vipat Tara", te: "విపత్ తార", quality: "inauspicious" },
  { name: "Kshema Tara", te: "క్షేమ తార", quality: "auspicious" },
  { name: "Pratyak Tara", te: "ప్రత్యక్ తార", quality: "inauspicious" },
  { name: "Sadhana Tara", te: "సాధన తార", quality: "auspicious" },
  { name: "Naidhana Tara", te: "నైధన తార", quality: "highly_inauspicious" },
  { name: "Mitra Tara", te: "మిత్ర తార", quality: "auspicious" },
  { name: "Parama Mitra Tara", te: "పరమ మిత్ర తార", quality: "highly_auspicious" },
];

function calculateTarabalam(
  birthNakshatraNumber: number,
  todayNakshatraNumber: number,
  todayNakshatra: BilingualName
): TarabalamResult {
  // taraNumber: 1-based, cyclic distance mod 9
  const diff = ((todayNakshatraNumber - birthNakshatraNumber + 27) % 27);
  const taraNumber = (diff % 9) + 1;
  const entry = TARA_TABLE[taraNumber - 1];

  return {
    todaysNakshatra: todayNakshatra,
    taraNumber,
    taraName: entry.name,
    quality: entry.quality,
    te: entry.te,
    en: entry.name,
  };
}

// ─────────────────────────────────────────────
// Janma Nakshatra finder
// ─────────────────────────────────────────────

/**
 * Calculate the Janma Nakshatra (birth star) for a given birth date, time, and location.
 * Uses panchangam-js at the exact birth moment (not sunrise).
 * Optionally calculates Tarabalam if today's location/date are provided.
 */
export function getJanmaNakshatra(
  birthDate: string,
  birthTime: string,
  lat: number,
  lng: number,
  tz: string,
  todayLat?: number,
  todayLng?: number,
  todayTz?: string,
  todayDate?: string
): JanmaNakshatraResult {
  // Parse birth date + time
  const [year, month, day] = birthDate.split("-").map(Number);
  const [hours, minutes] = birthTime.split(":").map(Number);
  const birthLocal = new Date(year, month - 1, day, hours, minutes, 0);
  const birthUtc = localToUtc(birthLocal, tz);

  const tzOffsetMinutes = getTimezoneOffsetMinutes(birthUtc, tz);
  const observer = createObserver(lat, lng);

  const core = getCorePanchangam(birthUtc, observer, {
    timezoneOffset: tzOffsetMinutes,
    calendarType: "amanta",
  });

  // Extract nakshatra (0-indexed from panchangam-js)
  const nakshatraIndex = core.nakshatra;
  const padaRaw = core.nakshatraPada;
  const pada = Math.max(1, Math.min(4, padaRaw + 1)) as 1 | 2 | 3 | 4;
  const nakshatraNumber = nakshatraIndex + 1;

  const entry = nakshatraData[nakshatraIndex];
  if (!entry) {
    throw new Error(`Invalid nakshatra index: ${nakshatraIndex}`);
  }

  const nakshatra: BilingualName = { te: entry.te, en: entry.en };
  const raasi = getRaasi(nakshatraNumber, pada);

  // Calculate Tarabalam if today params provided
  let tarabalam: TarabalamResult | undefined;
  if (
    todayLat !== undefined &&
    todayLng !== undefined &&
    todayTz !== undefined &&
    todayDate !== undefined
  ) {
    const [ty, tm, td] = todayDate.split("-").map(Number);
    const todayNoon = new Date(ty, tm - 1, td, 12, 0, 0);
    const todayUtc = localToUtc(todayNoon, todayTz);
    const todayTzOffset = getTimezoneOffsetMinutes(todayUtc, todayTz);
    const todayObserver = createObserver(todayLat, todayLng);

    const todayCore = getCorePanchangam(todayUtc, todayObserver, {
      timezoneOffset: todayTzOffset,
      calendarType: "amanta",
    });

    const todayNakshatraIndex = todayCore.nakshatra;
    const todayNakshatraNumber = todayNakshatraIndex + 1;
    const todayEntry = nakshatraData[todayNakshatraIndex];
    const todayNakshatra: BilingualName = todayEntry
      ? { te: todayEntry.te, en: todayEntry.en }
      : { te: "", en: "" };

    tarabalam = calculateTarabalam(
      nakshatraNumber,
      todayNakshatraNumber,
      todayNakshatra
    );
  }

  return {
    nakshatraNumber,
    nakshatra,
    pada,
    raasi,
    deity: entry.deity,
    tarabalam,
  };
}
