"use client";

import { useEffect, useState, useCallback } from "react";
import { getCity, getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";
import type { MuhurtamWindow } from "@/engine/muhurtam";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";

const DAY_OPTIONS = [1, 3, 7, 14, 30];

const MONTH_NAMES_EN = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTH_NAMES_TE = [
  "", "జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్",
  "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్",
];

function formatDate(dateStr: string, lang: Lang): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  const weekdays =
    lang === "te"
      ? ["ఆదివారం", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం"]
      : ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const months = lang === "te" ? MONTH_NAMES_TE : MONTH_NAMES_EN;
  return `${weekdays[dt.getDay()]}, ${d} ${months[m]} ${y}`;
}

function formatTime(isoStr: string): string {
  const match = isoStr.match(/T(\d{2}):(\d{2})/);
  if (!match) return "--:--";
  return `${match[1]}:${match[2]}`;
}

function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

function groupByDate(windows: MuhurtamWindow[]): Map<string, MuhurtamWindow[]> {
  const map = new Map<string, MuhurtamWindow[]>();
  for (const w of windows) {
    const arr = map.get(w.date) ?? [];
    arr.push(w);
    map.set(w.date, arr);
  }
  return map;
}

export default function MuhurtamFinder() {
  const [lang, setLang] = useState<Lang>("en");
  const [fromDate, setFromDate] = useState(todayStr());
  const [days, setDays] = useState(7);
  const [windows, setWindows] = useState<MuhurtamWindow[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [cityName, setCityName] = useState("Melbourne");

  useEffect(() => {
    setLang(getLang());
    setCityName(getCity().name);
  }, []);

  const search = useCallback(async () => {
    setLoading(true);
    setSearched(true);
    setFetchError(null);
    const city = getCity();
    setCityName(city.name);
    try {
      const res = await fetch(
        `/api/muhurtam?from=${fromDate}&days=${days}&lat=${city.lat}&lng=${city.lng}&tz=${encodeURIComponent(city.tz)}`
      );
      if (!res.ok) throw new Error("Service temporarily unavailable");
      const json = await res.json();
      if (json.data) setWindows(json.data);
      else setWindows([]);
    } catch (err) {
      setWindows([]);
      setFetchError(err instanceof Error ? err.message : "Unable to find muhurtam windows");
    }
    setLoading(false);
  }, [fromDate, days]);

  const grouped = groupByDate(windows);

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-6">
        <h1 className="font-noto-telugu text-3xl text-accent mb-1">
          ముహూర్తం
        </h1>
        <p className="font-playfair italic text-text-secondary text-lg mb-1">
          Muhurtam Finder
        </p>
        <p className="text-xs text-label font-lora">
          {lang === "te"
            ? "శుభ ముహూర్త సమయాలు కనుగొనండి"
            : "Find auspicious time windows"}
        </p>
        <div className="w-16 h-px bg-accent mx-auto mt-4" />
      </div>

      {/* Form */}
      <div className="bg-white/50 rounded-lg border border-label/10 p-4 mb-6">
        {/* From date */}
        <div className="mb-3">
          <label className="block text-xs text-label font-lora mb-1">
            {lang === "te" ? "తేది నుండి" : "From date"}
          </label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
          />
        </div>

        {/* Days */}
        <div className="mb-4">
          <label className="block text-xs text-label font-lora mb-1">
            {lang === "te" ? "రోజులు" : "Number of days"}
          </label>
          <div className="flex gap-2">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1 text-sm rounded-md border transition-colors font-lora ${
                  days === d
                    ? "bg-accent text-white border-accent"
                    : "border-label/20 text-text-secondary hover:bg-label/10"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* City indicator */}
        <p className="text-xs text-label font-lora mb-3">
          {lang === "te" ? `నగరం: ${cityName}` : `City: ${cityName}`}
        </p>

        {/* Search button */}
        <button
          onClick={search}
          disabled={loading}
          className="w-full py-2.5 rounded-lg bg-header-grad text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {loading
            ? lang === "te"
              ? "వెతుకుతోంది..."
              : "Searching..."
            : lang === "te"
              ? "ముహూర్తం కనుగొనండి"
              : "Find Muhurtam"}
        </button>
      </div>

      {/* Loading spinner in results area */}
      {loading && (
        <LoadingState variant="spinner" message="Searching..." messageTe="వెతుకుతోంది..." lang={lang} />
      )}

      {/* Error */}
      {!loading && fetchError && (
        <ErrorState
          title="Unable to find muhurtam"
          titleTe="ముహూర్తం కనుగొనడం సాధ్యం కాలేదు"
          message={fetchError}
          onRetry={search}
          lang={lang}
        />
      )}

      {/* Empty results */}
      {searched && !loading && !fetchError && windows.length === 0 && (
        <p className="text-center text-label font-lora mt-8">
          {lang === "te"
            ? "ఈ కాలంలో శుభ ముహూర్తాలు కనుగొనబడలేదు. వేరే తేదీ పరిధి ప్రయత్నించండి."
            : "No auspicious windows found in this period. Try a different date range."}
        </p>
      )}

      {!loading &&
        Array.from(grouped.entries())
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([date, dateWindows]) => (
            <div key={date} className="mb-6">
              {/* Date header */}
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-label/15" />
                <h2 className="text-sm font-semibold text-label font-lora">
                  {formatDate(date, lang)}
                </h2>
                <div className="h-px flex-1 bg-label/15" />
              </div>

              <div className="space-y-2">
                {dateWindows.map((w, i) => {
                  const borderClass =
                    w.quality === "excellent"
                      ? "border-gold/40"
                      : "border-accent/30";
                  const badgeBg =
                    w.quality === "excellent" ? "bg-gold/10" : "bg-accent/10";
                  const badgeText =
                    w.quality === "excellent" ? "text-gold" : "text-accent";
                  const qualityLabel =
                    w.quality === "excellent"
                      ? lang === "te"
                        ? "అత్యుత్తమం"
                        : "Excellent"
                      : lang === "te"
                        ? "మంచిది"
                        : "Good";

                  return (
                    <div
                      key={`${date}-${i}`}
                      className={`rounded-lg border p-3 ${borderClass}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded font-semibold ${badgeBg} ${badgeText} font-lora`}
                        >
                          {qualityLabel}
                        </span>
                        <span className="text-xs text-label font-lora">
                          {formatDuration(w.durationMinutes)}
                        </span>
                      </div>
                      <p className="text-lg font-semibold text-text-primary font-lora">
                        {formatTime(w.start)} — {formatTime(w.end)}
                      </p>
                      <div className="mt-2 space-y-0.5">
                        <p className="text-sm">
                          <span className="font-noto-telugu text-text-secondary">
                            {w.nakshatra.te}
                          </span>
                          <span className="text-label mx-1">&middot;</span>
                          <span className="font-lora text-text-secondary">
                            {w.nakshatra.en} Nakshatra
                          </span>
                        </p>
                        <p className="text-sm">
                          <span className="font-noto-telugu text-text-secondary">
                            {w.yoga.te}
                          </span>
                          <span className="text-label mx-1">&middot;</span>
                          <span className="font-lora text-text-secondary">
                            {w.yoga.en} Yoga
                          </span>
                        </p>
                        <p className="text-sm">
                          <span className="font-noto-telugu text-text-secondary">
                            {w.tithi.te}
                          </span>
                          <span className="text-label mx-1">&middot;</span>
                          <span className="font-lora text-text-secondary">
                            {w.tithi.en} Tithi
                          </span>
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
    </div>
  );
}
