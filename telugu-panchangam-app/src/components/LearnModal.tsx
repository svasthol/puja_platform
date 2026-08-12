"use client";

import { useEffect, useState } from "react";
import { getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";

interface LearnModalProps {
  onClose: () => void;
}

const ELEMENTS = [
  { te: "తిథి", en: "Tithi", desc: "The lunar day", descTe: "చంద్రుని దశ" },
  { te: "వారం", en: "Vara", desc: "The weekday", descTe: "వారపు రోజు" },
  { te: "నక్షత్రం", en: "Nakshatra", desc: "The Moon's star cluster", descTe: "చంద్రుని నక్షత్ర సమూహం" },
  { te: "యోగం", en: "Yoga", desc: "The combined quality", descTe: "సమిష్టి గుణం" },
  { te: "కరణం", en: "Karana", desc: "Half a lunar day", descTe: "తిథిలో సగం భాగం" },
];

export default function LearnModal({ onClose }: LearnModalProps) {
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    setLang(getLang());
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-cream rounded-xl shadow-xl max-w-md w-full p-6 animate-fade-up relative">
        <button
          onClick={onClose}
          className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center rounded-full hover:bg-label/10 text-text-secondary text-lg"
          aria-label="Close"
        >
          &times;
        </button>

        <h2 className="font-noto-telugu text-xl text-accent mb-1 text-center">
          పంచాంగం అంటే ఏమిటి?
        </h2>
        <p className="font-playfair italic text-text-secondary text-sm text-center mb-4">
          What is Panchangam?
        </p>

        <p className="font-lora text-text-secondary text-sm leading-relaxed mb-4">
          {lang === "te"
            ? "పంచాంగం (పంచ + అంగం) అంటే ఐదు అంగాలు. ఈ ఐదు అంశాలు వేద సంప్రదాయం ప్రకారం ఏ సమయాన్నైనా వివరిస్తాయి:"
            : "Panchangam (Pancha + Anga) means five limbs. These five elements describe any moment in time according to Vedic tradition:"}
        </p>

        <table className="w-full text-sm mb-4">
          <tbody>
            {ELEMENTS.map((el) => (
              <tr key={el.en} className="border-b border-label/10 last:border-b-0">
                <td className="py-2 pr-2 font-noto-telugu text-accent">{el.te}</td>
                <td className="py-2 pr-2 font-playfair italic text-text-primary">{el.en}</td>
                <td className="py-2 font-lora text-text-secondary text-xs">
                  {lang === "te" ? el.descTe : el.desc}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="font-lora text-label/60 text-xs italic leading-relaxed mb-4">
          {lang === "te"
            ? "అన్ని సమయాలు మీ నగరం యొక్క స్థానిక సూర్యోదయం ఆధారంగా లెక్కించబడతాయి — భారత ప్రామాణిక సమయం కాదు."
            : "All timings are calculated from local sunrise for your city — not Indian Standard Time."}
        </p>

        <button
          onClick={onClose}
          className="w-full py-2.5 rounded-lg bg-accent text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity"
        >
          {lang === "te" ? "మూసివేయండి" : "Close"}
        </button>
      </div>
    </div>
  );
}
