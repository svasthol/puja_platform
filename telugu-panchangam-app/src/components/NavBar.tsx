"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";
import KeyboardShortcutsHelp from "./KeyboardShortcutsHelp";
import Toast from "./Toast";

type View = "month" | "day";

/** Parse /year/month or /year/month/day from pathname */
function parseRoute(pathname: string): {
  year: number;
  month: number;
  day: number;
  view: View;
} {
  const parts = pathname.split("/").filter(Boolean);
  const now = new Date();
  const parsedYear = parseInt(parts[0], 10);
  const parsedMonth = parseInt(parts[1], 10);
  const parsedDay = parseInt(parts[2], 10);
  const year = isNaN(parsedYear) ? now.getFullYear() : parsedYear;
  const month = isNaN(parsedMonth) ? now.getMonth() + 1 : parsedMonth;
  const day = isNaN(parsedDay) ? now.getDate() : parsedDay;
  const view: View = !isNaN(parsedDay) ? "day" : "month";
  return { year, month, day, view };
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { year, month, day, view } = parseRoute(pathname);

  const [dateInput, setDateInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(getLang());
  }, []);

  const handleShare = useCallback(() => {
    if (typeof window === "undefined") return;
    navigator.clipboard
      .writeText(window.location.href)
      .then(() => setToastVisible(true))
      .catch(() => {});
  }, []);

  useKeyboardShortcuts({
    year,
    month,
    day,
    view,
    onPrint: () => window.print(),
    onShare: handleShare,
    onLearnModal: () => setShowHelp(true),
  });

  // Today check
  const now = new Date();
  const todayYear = now.getFullYear();
  const todayMonth = now.getMonth() + 1;
  const todayDay = now.getDate();
  const isToday =
    year === todayYear && month === todayMonth && day === todayDay;

  // Don't show on home page (it redirects immediately)
  if (pathname === "/") {
    return (
      <>
        <KeyboardShortcutsHelp isOpen={showHelp} onClose={() => setShowHelp(false)} lang={lang} />
        <Toast
          message={lang === "te" ? "✓ లింక్ కాపీ అయింది!" : "✓ Link copied!"}
          visible={toastVisible}
          onHide={() => setToastVisible(false)}
        />
      </>
    );
  }

  const goToDay = (y: number, m: number, d: number) => {
    router.push(`/${y}/${m}/${d}`);
  };

  const goToMonth = (y: number, m: number) => {
    router.push(`/${y}/${m}`);
  };

  const goPrev = () => {
    if (view === "day") {
      let ny = year, nm = month, nd = day - 1;
      if (nd < 1) {
        nm -= 1;
        if (nm < 1) { nm = 12; ny -= 1; }
        nd = daysInMonth(ny, nm);
      }
      goToDay(ny, nm, nd);
    } else {
      let ny = year, nm = month - 1;
      if (nm < 1) { nm = 12; ny -= 1; }
      goToMonth(ny, nm);
    }
  };

  const goNext = () => {
    if (view === "day") {
      let ny = year, nm = month, nd = day + 1;
      const maxDay = daysInMonth(ny, nm);
      if (nd > maxDay) {
        nd = 1;
        nm += 1;
        if (nm > 12) { nm = 1; ny += 1; }
      }
      goToDay(ny, nm, nd);
    } else {
      let ny = year, nm = month + 1;
      if (nm > 12) { nm = 1; ny += 1; }
      goToMonth(ny, nm);
    }
  };

  const handleDateSubmit = (value: string) => {
    // Parse "24 Mar 2026" or "2026-03-24" or "24/03/2026"
    const cleaned = value.trim();
    if (!cleaned) return;

    // Try ISO format first
    const isoMatch = cleaned.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      goToDay(
        parseInt(isoMatch[1], 10),
        parseInt(isoMatch[2], 10),
        parseInt(isoMatch[3], 10)
      );
      setDateInput("");
      return;
    }

    // Try "DD MMM YYYY"
    const months: Record<string, number> = {
      jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
      jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
    };
    const dmy = cleaned.match(/^(\d{1,2})\s+(\w{3,})\s+(\d{4})$/i);
    if (dmy) {
      const m = months[dmy[2].slice(0, 3).toLowerCase()];
      if (m) {
        goToDay(parseInt(dmy[3], 10), m, parseInt(dmy[1], 10));
        setDateInput("");
        return;
      }
    }

    // Try "DD/MM/YYYY"
    const slash = cleaned.match(/^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$/);
    if (slash) {
      goToDay(
        parseInt(slash[3], 10),
        parseInt(slash[2], 10),
        parseInt(slash[1], 10)
      );
      setDateInput("");
    }
  };

  // Format current date for display
  const monthNames = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const displayDate = `${day} ${monthNames[month - 1]} ${year}`;

  return (
    <>
    <div className="bg-cream border-b border-label/10 no-print">
      <div className="max-w-4xl mx-auto px-4 py-2">
        {/* Top row: arrows + tabs + today */}
        <div className="flex items-center justify-between gap-2">
          {/* Left arrow */}
          <button
            onClick={goPrev}
            className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-label/10 transition-colors text-accent text-lg"
            aria-label={view === "day" ? "Previous day" : "Previous month"}
          >
            &larr;
          </button>

          {/* Centre: tabs */}
          <div className="flex items-center gap-1 relative">
            <button
              onClick={() => goToMonth(year, month)}
              className={`px-3 py-2 min-h-[40px] text-sm rounded-md transition-all ${
                view === "month"
                  ? "bg-accent/10 text-accent font-semibold"
                  : "text-text-secondary hover:bg-label/10"
              }`}
            >
              <span className="mr-1">&#x1F5D3;</span>
              Month
            </button>
            <button
              onClick={() => goToDay(year, month, day)}
              className={`px-3 py-2 min-h-[40px] text-sm rounded-md transition-all ${
                view === "day"
                  ? "bg-accent/10 text-accent font-semibold"
                  : "text-text-secondary hover:bg-label/10"
              }`}
            >
              <span className="mr-1">&#x1F4C5;</span>
              Day
            </button>
          </div>

          {/* Right: next arrow + today button */}
          <div className="flex items-center gap-1">
            <button
              onClick={goNext}
              className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-label/10 transition-colors text-accent text-lg"
              aria-label={view === "day" ? "Next day" : "Next month"}
            >
              &rarr;
            </button>
            {!isToday && (
              <button
                onClick={() => goToDay(todayYear, todayMonth, todayDay)}
                className="px-2 py-1 text-xs rounded-md border border-accent/30 text-accent hover:bg-accent/10 transition-colors font-lora"
              >
                Today
              </button>
            )}
            <button
              onClick={() => setShowHelp(true)}
              className="hidden md:flex items-center gap-1 ml-1 px-1.5 text-xs text-label/50 hover:text-accent transition-colors no-print"
              title="Keyboard shortcuts (?)"
              aria-label="Keyboard shortcuts"
            >
              <span className="text-base">&#x2328;&#xFE0F;</span>
              <span className="font-mono">?</span>
            </button>
          </div>
        </div>

        {/* Date jump input */}
        <div className="flex justify-center mt-1.5">
          <input
            ref={inputRef}
            type="text"
            value={dateInput}
            onChange={(e) => setDateInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleDateSubmit(dateInput);
            }}
            placeholder={`${displayDate} — jump to any date...`}
            className="w-60 text-center text-xs bg-transparent border-b border-label/20 text-text-secondary placeholder:text-label/40 focus:outline-none focus:border-accent py-0.5 font-lora"
          />
        </div>
      </div>
    </div>
    <KeyboardShortcutsHelp isOpen={showHelp} onClose={() => setShowHelp(false)} lang={lang} />
    <Toast
      message={lang === "te" ? "✓ లింక్ కాపీ అయింది!" : "✓ Link copied!"}
      visible={toastVisible}
      onHide={() => setToastVisible(false)}
    />
    </>
  );
}
