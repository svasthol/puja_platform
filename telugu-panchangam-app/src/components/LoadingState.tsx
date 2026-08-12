"use client";

import { useEffect, useState } from "react";
import { getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";

interface LoadingStateProps {
  message?: string;
  messageTe?: string;
  lang?: Lang;
  variant?: "skeleton" | "spinner";
}

export default function LoadingState({
  message = "Calculating...",
  messageTe = "లెక్కిస్తోంది...",
  lang: langProp,
  variant = "spinner",
}: LoadingStateProps) {
  const [lang, setLang] = useState<Lang>(langProp ?? "en");

  useEffect(() => {
    if (!langProp) setLang(getLang());
  }, [langProp]);

  if (variant === "skeleton") {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6 animate-pulse">
        {/* Header skeleton */}
        <div className="flex flex-col items-center gap-2">
          <div className="skeleton h-8 w-48" />
          <div className="skeleton h-4 w-64" />
        </div>
        {/* 5 Anga cards */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-20 rounded-lg" />
          ))}
        </div>
        {/* 4 Sky timing cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton h-14 rounded-lg" />
          ))}
        </div>
        {/* Moon phase */}
        <div className="flex justify-center">
          <div className="skeleton h-20 w-20 rounded-full" />
        </div>
        {/* 3 inauspicious period cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-16 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-[40vh] gap-3">
      <div className="w-8 h-8 border-3 border-accent/20 border-t-accent rounded-full spinner" />
      <p className="font-lora text-label text-sm">
        {lang === "te" ? messageTe : message}
      </p>
    </div>
  );
}
