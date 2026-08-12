"use client";

import { useEffect, useState } from "react";
import { getCity } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";

export default function CitySearch() {
  const [city, setCityState] = useState<CityInfo | null>(null);

  useEffect(() => {
    setCityState(getCity());
  }, []);

  const handleClick = () => {
    window.dispatchEvent(new Event("city-change-requested"));
  };

  return (
    <button
      onClick={handleClick}
      className="flex items-center gap-1 px-3 py-2 min-h-[44px] rounded-md border border-label/30 hover:bg-label/10 transition-colors text-sm text-text-secondary"
      aria-label="Change city"
    >
      <span className="text-base">&#x1f4cd;</span>
      <span className="font-lora">{city?.name ?? "Melbourne"}</span>
      <span className="text-xs text-label/50 ml-0.5">&#x270E;</span>
    </button>
  );
}
