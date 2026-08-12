"use client";

import { useEffect, useState } from "react";
import { getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";

interface ErrorStateProps {
  title?: string;
  titleTe?: string;
  message?: string;
  messageTe?: string;
  onRetry?: () => void;
  lang?: Lang;
}

export default function ErrorState({
  title = "Unable to load",
  titleTe = "లోడ్ చేయడం సాధ్యం కాలేదు",
  message = "Please check your connection and try again.",
  messageTe = "దయచేసి మీ కనెక్షన్ తనిఖీ చేసి మళ్ళీ ప్రయత్నించండి.",
  onRetry,
  lang: langProp,
}: ErrorStateProps) {
  const [lang, setLang] = useState<Lang>(langProp ?? "en");

  useEffect(() => {
    if (!langProp) setLang(getLang());
  }, [langProp]);

  return (
    <div className="flex items-center justify-center min-h-[40vh] px-4">
      <div className="text-center max-w-sm">
        <div className="text-4xl mb-4">&#x1F305;</div>
        <h2 className="font-playfair text-xl text-text-primary mb-2">
          {lang === "te" ? titleTe : title}
        </h2>
        <p className="font-lora text-text-secondary text-sm mb-6 leading-relaxed">
          {lang === "te" ? messageTe : message}
        </p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-6 py-3 rounded-lg bg-accent text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity min-h-[44px]"
          >
            {lang === "te" ? "మళ్ళీ ప్రయత్నించండి" : "Try Again"}
          </button>
        )}
        <p className="font-lora text-label/50 text-xs mt-4 italic leading-relaxed">
          {lang === "te"
            ? "ఈ సమస్య కొనసాగితే, సేవ తాత్కాలికంగా అందుబాటులో లేకపోవచ్చు."
            : "If this problem persists, the service may be temporarily unavailable."}
        </p>
      </div>
    </div>
  );
}
