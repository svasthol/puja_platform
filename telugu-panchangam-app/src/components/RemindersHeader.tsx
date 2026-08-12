"use client";

import { useEffect, useState } from "react";
import { getLang } from "@/lib/cache";
import { REMINDERS } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

export default function RemindersHeader() {
  const [lang, setLang] = useState<Lang>("en");

  useEffect(() => {
    setLang(getLang());
  }, []);

  return (
    <div className="text-center mb-8">
      <h1 className="font-noto-telugu text-3xl text-accent mb-2">
        {REMINDERS.pageTitle.te}
      </h1>
      <p
        className={`text-lg mb-4 text-text-secondary ${
          lang === "te" ? "font-noto-telugu" : "font-playfair italic"
        }`}
      >
        {lang === "te" ? REMINDERS.pageSubtitle.te : REMINDERS.pageSubtitle.en}
      </p>
      <div className="w-16 h-px bg-accent mx-auto mb-6" />
      <p
        className={`text-text-secondary max-w-md mx-auto leading-relaxed ${
          lang === "te" ? "font-noto-telugu" : "font-lora"
        }`}
      >
        {REMINDERS.pageIntro[lang]}
      </p>
    </div>
  );
}
