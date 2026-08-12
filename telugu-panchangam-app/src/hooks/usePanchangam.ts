"use client";

import { useEffect, useState } from "react";
import { getCity } from "@/lib/cache";
import type { DayPanchangam } from "@/engine/types";
import type { CityInfo } from "@/lib/cache";

interface UsePanchangamResult {
  data: DayPanchangam | null;
  loading: boolean;
  error: string | null;
  city: CityInfo;
}

export function usePanchangam(date: string): UsePanchangamResult {
  const [data, setData] = useState<DayPanchangam | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState<CityInfo>(getCity());

  useEffect(() => {
    setCity(getCity());
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const url = `/api/panchangam?date=${date}&lat=${city.lat}&lng=${city.lng}&tz=${encodeURIComponent(city.tz)}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
      })
      .then((json) => {
        if (!cancelled) setData(json.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [date, city.lat, city.lng, city.tz]);

  return { data, loading, error, city };
}

interface MonthDaySummary {
  date: string;
  gregorianDay: number;
  vara: { te: string; en: string; number: number };
  tithi: { te: string; en: string; number: number };
  nakshatra: { te: string; en: string; number: number };
  paksha: "shukla" | "krishna";
  moonPhaseEmoji: string;
  moonPhase: { illuminationPercent: number; phase: number };
  festivals: Array<{
    te: string;
    en: string;
    tier: 1 | 2 | 3;
    isSignificantEkadashi?: boolean;
    significance?: { te: string; en: string };
  }>;
  isEkadashi: boolean;
  isAmavasya: boolean;
  isPurnima: boolean;
}

interface MonthData {
  year: number;
  month: number;
  samvatsaram: { te: string; en: string; number: number };
  masa: { te: string; en: string; number: number; isAdhika: boolean };
  days: MonthDaySummary[];
}

interface UseMonthResult {
  data: MonthData | null;
  loading: boolean;
  error: string | null;
  city: CityInfo;
}

export function useMonth(year: number, month: number): UseMonthResult {
  const [data, setData] = useState<MonthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState<CityInfo>(getCity());

  useEffect(() => {
    setCity(getCity());
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const url = `/api/panchangam/month?year=${year}&month=${month}&lat=${city.lat}&lng=${city.lng}&tz=${encodeURIComponent(city.tz)}`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
      })
      .then((json) => {
        if (!cancelled) setData(json.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [year, month, city.lat, city.lng, city.tz]);

  return { data, loading, error, city };
}
