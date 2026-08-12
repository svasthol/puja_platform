"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getLang } from "@/lib/cache";
import { getMonthName } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

interface TimeNavProps {
  year: number;
  month: number;
}

export default function TimeNav({ year, month }: TimeNavProps) {
  const router = useRouter();
  const [lang, setLang] = useState<Lang>("en");
  const [yearInput, setYearInput] = useState(String(year));

  useEffect(() => {
    setLang(getLang());
  }, []);

  useEffect(() => {
    setYearInput(String(year));
  }, [year]);

  const goTo = useCallback(
    (y: number, m: number) => {
      // Wrap months
      if (m < 1) {
        m = 12;
        y -= 1;
      } else if (m > 12) {
        m = 1;
        y += 1;
      }
      router.push(`/${y}/${m}`);
    },
    [router]
  );

  const handleYearChange = useCallback(
    (value: string) => {
      setYearInput(value);
      const parsed = parseInt(value, 10);
      if (!isNaN(parsed)) {
        goTo(parsed, month);
      }
    },
    [goTo, month]
  );

  return (
    <nav className="flex items-center justify-center gap-4">
      <button
        onClick={() => goTo(year, month - 1)}
        className="px-3 py-1.5 rounded-md border border-label/30 hover:bg-label/10 transition-colors text-accent"
        aria-label="Previous month"
      >
        &larr;
      </button>

      <div className="text-center min-w-[200px]">
        <div className="font-playfair text-lg text-text-primary">
          {getMonthName(month, lang)}
        </div>
        {lang === "en" ? null : (
          <div className="font-noto-telugu text-sm text-text-secondary">
            {getMonthName(month, "te")}
          </div>
        )}
        <input
          type="number"
          value={yearInput}
          onChange={(e) => handleYearChange(e.target.value)}
          className="w-20 text-center bg-transparent border-b border-label/30 text-text-secondary text-sm focus:outline-none focus:border-accent"
          aria-label="Year"
        />
      </div>

      <button
        onClick={() => goTo(year, month + 1)}
        className="px-3 py-1.5 rounded-md border border-label/30 hover:bg-label/10 transition-colors text-accent"
        aria-label="Next month"
      >
        &rarr;
      </button>
    </nav>
  );
}
