"use client";

import { getWeekdayHeaders } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

interface PrintDay {
  date: string;
  gregorianDay: number;
  tithi: { te: string; en: string; number: number };
  moonPhaseEmoji: string;
  festivals: Array<{ te: string; en: string; tier: 1 | 2 | 3 }>;
  isAmavasya: boolean;
}

interface PrintableCalendarProps {
  year: number;
  month: number;
  days: PrintDay[];
  samvatsaram: { te: string; en: string };
  masa: { te: string; en: string };
  cityName: string;
  lang: Lang;
}

export default function PrintableCalendar({
  year,
  month,
  days,
  samvatsaram,
  masa,
  cityName,
  lang,
}: PrintableCalendarProps) {
  const weekdaysTe = getWeekdayHeaders("te");
  const weekdaysEn = getWeekdayHeaders("en");
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay();

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  return (
    <div className="hidden print:block print-calendar">
      <div className="print-header">
        <div className="font-noto-telugu text-2xl font-bold" style={{ color: "#C04020" }}>
          {masa.te} &middot; {samvatsaram.te}
        </div>
        <div className="font-playfair italic text-lg" style={{ color: "#6B3010" }}>
          {masa.en} {year} &middot; {samvatsaram.en}
        </div>
        <div className="text-sm" style={{ color: "#6B3010" }}>
          తెలుగు పంచాంగం — Telugu Panchangam
        </div>
        <div className="text-xs" style={{ color: "#8B4020" }}>
          Calculated for {cityName}
        </div>
      </div>

      <div className="calendar-grid">
        {weekdaysTe.map((te, i) => (
          <div
            key={i}
            className="calendar-day text-center"
            style={{ background: "#f5f5f5", fontWeight: "bold", minHeight: "auto" }}
          >
            <div className="font-noto-telugu" style={{ fontSize: "9pt" }}>{te}</div>
            <div style={{ fontSize: "7pt", color: "#8B4020" }}>{weekdaysEn[i]}</div>
          </div>
        ))}

        {Array.from({ length: firstDayOfWeek }).map((_, i) => (
          <div key={`empty-${i}`} className="calendar-day" />
        ))}

        {days.map((day) => {
          const classes = ["calendar-day"];
          if (day.date === todayStr) classes.push("today");
          if (day.isAmavasya) classes.push("amavasya");
          if (day.festivals.length > 0) classes.push("festival");
          const fest = day.festivals[0];
          return (
            <div key={day.date} className={classes.join(" ")}>
              <div className="flex justify-between items-start">
                <span className="day-number">{day.gregorianDay}</span>
                <span className="day-moon">{day.moonPhaseEmoji}</span>
              </div>
              <div className="day-tithi font-noto-telugu">{day.tithi.te}</div>
              {fest && (
                <div className="day-festival">
                  {lang === "te" ? fest.te : fest.en}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="print-footer">
        <div>తెలుగు పంచాంగం &middot; Telugu Panchangam</div>
        <div>telugupanchangam.app &middot; Free, open-source, for the community</div>
        <div style={{ color: "#8B4020" }}>
          Timings calculated for {cityName}. Dates may differ from Indian printed calendars due to timezone differences.
        </div>
      </div>
    </div>
  );
}
