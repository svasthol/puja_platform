"use client";

import { isNonIndianTimezone } from "@/engine/timezone";
import type { Lang } from "@/lib/i18n";

interface LocationDisclaimerProps {
  cityName: string;
  tz: string;
  lang: Lang;
  variant: "day" | "festival";
}

export default function LocationDisclaimer({
  cityName,
  tz,
  lang,
  variant,
}: LocationDisclaimerProps) {
  if (!isNonIndianTimezone(tz)) return null;

  const messages = {
    day: {
      en: `Showing timings for ${cityName}. Tithi transitions may fall on different dates than printed Indian Panchangams due to timezone differences.`,
      te: `${cityName} కోసం సమయాలు చూపిస్తోంది. సమయ మండల తేడాల వల్ల తిథి మారే సమయం భారత పంచాంగాలలో వేరే తేదీన ఉండవచ్చు.`,
    },
    festival: {
      en: `Festival dates are calculated for ${cityName}. Some festivals may fall one day earlier or later than the date observed in India.`,
      te: `పండుగల తేదీలు ${cityName} కోసం లెక్కించబడ్డాయి. కొన్ని పండుగలు భారతదేశంలో జరుపుకునే తేదీకంటే ఒక రోజు ముందు లేదా వెనుక పడవచ్చు.`,
    },
  };

  const text = messages[variant][lang];

  return (
    <div
      className="flex items-start gap-2 rounded-lg text-sm font-lora text-text-secondary"
      style={{
        background: "rgba(212, 96, 58, 0.06)",
        borderLeft: "3px solid rgba(212, 96, 58, 0.3)",
        padding: "10px 14px",
      }}
      role="note"
    >
      <span aria-hidden="true">&#x1F30D;</span>
      <span className={lang === "te" ? "font-noto-telugu leading-relaxed" : "leading-relaxed"}>
        {text}
      </span>
    </div>
  );
}
