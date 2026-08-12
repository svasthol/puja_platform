"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCity, getLang } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";
import { getWeekdayHeaders } from "@/lib/i18n";
import Tooltip from "./Tooltip";
import LocationDisclaimer from "./LocationDisclaimer";
import { TOOLTIPS } from "@/lib/tooltips";
import type { Lang } from "@/lib/i18n";

interface DaySummary {
  date: string;
  gregorianDay: number;
  tithi: { te: string; en: string; number: number };
  nakshatra: { te: string; en: string; number: number };
  paksha: "shukla" | "krishna";
  moonPhaseEmoji: string;
  festivals: Array<{
    te: string;
    en: string;
    tier: 1 | 2 | 3;
    isSignificantEkadashi?: boolean;
  }>;
  isEkadashi: boolean;
  isAmavasya: boolean;
  isPurnima: boolean;
}

interface CalendarGridProps {
  year: number;
  month: number;
  days: DaySummary[];
}

export default function CalendarGrid({
  year,
  month,
  days,
}: CalendarGridProps) {
  const [lang, setLang] = useState<Lang>("en");
  const [city, setCityState] = useState<CityInfo | null>(null);

  useEffect(() => {
    setLang(getLang());
    setCityState(getCity());
  }, []);

  const headers = getWeekdayHeaders(lang);

  // Day of week for first day (0=Sun)
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay();

  // Today's date string for highlighting
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  return (
    <div className="w-full">
      {city && (
        <div className="mb-3">
          <LocationDisclaimer
            cityName={city.name}
            tz={city.tz}
            lang={lang}
            variant="day"
          />
        </div>
      )}

      {/* Mobile hint — only on small screens */}
      <div className="sm:hidden text-[11px] text-label/70 italic font-lora text-center pb-1.5">
        {lang === "te" ? "పండుగలకు రోజు నొక్కండి" : "Tap any day to see festivals"}
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-px mb-1">
        {headers.map((h, i) => (
          <div
            key={i}
            className={`text-center text-xs font-semibold py-2 ${lang === "te" ? "font-noto-telugu" : "font-lora"} text-label`}
          >
            {i === 0 ? (
              <span className="inline-flex items-center gap-0.5">
                {h}
                <Tooltip content={TOOLTIPS.calendar[lang]} position="bottom">
                  <span className="text-label/30 cursor-help text-[10px]">&oplus;</span>
                </Tooltip>
              </span>
            ) : (
              h
            )}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-px">
        {/* Empty cells before month starts */}
        {Array.from({ length: firstDayOfWeek }).map((_, i) => (
          <div key={`empty-${i}`} className="min-h-[80px]" />
        ))}

        {/* Day cells */}
        {days.map((day) => {
          const isToday = day.date === todayStr;
          const hasFestival = day.festivals.length > 0;

          let bgClass = "bg-cream hover:bg-label/5";
          if (day.isAmavasya) bgClass = "bg-text-primary/5 hover:bg-text-primary/10";
          else if (day.isPurnima) bgClass = "bg-gold/10 hover:bg-gold/15";
          else if (day.isEkadashi) bgClass = "bg-auspicious/5 hover:bg-auspicious/10";
          // Mobile-only faint tint for any other festival day so the
          // dot doesn't feel orphaned without a name beside it.
          else if (hasFestival) bgClass = "bg-accent/[0.04] sm:bg-cream hover:bg-accent/10";

          return (
            <Link
              key={day.date}
              href={`/${year}/${month}/${day.gregorianDay}`}
              className={`group relative min-h-[80px] p-1.5 rounded-md border transition-all duration-150
                hover:-translate-y-0.5 hover:shadow-md hover:shadow-label/10 active:animate-tap
                ${isToday ? "border-accent border-2 animate-today-pulse" : "border-transparent"} ${bgClass}`}
            >
              {/* Hover tooltip */}
              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 rounded bg-text-primary text-cream text-[10px] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                <span className="font-noto-telugu">{day.tithi.te}</span>
                <span className="mx-1">·</span>
                <span className="font-lora">{day.tithi.en}</span>
              </div>

              {/* Top row: date + moon emoji */}
              <div className="flex justify-between items-start">
                <span className="text-sm font-semibold text-text-primary font-lora">
                  {day.gregorianDay}
                </span>
                <span className="text-xs">{day.moonPhaseEmoji}</span>
              </div>

              {/* Tithi name */}
              <div className="mt-0.5">
                <span className="text-[11px] font-noto-telugu text-text-secondary leading-tight block">
                  {day.tithi.te}
                </span>
              </div>

              {/* Festival badges */}
              {hasFestival && (
                <>
                  {/* Mobile (< sm): dots only — no truncated text */}
                  <div className="flex items-center gap-0.5 mt-0.5 sm:hidden">
                    {day.festivals.slice(0, 3).map((f, fi) => {
                      const dotColor = f.isSignificantEkadashi
                        ? "bg-gold"
                        : f.tier === 1
                          ? "bg-gold"
                          : f.tier === 2
                            ? "bg-accent"
                            : "bg-label/40";
                      return (
                        <span
                          key={fi}
                          className={`w-1.5 h-1.5 rounded-full ${dotColor} inline-block flex-shrink-0`}
                        />
                      );
                    })}
                    {day.festivals.length > 3 && (
                      <span className="text-[9px] text-label leading-none">+</span>
                    )}
                  </div>

                  {/* Tablet/Desktop (sm+): dot + name */}
                  <div className="hidden sm:block mt-0.5 space-y-0.5">
                    {day.festivals.slice(0, 2).map((f, fi) => {
                      const isSig = f.isSignificantEkadashi;
                      const dotColor = isSig
                        ? "bg-gold"
                        : f.tier === 1
                          ? "bg-gold"
                          : f.tier === 2
                            ? "bg-accent"
                            : "bg-label/40";
                      const textColor = isSig
                        ? "text-gold font-bold"
                        : f.tier === 1
                          ? "text-gold"
                          : f.tier === 2
                            ? "text-accent"
                            : "text-label";
                      return (
                        <div key={fi} className="flex items-center gap-0.5">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${dotColor} inline-block flex-shrink-0`}
                          />
                          <span
                            className={`text-[10px] ${textColor} truncate max-w-[70px] lg:max-w-none ${
                              lang === "te" ? "font-noto-telugu" : "font-lora"
                            }`}
                          >
                            {isSig ? "✨ " : ""}
                            {lang === "te" ? f.te : f.en}
                          </span>
                        </div>
                      );
                    })}
                    {day.festivals.length > 2 && (
                      <span className="text-[9px] text-label">
                        +{day.festivals.length - 2}
                      </span>
                    )}
                  </div>
                </>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
