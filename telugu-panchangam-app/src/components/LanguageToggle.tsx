"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getLang, setLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";

export default function LanguageToggle() {
  const router = useRouter();
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(getLang());
  }, []);

  const toggle = useCallback(() => {
    const next: Lang = lang === "en" ? "te" : "en";
    setLang(next);
    setLangState(next);
    router.refresh();
  }, [lang, router]);

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-1 px-3 py-2 min-h-[44px] rounded-md border border-label/30 hover:bg-label/10 transition-colors text-sm"
      aria-label="Toggle language"
    >
      <span
        className={`font-noto-telugu ${lang === "te" ? "text-accent font-semibold" : "text-text-secondary"}`}
      >
        తె
      </span>
      <span className="text-label">|</span>
      <span
        className={`font-lora ${lang === "en" ? "text-accent font-semibold" : "text-text-secondary"}`}
      >
        EN
      </span>
    </button>
  );
}
