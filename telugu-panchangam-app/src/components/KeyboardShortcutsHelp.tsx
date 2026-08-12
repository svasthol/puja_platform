"use client";

import { useEffect } from "react";
import type { Lang } from "@/lib/i18n";

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
  lang: Lang;
}

interface Row {
  keys: string[];
  en: string;
  te: string;
}

const NAV_ROWS: Row[] = [
  { keys: ["←", "→"], en: "Previous / Next", te: "ముందు / తరువాత" },
  { keys: ["T"], en: "Today", te: "ఈ రోజు" },
  { keys: ["M"], en: "Month view", te: "నెల వీక్షణ" },
  { keys: ["D"], en: "Day view", te: "రోజు వీక్షణ" },
];

const PAGE_ROWS: Row[] = [
  { keys: ["F"], en: "Festivals", te: "పండుగలు" },
  { keys: ["U"], en: "Muhurtam", te: "ముహూర్తం" },
  { keys: ["N"], en: "Nakshatra", te: "నక్షత్రం" },
  { keys: ["R"], en: "Reminders", te: "రిమైండర్లు" },
  { keys: ["/"], en: "How it works", te: "ఎలా పని చేస్తుంది" },
  { keys: ["S"], en: "Share / Copy URL", te: "షేర్ / లింక్ కాపీ" },
  { keys: ["P"], en: "Print (month only)", te: "ముద్రణ (నెల మాత్రమే)" },
  { keys: ["?"], en: "This help screen", te: "ఈ సహాయ స్క్రీన్" },
  { keys: ["Esc"], en: "Close modal", te: "మోడల్ మూసివేయండి" },
];

function KeyBadge({ k }: { k: string }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[32px] h-7 px-2 rounded-md bg-accent/15 text-accent font-mono text-xs font-semibold border border-accent/20">
      {k}
    </kbd>
  );
}

function ShortcutRow({ row, lang }: { row: Row; lang: Lang }) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="flex items-center gap-1 min-w-[80px]">
        {row.keys.map((k, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <span className="text-label/50 text-xs">·</span>}
            <KeyBadge k={k} />
          </span>
        ))}
      </div>
      <div className={`text-sm text-text-secondary ${lang === "te" ? "font-noto-telugu" : "font-lora"}`}>
        {row[lang]}
      </div>
    </div>
  );
}

export default function KeyboardShortcutsHelp({ isOpen, onClose, lang }: KeyboardShortcutsHelpProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[250] flex items-center justify-center p-4 bg-black/50 no-print"
      onClick={onClose}
    >
      <div
        className="bg-cream max-w-2xl w-full rounded-xl shadow-2xl border border-label/10 p-6 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="font-playfair text-2xl text-accent">
              {lang === "te" ? "కీబోర్డ్ సత్వర మార్గాలు" : "Keyboard Shortcuts"}
            </h2>
            <p className={`text-xs text-label mt-1 ${lang === "te" ? "font-noto-telugu" : "font-lora"}`}>
              {lang === "te" ? "ఈ యాప్‌ను వేగంగా ఉపయోగించడానికి" : "Navigate the app faster"}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-label/10 text-text-secondary text-lg"
          >
            &times;
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-label mb-2">
              {lang === "te" ? "నావిగేషన్" : "Navigation"}
            </h3>
            <div className="divide-y divide-label/5">
              {NAV_ROWS.map((r, i) => (
                <ShortcutRow key={i} row={r} lang={lang} />
              ))}
            </div>
          </section>
          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-label mb-2">
              {lang === "te" ? "పేజీలు & UI" : "Pages & UI"}
            </h3>
            <div className="divide-y divide-label/5">
              {PAGE_ROWS.map((r, i) => (
                <ShortcutRow key={i} row={r} lang={lang} />
              ))}
            </div>
          </section>
        </div>

        <p className={`mt-6 text-xs text-label/70 italic text-center ${lang === "te" ? "font-noto-telugu" : "font-lora"}`}>
          {lang === "te"
            ? "ఫారమ్‌లో టైప్ చేస్తున్నప్పుడు సత్వర మార్గాలు పని చేయవు."
            : "Shortcuts are disabled when typing in a form field."}
        </p>
      </div>
    </div>
  );
}
