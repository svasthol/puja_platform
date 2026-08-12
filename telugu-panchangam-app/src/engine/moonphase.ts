import SunCalc from "suncalc";
import type { BilingualName } from "./types";

export interface MoonPhaseInfo {
  te: string;
  en: string;
  illuminationPercent: number;
  phase: number;
}

const PHASE_NAMES: Array<{ min: number; max: number; en: string; te: string }> =
  [
    { min: 0, max: 0.03, en: "New Moon", te: "అమావాస్య" },
    { min: 0.03, max: 0.22, en: "Waxing Crescent", te: "శుక్ల వంక" },
    { min: 0.22, max: 0.28, en: "First Quarter", te: "శుక్ల అష్టమి" },
    { min: 0.28, max: 0.47, en: "Waxing Gibbous", te: "శుక్ల గిబ్బస్" },
    { min: 0.47, max: 0.53, en: "Full Moon", te: "పౌర్ణమి" },
    { min: 0.53, max: 0.72, en: "Waning Gibbous", te: "కృష్ణ గిబ్బస్" },
    { min: 0.72, max: 0.78, en: "Last Quarter", te: "కృష్ణ అష్టమి" },
    { min: 0.78, max: 0.97, en: "Waning Crescent", te: "కృష్ణ వంక" },
    { min: 0.97, max: 1.01, en: "New Moon", te: "అమావాస్య" },
  ];

/**
 * Get moon phase and illumination for a given date.
 */
export function getMoonPhaseInfo(date: Date): MoonPhaseInfo {
  const illum = SunCalc.getMoonIllumination(date);
  const phase = illum.phase;
  const illuminationPercent = Math.round(illum.fraction * 1000) / 10;

  const phaseName =
    PHASE_NAMES.find((p) => phase >= p.min && phase < p.max) ?? PHASE_NAMES[0];

  return {
    te: phaseName.te,
    en: phaseName.en,
    illuminationPercent,
    phase: Math.round(phase * 1000) / 1000,
  };
}
