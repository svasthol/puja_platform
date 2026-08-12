import type { Lang } from "./i18n";

export interface CityInfo {
  name: string;
  lat: number;
  lng: number;
  tz: string;
}

const CITY_KEY = "panchangam-city";
const LANG_KEY = "panchangam-lang";

const DEFAULT_CITY: CityInfo = {
  name: "Melbourne",
  lat: -37.8136,
  lng: 144.9631,
  tz: "Australia/Melbourne",
};

export function getCity(): CityInfo {
  if (typeof window === "undefined") return DEFAULT_CITY;
  try {
    const stored = localStorage.getItem(CITY_KEY);
    if (stored) return JSON.parse(stored) as CityInfo;
  } catch {
    // localStorage unavailable or corrupted
  }
  return DEFAULT_CITY;
}

export function setCity(city: CityInfo): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CITY_KEY, JSON.stringify(city));
  } catch {
    // localStorage full or unavailable
  }
}

export function getLang(): Lang {
  if (typeof window === "undefined") return "en";
  try {
    const stored = localStorage.getItem(LANG_KEY);
    if (stored === "te" || stored === "en") return stored;
  } catch {
    // localStorage unavailable
  }
  return "en";
}

export function setLang(lang: Lang): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // localStorage full or unavailable
  }
}

export function hasCity(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(CITY_KEY) !== null;
  } catch {
    return true;
  }
}

export { DEFAULT_CITY };
