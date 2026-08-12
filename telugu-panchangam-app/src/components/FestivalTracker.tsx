"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { getCity, getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";
import type { Festival } from "@/engine/types";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import LocationDisclaimer from "./LocationDisclaimer";

type Filter = "all" | "tier1" | "regional" | "ekadashi" | "amavasya";

const FILTERS: { key: Filter; te: string; en: string }[] = [
  { key: "all", te: "అన్నీ", en: "All" },
  { key: "tier1", te: "ప్రధాన", en: "Major" },
  { key: "regional", te: "ప్రాంతీయ", en: "Regional" },
  { key: "ekadashi", te: "ఏకాదశి", en: "Ekadashi" },
  { key: "amavasya", te: "అమావాస్య", en: "Amavasya" },
];

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
      ? ["ఆది", "సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని"]
      : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = lang === "te" ? MONTH_NAMES_TE : MONTH_NAMES_EN;
  return `${weekdays[dt.getDay()]}, ${d} ${months[m]} ${y}`;
}

function daysBetween(from: string, to: string): number {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return Math.round(
    (new Date(ty, tm - 1, td).getTime() - new Date(fy, fm - 1, fd).getTime()) /
      86400000
  );
}

function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}

function filterFestivals(festivals: Festival[], filter: Filter): Festival[] {
  switch (filter) {
    case "tier1":
      return festivals.filter(
        (f) =>
          f.tier === 1 &&
          !f.en.includes("Ekadashi") &&
          f.en !== "Amavasya" &&
          f.en !== "Purnima" &&
          !f.en.endsWith("Amavasya") &&
          !f.en.endsWith("Purnima")
      );
    case "regional":
      return festivals.filter((f) => f.tier === 2);
    case "ekadashi":
      return festivals.filter((f) => f.en.includes("Ekadashi"));
    case "amavasya":
      return festivals.filter(
        (f) => f.en === "Amavasya" || f.en.endsWith("Amavasya")
      );
    default:
      return festivals;
  }
}

function groupByMonth(
  festivals: Festival[]
): Map<number, Festival[]> {
  const map = new Map<number, Festival[]>();
  for (const f of festivals) {
    if (!f.date) continue;
    const month = parseInt(f.date.split("-")[1], 10);
    const arr = map.get(month) ?? [];
    arr.push(f);
    map.set(month, arr);
  }
  return map;
}

export default function FestivalTracker() {
  const [lang, setLang] = useState<Lang>("en");
  const [year, setYear] = useState(new Date().getFullYear());
  const [festivals, setFestivals] = useState<Festival[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [cityName, setCityName] = useState("Melbourne");
  const [cityTz, setCityTz] = useState("Australia/Melbourne");
  const nextRef = useRef<HTMLDivElement>(null);

  const today = todayStr();

  const fetchFestivals = useCallback(async (y: number) => {
    setLoading(true);
    setFetchError(null);
    const city = getCity();
    setCityName(city.name);
    setCityTz(city.tz);
    try {
      const res = await fetch(
        `/api/festivals?year=${y}&lat=${city.lat}&lng=${city.lng}&tz=${encodeURIComponent(city.tz)}`
      );
      if (!res.ok) throw new Error("Service temporarily unavailable");
      const json = await res.json();
      if (json.data) setFestivals(json.data);
    } catch (err) {
      setFestivals([]);
      setFetchError(err instanceof Error ? err.message : "Unable to load festivals");
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    setLang(getLang());
    fetchFestivals(year);
  }, [year, fetchFestivals]);

  // Scroll to next upcoming festival on load
  useEffect(() => {
    if (!loading && nextRef.current) {
      nextRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [loading, filter]);

  const filtered = filterFestivals(festivals, filter);
  const grouped = groupByMonth(filtered);

  // Find next upcoming festival (Tier 1 highlight only)
  const nextFestival = festivals.find(
    (f) =>
      f.date &&
      f.date >= today &&
      f.tier === 1 &&
      !f.en.includes("Ekadashi") &&
      f.en !== "Amavasya" &&
      f.en !== "Purnima" &&
      !f.en.endsWith("Amavasya") &&
      !f.en.endsWith("Purnima")
  );

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-6">
        <h1 className="font-noto-telugu text-3xl text-accent mb-1">
          పండుగలు
        </h1>
        <p className="font-playfair italic text-text-secondary text-lg mb-2">
          Festivals
        </p>
        <div className="w-16 h-px bg-accent mx-auto mb-4" />
      </div>

      {/* Year selector */}
      <div className="flex items-center justify-center gap-4 mb-4">
        <button
          onClick={() => setYear((y) => y - 1)}
          className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-label/10 text-accent text-lg"
        >
          &larr;
        </button>
        <span className="font-playfair text-xl text-text-primary font-semibold">
          {year}
        </span>
        <button
          onClick={() => setYear((y) => y + 1)}
          className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-label/10 text-accent text-lg"
        >
          &rarr;
        </button>
      </div>

      {/* City indicator */}
      <p className="text-center text-xs text-label font-lora mb-4">
        {lang === "te" ? `${cityName} సమయాలు` : `Showing times for ${cityName}`}
      </p>

      {/* Next festival banner */}
      {nextFestival && nextFestival.date && (
        <div className="mb-6 rounded-lg border-2 border-gold/30 bg-gold/5 p-4 text-center">
          <p className="text-xs text-gold font-lora mb-1">
            {lang === "te" ? "తదుపరి పండుగ" : "Next Festival"}
          </p>
          <p className="font-noto-telugu text-xl text-text-primary">
            {nextFestival.te}
          </p>
          <p className="font-playfair italic text-text-secondary">
            {nextFestival.en}
          </p>
          <p className="text-sm text-label mt-1 font-lora">
            {formatDate(nextFestival.date, lang)}
            <span className="mx-2">&middot;</span>
            {lang === "te"
              ? `${daysBetween(today, nextFestival.date)} రోజులు`
              : `in ${daysBetween(today, nextFestival.date)} days`}
          </p>
        </div>
      )}

      <div className="mb-4">
        <LocationDisclaimer
          cityName={cityName}
          tz={cityTz}
          lang={lang}
          variant="festival"
        />
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap justify-center gap-2 mb-6">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1 text-sm rounded-full border transition-colors ${
              filter === f.key
                ? "bg-accent text-white border-accent"
                : "border-label/20 text-text-secondary hover:bg-label/10"
            } ${lang === "te" ? "font-noto-telugu" : "font-lora"}`}
          >
            {lang === "te" ? f.te : f.en}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <LoadingState
          variant="spinner"
          message="Loading festivals..."
          messageTe="పండుగలు లోడ్ అవుతున్నాయి..."
          lang={lang}
        />
      )}

      {/* Error */}
      {!loading && fetchError && (
        <ErrorState
          title="Unable to load festivals"
          titleTe="పండుగలు లోడ్ చేయడం సాధ్యం కాలేదు"
          message={fetchError}
          onRetry={() => fetchFestivals(year)}
          lang={lang}
        />
      )}

      {/* Festival list grouped by month */}
      {!loading &&
        Array.from(grouped.entries())
          .sort(([a], [b]) => a - b)
          .map(([month, monthFestivals]) => (
            <div key={month} className="mb-6">
              {/* Month header */}
              <div className="flex items-center gap-2 mb-3">
                <div className="h-px flex-1 bg-label/15" />
                <h2 className="text-sm font-semibold text-label">
                  {lang === "te" ? MONTH_NAMES_TE[month] : MONTH_NAMES_EN[month]}{" "}
                  {year}
                </h2>
                <div className="h-px flex-1 bg-label/15" />
              </div>

              {/* Festival cards */}
              <div className="space-y-2">
                {monthFestivals.map((f, i) => {
                  const isToday = f.date === today;
                  const isPast = (f.date ?? "") < today;
                  const isNext =
                    nextFestival && f.date === nextFestival.date && f.en === nextFestival.en;
                  const daysAway = f.date ? daysBetween(today, f.date) : 0;

                  let borderClass = "border-transparent";
                  if (f.isSignificantEkadashi) borderClass = "border-l-4 border-l-gold border-gold/30 bg-gold/5";
                  else if (isToday) borderClass = "border-gold border-2";
                  else if (isNext) borderClass = "border-accent/30";

                  const tierBadge =
                    f.tier === 1
                      ? { bg: "bg-gold/10", text: "text-gold", label: "Tier 1" }
                      : f.tier === 2
                        ? { bg: "bg-accent/10", text: "text-accent", label: "Regional" }
                        : { bg: "bg-label/10", text: "text-label", label: "National" };

                  return (
                    <div
                      key={`${f.date}-${f.en}-${i}`}
                      ref={isNext ? nextRef : undefined}
                      className={`rounded-lg border p-3 transition-all ${borderClass} ${
                        isPast ? "opacity-50" : ""
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <p className="text-xs text-label font-lora">
                          {f.date ? formatDate(f.date, lang) : ""}
                        </p>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded ${tierBadge.bg} ${tierBadge.text} font-lora`}
                        >
                          {tierBadge.label}
                        </span>
                      </div>
                      <p className="font-noto-telugu text-lg text-text-primary mt-1">
                        {f.isSignificantEkadashi ? "✨ " : ""}
                        {f.te}
                        {f.isSignificantEkadashi && (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-gold bg-gold/10 px-2 py-0.5 rounded-full ml-2 align-middle font-lora">
                            {lang === "te" ? "విశేష ఏకాదశి" : "Significant"}
                          </span>
                        )}
                      </p>
                      <p className="font-playfair italic text-text-secondary text-sm">
                        {f.en}
                      </p>
                      {f.isSignificantEkadashi && f.significance && (
                        <p className={`text-sm text-text-secondary italic mt-2 leading-relaxed ${lang === "te" ? "font-noto-telugu" : "font-lora"}`}>
                          {f.significance[lang]}
                        </p>
                      )}
                      {!isPast && f.date && daysAway > 0 && (
                        <p className="text-xs text-auspicious mt-1 font-lora">
                          {lang === "te"
                            ? `${daysAway} రోజుల్లో`
                            : `in ${daysAway} days`}
                        </p>
                      )}
                      {isToday && (
                        <p className="text-xs text-gold mt-1 font-lora font-semibold">
                          {lang === "te" ? "ఈ రోజు!" : "Today!"}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}

      {/* Empty state */}
      {!loading && filtered.length === 0 && (
        <p className="text-center text-label font-lora mt-8">
          {lang === "te"
            ? "ఈ వడపోతకు పండుగలు లేవు"
            : "No festivals found for this filter"}
        </p>
      )}
    </div>
  );
}
