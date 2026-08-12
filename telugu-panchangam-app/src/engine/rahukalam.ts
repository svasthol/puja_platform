import type { TimePeriod } from "./types";
import { formatWithTz } from "./timezone";

/**
 * Slot assignments for inauspicious periods by weekday (0=Sunday).
 * Each value is the 1-indexed slot number in the 8-slot daylight division.
 */
const RAHUKALAM_SLOTS: Record<number, number> = {
  0: 8, // Sunday
  1: 2, // Monday
  2: 7, // Tuesday
  3: 5, // Wednesday
  4: 6, // Thursday
  5: 3, // Friday
  6: 1, // Saturday
};

const GULIKA_SLOTS: Record<number, number> = {
  0: 3,
  1: 1,
  2: 6,
  3: 7,
  4: 5,
  5: 4,
  6: 2,
};

const YAMAGANDAM_SLOTS: Record<number, number> = {
  0: 1,
  1: 5,
  2: 4,
  3: 3,
  4: 2,
  5: 6,
  6: 7,
};

interface SlotTime {
  start: Date;
  end: Date;
}

/**
 * Calculate a time slot from sunrise and sunset.
 * Divides daylight into 8 equal slots, returns the specified slot (1-indexed).
 */
function getSlotTime(
  sunrise: Date,
  sunset: Date,
  slotNumber: number
): SlotTime {
  const daylightMs = sunset.getTime() - sunrise.getTime();
  const slotDurationMs = daylightMs / 8;

  const startMs = sunrise.getTime() + (slotNumber - 1) * slotDurationMs;
  const endMs = startMs + slotDurationMs;

  return {
    start: new Date(startMs),
    end: new Date(endMs),
  };
}

/**
 * Calculate Rahukalam for a given day.
 */
export function calculateRahukalam(
  sunrise: Date,
  sunset: Date,
  weekday: number,
  tz: string
): TimePeriod {
  const slot = RAHUKALAM_SLOTS[weekday];
  const times = getSlotTime(sunrise, sunset, slot);

  return {
    start: formatWithTz(times.start, tz),
    end: formatWithTz(times.end, tz),
    te: "రాహుకాలం",
    en: "Rahukalam",
  };
}

/**
 * Calculate Gulika Kalam for a given day.
 */
export function calculateGulikaKalam(
  sunrise: Date,
  sunset: Date,
  weekday: number,
  tz: string
): TimePeriod {
  const slot = GULIKA_SLOTS[weekday];
  const times = getSlotTime(sunrise, sunset, slot);

  return {
    start: formatWithTz(times.start, tz),
    end: formatWithTz(times.end, tz),
    te: "గులికకాలం",
    en: "Gulika Kalam",
  };
}

/**
 * Calculate Yamagandam for a given day.
 */
export function calculateYamagandam(
  sunrise: Date,
  sunset: Date,
  weekday: number,
  tz: string
): TimePeriod {
  const slot = YAMAGANDAM_SLOTS[weekday];
  const times = getSlotTime(sunrise, sunset, slot);

  return {
    start: formatWithTz(times.start, tz),
    end: formatWithTz(times.end, tz),
    te: "యమగండం",
    en: "Yamagandam",
  };
}
