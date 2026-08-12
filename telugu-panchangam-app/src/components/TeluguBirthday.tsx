"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getCity, getLang } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";
import { TELUGU_BIRTHDAY, TITHI_ANNIV } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import CitySearchInline from "./CitySearchInline";

interface TithiIdentity {
  masaNumber: number;
  masa: { te: string; en: string };
  paksha: "shukla" | "krishna";
  tithiNumber: number;
  tithi: { te: string; en: string };
  samvatsaram: { te: string; en: string };
  description: string;
}

interface AnniversaryOccurrence {
  year: number;
  date: string;
  gregorianFormatted: string;
  teluguFormatted: string;
  sunriseTime: string;
  daysFromNow: number;
  samvatsaram: { te: string; en: string };
  isCurrentYear: boolean;
}

interface GeocodeResult {
  displayName: string;
  lat: number;
  lng: number;
  timezone: string;
}

type ViewState = "form" | "loading" | "results";

export default function TeluguBirthday() {
  const [viewState, setViewState] = useState<ViewState>("form");
  const [city, setCity] = useState<CityInfo | null>(null);
  const [editingCurrentCity, setEditingCurrentCity] = useState(false);
  const [lang, setLangState] = useState<Lang>("en");

  const [dob, setDob] = useState("");
  const [birthCity, setBirthCity] = useState("");
  const [birthGeo, setBirthGeo] = useState<{ lat: number; lng: number; tz: string } | null>(null);
  const [yearRange, setYearRange] = useState(5);
  const [searchResults, setSearchResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [tithiIdentity, setTithiIdentity] = useState<TithiIdentity | null>(null);
  const [occurrences, setOccurrences] = useState<AnniversaryOccurrence[]>([]);
  const [error, setError] = useState("");
  const [shareCopied, setShareCopied] = useState(false);

  // Inline yearly reminder signup state
  const [reminderOpen, setReminderOpen] = useState(false);
  const [reminderEmail, setReminderEmail] = useState("");
  const [reminderDays, setReminderDays] = useState(1);
  const [reminderSending, setReminderSending] = useState(false);
  const [reminderSaved, setReminderSaved] = useState(false);

  useEffect(() => {
    setCity(getCity());
    setLangState(getLang());
  }, []);

  const teClass = lang === "te" ? "font-noto-telugu" : "font-lora";

  const searchBirthCity = useCallback(async (q: string) => {
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) setSearchResults(Array.isArray(json.data) ? json.data : [json.data]);
      }
    } catch {
      /* ignore */
    } finally {
      setSearching(false);
    }
  }, []);

  const handleCityInput = useCallback(
    (value: string) => {
      setBirthCity(value);
      setBirthGeo(null);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => searchBirthCity(value), 300);
    },
    [searchBirthCity]
  );

  const selectCity = useCallback((r: GeocodeResult) => {
    setBirthCity(r.displayName.split(",")[0]);
    setBirthGeo({ lat: r.lat, lng: r.lng, tz: r.timezone });
    setSearchResults([]);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!birthGeo || !city || !dob) return;

      setViewState("loading");
      setError("");

      const now = new Date();
      const fromYear = now.getFullYear();
      const toYear = fromYear + yearRange - 1;

      try {
        const params = new URLSearchParams({
          date: dob,
          origin_lat: String(birthGeo.lat),
          origin_lng: String(birthGeo.lng),
          origin_tz: birthGeo.tz,
          lat: String(city.lat),
          lng: String(city.lng),
          tz: city.tz,
          from_year: String(fromYear),
          to_year: String(toYear),
        });

        const res = await fetch(`/api/reminders/anniversary?${params}`);
        if (!res.ok) throw new Error("Failed to find Telugu birthday");
        const json = await res.json();
        setTithiIdentity(json.data.tithiIdentity);
        setOccurrences(json.data.occurrences);
        setViewState("results");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        setViewState("form");
      }
    },
    [birthGeo, city, dob, yearRange]
  );

  const handleShare = useCallback(() => {
    if (!occurrences.length || !tithiIdentity) return;
    const thisYear = occurrences.find((o) => o.isCurrentYear) ?? occurrences[0];
    const message =
      lang === "te"
        ? `నా తెలుగు పుట్టినరోజు ${thisYear.gregorianFormatted} (${thisYear.teluguFormatted})\ntelugupanchangam.app ద్వారా కనుగొన్నాను`
        : `My Telugu birthday this year is ${thisYear.gregorianFormatted} (${tithiIdentity.description})\nFound using telugupanchangam.app`;
    navigator.clipboard
      .writeText(message)
      .then(() => {
        setShareCopied(true);
        setTimeout(() => setShareCopied(false), 2000);
      })
      .catch(() => {});
  }, [occurrences, tithiIdentity, lang]);

  const saveYearlyReminder = useCallback(async () => {
    if (!city || !tithiIdentity || !reminderEmail) return;
    setReminderSending(true);
    try {
      const res = await fetch("/api/reminders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: reminderEmail,
          name: reminderEmail.split("@")[0],
          city_name: city.name,
          lat: city.lat,
          lng: city.lng,
          tz: city.tz,
          tithi_types: ["tithi_anniversary"],
          personal_note:
            lang === "te" ? "నా తెలుగు పుట్టినరోజు" : "My Telugu birthday",
          remind_days_before: reminderDays,
          remind_time: "06:00",
          reminder_type: "tithi_anniversary",
          // Identifying triple — the cron worker uses these to find
          // the correct day each year. Without them the row stores
          // but never fires.
          tithi_masa_number: tithiIdentity.masaNumber,
          tithi_paksha: tithiIdentity.paksha,
          tithi_number: tithiIdentity.tithiNumber,
          tithi_description: tithiIdentity.description,
          original_date: dob,
        }),
      });
      if (res.ok) {
        setReminderSaved(true);
        setReminderOpen(false);
      }
    } catch {
      /* ignore */
    } finally {
      setReminderSending(false);
    }
  }, [city, tithiIdentity, reminderEmail, reminderDays, dob, lang]);

  // ─── STATE 1: Form ───
  if (viewState === "form") {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <h2 className="font-noto-telugu text-2xl text-accent mb-1">
            {TELUGU_BIRTHDAY.pageTitle.te}
          </h2>
          <p className={`text-text-secondary text-sm italic ${lang === "te" ? "font-noto-telugu" : "font-playfair"}`}>
            {TELUGU_BIRTHDAY.subtitle[lang]}
          </p>
        </div>

        <p className={`text-text-secondary text-sm leading-relaxed ${teClass}`}>
          {TELUGU_BIRTHDAY.intro[lang]}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Date of birth */}
          <div>
            <label className={`block text-xs text-label mb-1 ${teClass}`}>
              {TELUGU_BIRTHDAY.dobLabel[lang]}
            </label>
            <input
              type="date"
              required
              value={dob}
              onChange={(e) => setDob(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
            />
            <div className={`text-[10px] text-label mt-0.5 ${teClass}`}>
              {TELUGU_BIRTHDAY.dobHint[lang]}
            </div>
          </div>

          {/* Birth city */}
          <div className="relative">
            <label className={`block text-xs text-label mb-1 ${teClass}`}>
              {TELUGU_BIRTHDAY.birthCityLabel[lang]}
            </label>
            <input
              type="text"
              required
              value={birthCity}
              onChange={(e) => handleCityInput(e.target.value)}
              placeholder={TITHI_ANNIV.originCityPlaceholder[lang]}
              className={`w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm focus:outline-none focus:border-accent ${teClass}`}
            />
            <div className={`text-[10px] text-label mt-0.5 ${teClass}`}>
              {TELUGU_BIRTHDAY.birthCityHint[lang]}
            </div>
            {birthGeo && (
              <div className={`text-[10px] text-auspicious mt-0.5 ${teClass}`}>
                ✓ {birthCity} {TITHI_ANNIV.selected[lang]}
              </div>
            )}
            {searchResults.length > 0 && !birthGeo && (
              <ul className="absolute z-10 w-full mt-1 bg-cream border border-label/20 rounded-lg shadow-lg max-h-40 overflow-y-auto">
                {searchResults.map((r, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => selectCity(r)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-label/10 text-text-primary"
                    >
                      {r.displayName}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {searching && (
              <div className={`text-[10px] text-label mt-1 ${teClass}`}>
                {TITHI_ANNIV.searching[lang]}
              </div>
            )}
          </div>

          {/* Current city — editable override */}
          {city && (
            <div>
              <label className={`block text-xs text-label mb-1 ${teClass}`}>
                {TITHI_ANNIV.currentCityLabel[lang]}
              </label>
              {!editingCurrentCity ? (
                <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-accent/20 bg-cream">
                  <span className="font-lora text-text-secondary text-sm truncate">
                    📍 {city.name}
                    <span className="text-label/60 text-xs ml-1">({city.tz})</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setEditingCurrentCity(true)}
                    className={`text-xs text-accent hover:underline flex-shrink-0 ${teClass}`}
                  >
                    {TITHI_ANNIV.changeCity[lang]}
                  </button>
                </div>
              ) : (
                <>
                  <CitySearchInline
                    placeholder={TITHI_ANNIV.searchCityPlaceholder[lang]}
                    cancelLabel={TITHI_ANNIV.cancel[lang]}
                    searchingLabel={TITHI_ANNIV.searching[lang]}
                    onSelect={(picked) => {
                      setCity(picked);
                      setEditingCurrentCity(false);
                    }}
                    onCancel={() => setEditingCurrentCity(false)}
                  />
                  <p className={`text-[10px] text-label/70 italic mt-1 ${teClass}`}>
                    {TITHI_ANNIV.cityOverrideNote[lang]}
                  </p>
                </>
              )}
            </div>
          )}

          {/* Year range */}
          <div>
            <label className={`block text-xs text-label mb-1 ${teClass}`}>
              {TITHI_ANNIV.yearsLabel[lang]}
            </label>
            <select
              value={yearRange}
              onChange={(e) => setYearRange(parseInt(e.target.value, 10))}
              className={`w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm focus:outline-none focus:border-accent ${teClass}`}
            >
              <option value={5}>{TITHI_ANNIV.next5[lang]}</option>
              <option value={10}>{TITHI_ANNIV.next10[lang]}</option>
              <option value={15}>{TITHI_ANNIV.next15[lang]}</option>
              <option value={25}>{TITHI_ANNIV.next25[lang]}</option>
            </select>
          </div>

          {error && <div className="text-sm text-danger font-lora">{error}</div>}

          <button
            type="submit"
            disabled={!birthGeo || !dob}
            className={`w-full py-2.5 rounded-md bg-header-grad text-white text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed ${teClass}`}
          >
            🎂 {TELUGU_BIRTHDAY.findButton[lang]}
          </button>
        </form>
      </div>
    );
  }

  // ─── STATE 2: Loading ───
  if (viewState === "loading") {
    return (
      <div className="flex flex-col items-center justify-center py-16 space-y-4">
        <div className="text-4xl animate-moon-pulse">🎂</div>
        <div className={`text-text-secondary ${lang === "te" ? "font-noto-telugu" : "font-playfair italic"}`}>
          {TITHI_ANNIV.loadingText[lang]}
        </div>
      </div>
    );
  }

  // ─── STATE 3: Results ───
  return (
    <div className="space-y-6">
      {/* Birth tithi card */}
      {tithiIdentity && (
        <div className="bg-header-grad rounded-xl p-6 text-center text-white">
          <div className={`text-sm opacity-80 mb-1 ${teClass}`}>
            {TELUGU_BIRTHDAY.bornOn[lang]}
          </div>
          <div className="font-noto-telugu text-2xl font-bold mb-1">
            {tithiIdentity.masa.te} {tithiIdentity.paksha === "shukla" ? "శుక్ల" : "కృష్ణ"} {tithiIdentity.tithi.te}
          </div>
          <div className="font-playfair italic text-sm opacity-90 mb-2">
            {tithiIdentity.description}
          </div>
          <div className="text-xs opacity-70">
            {tithiIdentity.samvatsaram.en} Samvatsaram
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => setViewState("form")}
          className={`text-sm text-accent hover:underline ${teClass}`}
        >
          ← {TITHI_ANNIV.searchAgain[lang]}
        </button>
        {occurrences.length > 0 && (
          <button
            onClick={handleShare}
            className={`text-sm px-3 py-1.5 rounded-md border border-accent/30 text-accent hover:bg-accent/10 transition-colors ${teClass}`}
          >
            {shareCopied ? TELUGU_BIRTHDAY.shareCopied[lang] : `📤 ${TELUGU_BIRTHDAY.shareBtn[lang]}`}
          </button>
        )}
      </div>

      {/* Yearly birthday reminder signup */}
      {occurrences.length > 0 && tithiIdentity && !reminderSaved && (
        <div className="rounded-xl border-2 border-gold/30 p-5 bg-gold/5">
          <h3 className="font-noto-telugu text-gold text-base font-semibold mb-1">
            🎂 {TELUGU_BIRTHDAY.setReminder[lang]}
          </h3>
          <p className={`text-text-secondary text-xs mb-3 ${teClass}`}>
            {lang === "te"
              ? "ప్రతి సంవత్సరం మీ తెలుగు పుట్టినరోజుకు ముందు రోజు ఇమెయిల్ ద్వారా గుర్తు చేస్తాం."
              : "We will email you a day before your Telugu birthday every year — automatically, no need to look it up again."}
          </p>
          {!reminderOpen ? (
            <button
              type="button"
              onClick={() => setReminderOpen(true)}
              className={`w-full py-2.5 rounded-md bg-gold text-white text-sm font-semibold hover:opacity-90 transition-opacity ${teClass}`}
            >
              {TELUGU_BIRTHDAY.setReminder[lang]} →
            </button>
          ) : (
            <div className="space-y-2">
              <input
                type="email"
                value={reminderEmail}
                onChange={(e) => setReminderEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full px-3 py-2 rounded-md border border-gold/30 bg-cream text-sm font-lora focus:outline-none focus:border-gold"
              />
              <select
                value={reminderDays}
                onChange={(e) => setReminderDays(parseInt(e.target.value, 10))}
                className={`w-full px-3 py-2 rounded-md border border-gold/30 bg-cream text-sm focus:outline-none focus:border-gold ${teClass}`}
              >
                <option value={0}>{TITHI_ANNIV.onTheDay[lang]}</option>
                <option value={1}>{TITHI_ANNIV.oneDayBefore[lang]}</option>
                <option value={2}>{TITHI_ANNIV.twoDaysBefore[lang]}</option>
              </select>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={saveYearlyReminder}
                  disabled={!reminderEmail || reminderSending}
                  className={`flex-1 py-2 rounded-md bg-gold text-white text-sm font-semibold disabled:opacity-50 ${teClass}`}
                >
                  {reminderSending ? TITHI_ANNIV.sending[lang] : TITHI_ANNIV.confirmReminder[lang]}
                </button>
                <button
                  type="button"
                  onClick={() => setReminderOpen(false)}
                  className={`px-3 py-2 rounded-md border border-label/20 text-xs text-label ${teClass}`}
                >
                  {TITHI_ANNIV.cancel[lang]}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      {reminderSaved && (
        <div className="rounded-xl border border-auspicious/30 bg-auspicious/5 p-4 text-center">
          <p className={`text-auspicious text-sm ${teClass}`}>
            ✓ {TITHI_ANNIV.reminderSet[lang]} — {TITHI_ANNIV.oncePerYear[lang]}
          </p>
        </div>
      )}

      {/* Birthday list */}
      <div>
        <h3 className={`text-xs font-semibold uppercase tracking-wider text-label mb-3 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {TELUGU_BIRTHDAY.resultsTitle[lang]}
        </h3>

        <div className="space-y-3">
          {occurrences.map((occ) => {
            const isPast = occ.daysFromNow < 0;
            return (
              <div
                key={occ.year}
                className={`rounded-lg border p-4 transition-all ${
                  occ.isCurrentYear
                    ? "border-accent border-2 bg-accent/5"
                    : isPast
                      ? "border-label/10 opacity-60"
                      : "border-label/10 bg-cream"
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-playfair text-lg text-text-primary">{occ.year}</span>
                  {occ.isCurrentYear && (
                    <span className={`px-2 py-0.5 rounded-full bg-accent text-white text-[10px] font-semibold ${lang === "te" ? "font-noto-telugu" : ""}`}>
                      {TELUGU_BIRTHDAY.thisYear[lang]}
                    </span>
                  )}
                </div>
                <div className="font-noto-telugu text-text-primary text-sm mb-0.5">
                  {occ.teluguFormatted}
                </div>
                <div className="font-lora text-text-secondary text-sm">
                  {occ.gregorianFormatted}
                </div>
                <div className={`text-xs text-label mt-1 ${teClass}`}>
                  🌅 {TITHI_ANNIV.sunriseLabel[lang]}: {occ.sunriseTime}
                  {occ.daysFromNow === 0 && (
                    <span className="ml-2 text-gold font-bold">
                      · 🎂 {TITHI_ANNIV.todayLabel[lang]}!
                    </span>
                  )}
                  {occ.daysFromNow > 0 && (
                    <span className="ml-2 text-accent">
                      · {occ.daysFromNow} {TITHI_ANNIV.inDays[lang]}
                    </span>
                  )}
                  {occ.daysFromNow < 0 && (
                    <span className="ml-2 text-label/60">
                      · {Math.abs(occ.daysFromNow)} {TITHI_ANNIV.daysAgo[lang]}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <p className={`text-[10px] text-label/70 italic mt-4 text-center ${teClass}`}>
          {TELUGU_BIRTHDAY.disclaimer[lang]}
        </p>
      </div>
    </div>
  );
}
