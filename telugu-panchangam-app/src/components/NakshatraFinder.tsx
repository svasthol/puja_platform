"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { getCity, getLang } from "@/lib/cache";
import type { Lang } from "@/lib/i18n";
import type { JanmaNakshatraResult } from "@/engine/nakshatra";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";

interface GeocodeResult {
  displayName: string;
  lat: number;
  lng: number;
  timezone: string;
}

interface BirthCity {
  name: string;
  lat: number;
  lng: number;
  tz: string;
}

const QUALITY_STYLES: Record<
  string,
  { bg: string; text: string; label: string; labelTe: string }
> = {
  highly_auspicious: {
    bg: "bg-auspicious/10",
    text: "text-auspicious",
    label: "Highly Auspicious",
    labelTe: "అత్యంత శుభం",
  },
  auspicious: {
    bg: "bg-auspicious/10",
    text: "text-auspicious",
    label: "Auspicious",
    labelTe: "శుభం",
  },
  neutral: {
    bg: "bg-label/10",
    text: "text-label",
    label: "Neutral",
    labelTe: "సాధారణం",
  },
  inauspicious: {
    bg: "bg-danger/10",
    text: "text-danger",
    label: "Inauspicious",
    labelTe: "అశుభం",
  },
  highly_inauspicious: {
    bg: "bg-danger/10",
    text: "text-danger",
    label: "Highly Inauspicious",
    labelTe: "అత్యంత అశుభం",
  },
};

export default function NakshatraFinder() {
  const [lang, setLang] = useState<Lang>("en");
  const [birthDate, setBirthDate] = useState("");
  const [birthTime, setBirthTime] = useState("");
  const [birthCity, setBirthCity] = useState<BirthCity | null>(null);
  const [birthCityQuery, setBirthCityQuery] = useState("");
  const [birthCityResults, setBirthCityResults] = useState<GeocodeResult[]>([]);
  const [showBirthDropdown, setShowBirthDropdown] = useState(false);
  const [searchingCity, setSearchingCity] = useState(false);
  const [result, setResult] = useState<JanmaNakshatraResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLang(getLang());
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowBirthDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const searchBirthCity = useCallback(async (q: string) => {
    if (q.length < 2) {
      setBirthCityResults([]);
      return;
    }
    setSearchingCity(true);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) {
          setBirthCityResults(
            Array.isArray(json.data) ? json.data : [json.data]
          );
        }
      }
    } catch {
      // ignore
    } finally {
      setSearchingCity(false);
    }
  }, []);

  const handleBirthCityInput = useCallback(
    (value: string) => {
      setBirthCityQuery(value);
      setShowBirthDropdown(true);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => searchBirthCity(value), 300);
    },
    [searchBirthCity]
  );

  const selectBirthCity = useCallback((r: GeocodeResult) => {
    setBirthCity({
      name: r.displayName.split(",")[0],
      lat: r.lat,
      lng: r.lng,
      tz: r.timezone,
    });
    setBirthCityQuery(r.displayName.split(",")[0]);
    setShowBirthDropdown(false);
    setBirthCityResults([]);
  }, []);

  const search = useCallback(async () => {
    if (!birthDate || !birthTime || !birthCity) return;
    setLoading(true);
    setSearched(true);
    setFetchError(null);

    const currentCity = getCity();
    const params = new URLSearchParams({
      date: birthDate,
      time: birthTime,
      lat: String(birthCity.lat),
      lng: String(birthCity.lng),
      tz: birthCity.tz,
      today_lat: String(currentCity.lat),
      today_lng: String(currentCity.lng),
      today_tz: currentCity.tz,
    });

    try {
      const res = await fetch(`/api/nakshatra?${params}`);
      if (!res.ok) throw new Error("Service temporarily unavailable");
      const json = await res.json();
      if (json.data) setResult(json.data);
      else setResult(null);
    } catch (err) {
      setResult(null);
      setFetchError(err instanceof Error ? err.message : "Unable to calculate nakshatra");
    }
    setLoading(false);
  }, [birthDate, birthTime, birthCity]);

  const currentCityName = getCity().name;

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="text-center mb-6">
        <h1 className="font-noto-telugu text-3xl text-accent mb-1">
          జన్మ నక్షత్రం
        </h1>
        <p className="font-playfair italic text-text-secondary text-lg mb-1">
          Nakshatra Finder
        </p>
        <p className="text-xs text-label font-lora">
          {lang === "te"
            ? "జన్మ సమయంలో చంద్రుని స్థానం నుండి మీ నక్షత్రం కనుగొనండి"
            : "Find your birth star from the Moon's position at birth"}
        </p>
        <div className="w-16 h-px bg-accent mx-auto mt-4" />
      </div>

      {/* Form */}
      <div className="bg-white/50 rounded-lg border border-label/10 p-4 mb-6">
        {/* Birth date */}
        <div className="mb-3">
          <label className="block text-xs text-label font-lora mb-1">
            {lang === "te" ? "జన్మ తేది" : "Birth date"}
          </label>
          <input
            type="date"
            value={birthDate}
            onChange={(e) => setBirthDate(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
          />
        </div>

        {/* Birth time */}
        <div className="mb-3">
          <label className="block text-xs text-label font-lora mb-1">
            {lang === "te" ? "జన్మ సమయం" : "Birth time"}
            <span className="text-label/50 ml-1">(HH:MM, 24hr)</span>
          </label>
          <input
            type="time"
            value={birthTime}
            onChange={(e) => setBirthTime(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
          />
          <p className="text-[10px] text-label/60 mt-0.5 font-lora">
            {lang === "te"
              ? "జన్మ స్థలంలో స్థానిక సమయం. ఖచ్చితత్వం జన్మ సమయం మీద ఆధారపడి ఉంటుంది."
              : "Local time at place of birth. Accuracy depends on birth time precision."}
          </p>
        </div>

        {/* Birth city */}
        <div className="mb-3 relative" ref={dropdownRef}>
          <label className="block text-xs text-label font-lora mb-1">
            {lang === "te" ? "జన్మ స్థలం" : "Birth city"}
          </label>
          <input
            type="text"
            value={birthCityQuery}
            onChange={(e) => handleBirthCityInput(e.target.value)}
            onFocus={() => {
              if (birthCityResults.length > 0) setShowBirthDropdown(true);
            }}
            placeholder={lang === "te" ? "నగరం వెతకండి..." : "Search city..."}
            className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent placeholder:text-label/40"
          />
          {showBirthDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-cream border border-label/20 rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
              {searchingCity && (
                <div className="px-3 py-2 text-sm text-label">
                  {lang === "te" ? "వెతుకుతోంది..." : "Searching..."}
                </div>
              )}
              {birthCityResults.map((r, i) => (
                <button
                  key={i}
                  onClick={() => selectBirthCity(r)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-label/10 text-text-primary transition-colors"
                >
                  {r.displayName}
                </button>
              ))}
              {birthCityQuery.length >= 2 &&
                !searchingCity &&
                birthCityResults.length === 0 && (
                  <div className="px-3 py-2 text-sm text-label">
                    {lang === "te" ? "ఫలితాలు లేవు" : "No results found"}
                  </div>
                )}
            </div>
          )}
        </div>

        {/* Current city info */}
        <p className="text-xs text-label font-lora mb-3">
          {lang === "te"
            ? `తారాబలం: ${currentCityName} ప్రస్తుత నక్షత్రం ఆధారంగా`
            : `Tarabalam based on today's Nakshatra at ${currentCityName}`}
        </p>

        {/* Search button */}
        <button
          onClick={search}
          disabled={loading || !birthDate || !birthTime || !birthCity}
          className="w-full py-2.5 rounded-lg bg-header-grad text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          {loading
            ? lang === "te"
              ? "వెతుకుతోంది..."
              : "Calculating..."
            : lang === "te"
              ? "నక్షత్రం కనుగొనండి"
              : "Find Nakshatra"}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <LoadingState variant="spinner" message="Calculating..." messageTe="లెక్కిస్తోంది..." lang={lang} />
      )}

      {/* Error */}
      {!loading && fetchError && (
        <ErrorState
          title="Unable to calculate"
          titleTe="లెక్కించడం సాధ్యం కాలేదు"
          message={fetchError}
          onRetry={search}
          lang={lang}
        />
      )}

      {/* No result */}
      {searched && !loading && !fetchError && !result && (
        <p className="text-center text-label font-lora mt-8">
          {lang === "te"
            ? "ఫలితాలు లభించలేదు. దయచేసి మీ వివరాలు తనిఖీ చేయండి."
            : "Could not calculate. Please check your inputs."}
        </p>
      )}

      {result && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            {/* Card 1: Birth Star */}
            <div className="rounded-lg border border-gold/30 bg-gold/5 p-4 text-center">
              <p className="text-[10px] text-gold font-lora mb-2 uppercase tracking-wider">
                {lang === "te" ? "జన్మ నక్షత్రం" : "Birth Star"}
              </p>
              <p className="font-noto-telugu text-2xl text-text-primary mb-1">
                {result.nakshatra.te}
              </p>
              <p className="font-playfair italic text-text-secondary text-sm">
                {result.nakshatra.en}
              </p>
              <p className="text-xs text-label font-lora mt-2">
                {lang === "te" ? `పాదం ${result.pada}` : `Pada ${result.pada}`}
              </p>
              <p className="text-[10px] text-label/60 font-lora mt-1">
                {result.deity}
              </p>
            </div>

            {/* Card 2: Raasi */}
            <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 text-center">
              <p className="text-[10px] text-accent font-lora mb-2 uppercase tracking-wider">
                {lang === "te" ? "రాశి" : "Raasi"}
              </p>
              <p className="font-noto-telugu text-2xl text-text-primary mb-1">
                {result.raasi.te}
              </p>
              <p className="font-playfair italic text-text-secondary text-sm">
                {result.raasi.en}
              </p>
            </div>

            {/* Card 3: Tarabalam */}
            {result.tarabalam && (
              <div className="rounded-lg border border-label/20 p-4 text-center">
                <p className="text-[10px] text-label font-lora mb-2 uppercase tracking-wider">
                  {lang === "te" ? "తారాబలం" : "Today's Tarabalam"}
                </p>
                {(() => {
                  const style =
                    QUALITY_STYLES[result.tarabalam!.quality] ??
                    QUALITY_STYLES.neutral;
                  return (
                    <>
                      <span
                        className={`inline-block text-xs px-2 py-0.5 rounded ${style.bg} ${style.text} font-lora font-semibold mb-2`}
                      >
                        {lang === "te" ? style.labelTe : style.label}
                      </span>
                      <p className="font-noto-telugu text-lg text-text-primary">
                        {result.tarabalam!.te}
                      </p>
                      <p className="font-lora text-sm text-text-secondary italic">
                        {result.tarabalam!.taraName}
                      </p>
                      <p className="text-[10px] text-label mt-2 font-lora">
                        {lang === "te" ? "ఈ రోజు నక్షత్రం:" : "Today's Nakshatra:"}
                        {" "}
                        <span className="font-noto-telugu">
                          {result.tarabalam!.todaysNakshatra.te}
                        </span>
                      </p>
                    </>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Disclaimer */}
          <p className="text-center text-[11px] text-label/50 font-lora italic max-w-md mx-auto leading-relaxed">
            {lang === "te"
              ? "ఇది జన్మ సమయంలో చంద్రుని ఖగోళ స్థానం నుండి గణించబడింది. ఇది సమయ-ఆధారిత ఖగోళశాస్త్రం మాత్రమే — ఎటువంటి అంచనాలు లేదా వ్యాఖ్యానాలు చేయబడవు."
              : "This is calculated from the Moon's astronomical position at the time of birth. It is time-based astronomy only — no predictions or interpretations are made."}
          </p>
        </>
      )}
    </div>
  );
}
