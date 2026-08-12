"use client";

import { useEffect, useState } from "react";
import { useMonth } from "@/hooks/usePanchangam";
import { getLang } from "@/lib/cache";
import CalendarGrid from "@/components/CalendarGrid";
import PrintableCalendar from "@/components/PrintableCalendar";
import TimeNav from "@/components/TimeNav";
import LoadingState from "@/components/LoadingState";
import ErrorState from "@/components/ErrorState";
import type { Lang } from "@/lib/i18n";

interface MonthPageProps {
  params: { year: string; month: string };
}

export default function MonthPage({ params }: MonthPageProps) {
  const year = parseInt(params.year, 10);
  const month = parseInt(params.month, 10);
  const { data, loading, error, city } = useMonth(year, month);
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    setLang(getLang());
  }, []);

  if (loading) {
    return (
      <div className="py-6 px-4 max-w-4xl mx-auto">
        <LoadingState
          variant="spinner"
          message="Loading calendar..."
          messageTe="క్యాలెండర్ లోడ్ అవుతోంది..."
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="py-6 px-4 max-w-4xl mx-auto">
        <ErrorState
          title="Unable to load calendar"
          titleTe="క్యాలెండర్ లోడ్ చేయడం సాధ్యం కాలేదు"
          message={error ?? "Failed to load month data."}
          messageTe={error ?? "నెల డేటా లోడ్ చేయడం విఫలమైంది."}
          onRetry={() => window.location.reload()}
          lang={lang}
        />
      </div>
    );
  }

  return (
    <div className="py-6 px-4 max-w-4xl mx-auto space-y-6">
      <div className="text-center space-y-1">
        <div className="font-noto-telugu text-text-secondary text-sm">
          {data.samvatsaram.te} &middot; {data.masa.te}
        </div>
        {lang === "en" && (
          <div className="font-playfair italic text-text-secondary text-xs">
            {data.samvatsaram.en} &middot; {data.masa.en}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 no-print">
        <div className="flex-1">
          <TimeNav year={year} month={month} />
        </div>
        <button
          onClick={() => window.print()}
          className="no-print flex items-center gap-1.5 px-3 py-2 rounded-lg border border-accent/30 text-text-secondary text-sm font-lora hover:border-accent hover:text-accent transition-colors min-h-[44px]"
          title="Print this month's calendar"
          aria-label="Print"
        >
          <span aria-hidden="true">&#x1F5A8;&#xFE0F;</span>
          <span className={`hidden sm:inline ${lang === "te" ? "font-noto-telugu" : ""}`}>
            {lang === "te" ? "ముద్రించు" : "Print"}
          </span>
        </button>
      </div>

      <div className="print:hidden">
        <CalendarGrid year={year} month={month} days={data.days} />
      </div>

      <PrintableCalendar
        year={year}
        month={month}
        days={data.days}
        samvatsaram={data.samvatsaram}
        masa={data.masa}
        cityName={city.name}
        lang={lang}
      />
    </div>
  );
}
