import { getPanchangam as getCorePanchangam } from "@ishubhamx/panchangam-js";
import type { DayPanchangam, Location, BilingualName } from "./types";
import { createObserver } from "./astronomy";
import { getTithiInfo } from "./tithi";
import { getNakshatraInfo } from "./nakshatra";
import { getYogaInfo } from "./yoga";
import { getKaranaInfo } from "./karana";
import { getSamvatsaram, getSamvatsaramForDate } from "./samvatsaram";
import { getMasaInfo, getRituInfo, getAyanaInfo } from "./masa";
import {
  calculateRahukalam,
  calculateGulikaKalam,
  calculateYamagandam,
} from "./rahukalam";
import { getCelestialTimes } from "./sunrise";
import { getMoonPhaseInfo } from "./moonphase";
import { formatWithTz, getTimezoneOffsetMinutes } from "./timezone";
import { localToUtc } from "./timezone";
import { matchFestivalsForDay } from "./festivalMatcher";

/** Telugu weekday names */
const VARA_NAMES: BilingualName[] = [
  { te: "ఆదివారం", en: "Sunday" },
  { te: "సోమవారం", en: "Monday" },
  { te: "మంగళవారం", en: "Tuesday" },
  { te: "బుధవారం", en: "Wednesday" },
  { te: "గురువారం", en: "Thursday" },
  { te: "శుక్రవారం", en: "Friday" },
  { te: "శనివారం", en: "Saturday" },
];

/** Paksha bilingual labels */
const PAKSHA_LABELS = {
  shukla: { te: "శుక్ల పక్షం", en: "Shukla Paksha" },
  krishna: { te: "కృష్ణ పక్షం", en: "Krishna Paksha" },
};

/**
 * Calculate the complete Panchangam for a single date and location.
 *
 * This is the main entry point for the calculation engine.
 * It wraps @ishubhamx/panchangam-js with Telugu bilingual names
 * and adds sunrise-based Rahukalam/Gulika/Yamagandam.
 */
export function calculateDayPanchangam(
  dateStr: string,
  location: Location
): DayPanchangam {
  const { lat, lng, tz } = location;

  // Parse the date string and create a Date at noon local time
  const [year, month, day] = dateStr.split("-").map(Number);
  const localNoon = new Date(year, month - 1, day, 12, 0, 0);
  const utcDate = localToUtc(localNoon, tz);

  // Get timezone offset in minutes for panchangam-js
  const tzOffsetMinutes = getTimezoneOffsetMinutes(utcDate, tz);

  // Create observer
  const observer = createObserver(lat, lng);

  // Get core panchangam from library
  const core = getCorePanchangam(utcDate, observer, {
    timezoneOffset: tzOffsetMinutes,
    calendarType: "amanta", // Telugu tradition
  });

  // Get celestial times (sunrise, sunset, moonrise, moonset)
  const celestial = getCelestialTimes(utcDate, lat, lng);

  // Vara (weekday) — from the local date
  const localDate = new Date(year, month - 1, day);
  const weekday = localDate.getDay(); // 0=Sunday

  // Build Tithi info
  const tithiResult = getTithiInfo(
    core.tithi,
    core.tithiEndTime ?? null
  );

  // Build Nakshatra info
  const nakshatraResult = getNakshatraInfo(
    core.nakshatra,
    core.nakshatraPada,
    core.nakshatraEndTime ?? null
  );

  // Build Yoga info
  const yogaResult = getYogaInfo(
    core.yoga,
    core.yogaEndTime ?? null
  );

  // Build Karana info
  const karanaEndTime =
    core.karanaTransitions?.[0]?.endTime ?? core.tithiEndTime ?? null;
  const karanaResult = getKaranaInfo(core.karana, karanaEndTime);

  // Samvatsaram — try from library first, then calculate
  let samvatsaramResult;
  if (core.samvat?.samvatsara) {
    samvatsaramResult = getSamvatsaram(core.samvat.samvatsara);
  } else {
    samvatsaramResult = getSamvatsaramForDate(year, month);
  }

  // Masa
  const masaResult = getMasaInfo(
    core.masa?.index ?? 0,
    core.masa?.isAdhika ?? false
  );

  // Ritu and Ayana
  const rituResult = getRituInfo(core.ritu ?? "");
  const ayanaResult = getAyanaInfo(core.ayana ?? "");

  // Paksha
  const pakshaValue = tithiResult.paksha;
  const pakshaLabel = PAKSHA_LABELS[pakshaValue];

  // Moon phase
  const moonPhase = getMoonPhaseInfo(utcDate);

  // Rahukalam, Gulika, Yamagandam — based on actual sunrise/sunset
  const rahukalam = calculateRahukalam(
    celestial.sunrise,
    celestial.sunset,
    weekday,
    tz
  );
  const gulikaKalam = calculateGulikaKalam(
    celestial.sunrise,
    celestial.sunset,
    weekday,
    tz
  );
  const yamagandam = calculateYamagandam(
    celestial.sunrise,
    celestial.sunset,
    weekday,
    tz
  );

  const result: DayPanchangam = {
    date: dateStr,
    samvatsaram: {
      ...samvatsaramResult.name,
      number: samvatsaramResult.number,
    },
    masa: {
      ...masaResult.name,
      number: masaResult.number,
      isAdhika: masaResult.isAdhika,
    },
    paksha: {
      ...pakshaLabel,
      value: pakshaValue,
    },
    ritu: rituResult,
    ayana: ayanaResult,
    tithi: {
      ...tithiResult.name,
      number: tithiResult.number,
      endsAt: tithiResult.endsAt ? formatWithTz(tithiResult.endsAt, tz) : "",
      nextTithi: tithiResult.nextTithi,
    },
    nakshatra: {
      ...nakshatraResult.name,
      number: nakshatraResult.number,
      pada: nakshatraResult.pada,
      endsAt: nakshatraResult.endsAt
        ? formatWithTz(nakshatraResult.endsAt, tz)
        : "",
    },
    yoga: {
      ...yogaResult.name,
      number: yogaResult.number,
      isAuspicious: yogaResult.isAuspicious,
      endsAt: yogaResult.endsAt ? formatWithTz(yogaResult.endsAt, tz) : "",
    },
    karana: {
      ...karanaResult.name,
      number: karanaResult.number,
      endsAt: karanaResult.endsAt ? formatWithTz(karanaResult.endsAt, tz) : "",
    },
    vara: {
      ...VARA_NAMES[weekday],
      number: weekday,
    },
    sunrise: formatWithTz(celestial.sunrise, tz),
    sunset: formatWithTz(celestial.sunset, tz),
    moonrise: celestial.moonrise ? formatWithTz(celestial.moonrise, tz) : "",
    moonset: celestial.moonset ? formatWithTz(celestial.moonset, tz) : "",
    moonPhase,
    rahukalam,
    gulikaKalam,
    yamagandam,
    festivals: [],
  };

  // Match festivals for this day
  result.festivals = matchFestivalsForDay(result);

  return result;
}
