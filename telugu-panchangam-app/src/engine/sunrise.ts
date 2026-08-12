import SunCalc from "suncalc";
import { formatWithTz } from "./timezone";

export interface CelestialTimes {
  sunrise: Date;
  sunset: Date;
  moonrise: Date | null;
  moonset: Date | null;
}

/**
 * Get sunrise, sunset, moonrise, moonset for a given date and location.
 * The date should be in local time for the location.
 */
export function getCelestialTimes(
  date: Date,
  lat: number,
  lng: number
): CelestialTimes {
  const times = SunCalc.getTimes(date, lat, lng);
  const moonTimes = SunCalc.getMoonTimes(date, lat, lng);

  return {
    sunrise: times.sunrise,
    sunset: times.sunset,
    moonrise: moonTimes.rise ?? null,
    moonset: moonTimes.set ?? null,
  };
}

/**
 * Get formatted celestial times as ISO strings with timezone.
 */
export function getFormattedCelestialTimes(
  date: Date,
  lat: number,
  lng: number,
  tz: string
): {
  sunrise: string;
  sunset: string;
  moonrise: string;
  moonset: string;
} {
  const times = getCelestialTimes(date, lat, lng);

  return {
    sunrise: formatWithTz(times.sunrise, tz),
    sunset: formatWithTz(times.sunset, tz),
    moonrise: times.moonrise ? formatWithTz(times.moonrise, tz) : "",
    moonset: times.moonset ? formatWithTz(times.moonset, tz) : "",
  };
}
