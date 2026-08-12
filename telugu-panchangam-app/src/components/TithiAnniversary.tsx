"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getCity, getLang } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";
import { TITHI_ANNIV } from "@/lib/i18n";
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

export default function TithiAnniversary() {
  const [viewState, setViewState] = useState<ViewState>("form");
  const [city, setCity] = useState<CityInfo | null>(null);
  const [editingCurrentCity, setEditingCurrentCity] = useState(false);
  const [lang, setLangState] = useState<Lang>("en");

  // Form state
  const [passingDate, setPassingDate] = useState("");
  const [originCity, setOriginCity] = useState("");
  const [originGeo, setOriginGeo] = useState<{ lat: number; lng: number; tz: string } | null>(null);
  const [yearRange, setYearRange] = useState(5);
  const [originResults, setOriginResults] = useState<GeocodeResult[]>([]);
  const [originSearching, setOriginSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Results state
  const [tithiIdentity, setTithiIdentity] = useState<TithiIdentity | null>(null);
  const [occurrences, setOccurrences] = useState<AnniversaryOccurrence[]>([]);
  const [originalDate, setOriginalDate] = useState("");
  const [error, setError] = useState("");

  // Inline reminder state
  const [reminderIdx, setReminderIdx] = useState<number | null>(null);
  const [reminderEmail, setReminderEmail] = useState("");
  const [reminderNote, setReminderNote] = useState("");
  const [reminderDays, setReminderDays] = useState(1);
  const [reminderSending, setReminderSending] = useState(false);
  const [reminderSent, setReminderSent] = useState<Set<number>>(new Set());

  useEffect(() => {
    setCity(getCity());
    setLangState(getLang());
  }, []);

  const teClass = lang === "te" ? "font-noto-telugu" : "font-lora";

  // Origin city search
  const searchOrigin = useCallback(async (q: string) => {
    if (q.length < 2) { setOriginResults([]); return; }
    setOriginSearching(true);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) setOriginResults(Array.isArray(json.data) ? json.data : [json.data]);
      }
    } catch { /* ignore */ }
    finally { setOriginSearching(false); }
  }, []);

  const handleOriginInput = useCallback((value: string) => {
    setOriginCity(value);
    setOriginGeo(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => searchOrigin(value), 300);
  }, [searchOrigin]);

  const selectOrigin = useCallback((r: GeocodeResult) => {
    setOriginCity(r.displayName.split(",")[0]);
    setOriginGeo({ lat: r.lat, lng: r.lng, tz: r.timezone });
    setOriginResults([]);
  }, []);

  // Submit
  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!originGeo || !city || !passingDate) return;

    setViewState("loading");
    setError("");

    const now = new Date();
    const fromYear = now.getFullYear();
    const toYear = fromYear + yearRange - 1;

    try {
      const params = new URLSearchParams({
        date: passingDate,
        origin_lat: String(originGeo.lat),
        origin_lng: String(originGeo.lng),
        origin_tz: originGeo.tz,
        lat: String(city.lat),
        lng: String(city.lng),
        tz: city.tz,
        from_year: String(fromYear),
        to_year: String(toYear),
      });

      const res = await fetch(`/api/reminders/anniversary?${params}`);
      if (!res.ok) throw new Error("Failed to calculate anniversaries");

      const json = await res.json();
      setTithiIdentity(json.data.tithiIdentity);
      setOccurrences(json.data.occurrences);
      setOriginalDate(json.data.originalDate);
      setViewState("results");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setViewState("form");
    }
  }, [originGeo, city, passingDate, yearRange]);

  // Inline reminder submit
  const sendReminder = useCallback(async (occ: AnniversaryOccurrence) => {
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
          personal_note: reminderNote || undefined,
          remind_days_before: reminderDays,
          remind_time: "06:00",
          reminder_type: "tithi_anniversary",
          // CRITICAL — these three fields are what the daily cron
          // worker uses to find the right day each year. Without
          // them the row is stored but never fires.
          tithi_masa_number: tithiIdentity.masaNumber,
          tithi_paksha: tithiIdentity.paksha,
          tithi_number: tithiIdentity.tithiNumber,
          tithi_description: tithiIdentity.description,
          original_date: originalDate,
        }),
      });
      if (res.ok) {
        setReminderSent((prev) => new Set(prev).add(occ.year));
        setReminderIdx(null);
      }
    } catch { /* ignore */ }
    finally { setReminderSending(false); }
  }, [city, tithiIdentity, reminderEmail, reminderNote, reminderDays, originalDate]);

  // ─── STATE 1: Form ───
  if (viewState === "form") {
    return (
      <div className="space-y-6">
        <p className={`text-text-secondary text-sm leading-relaxed ${teClass}`}>
          {TITHI_ANNIV.intro[lang]}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Date of passing */}
          <div>
            <label className={`block text-xs text-label mb-1 ${teClass}`}>{TITHI_ANNIV.dateLabel[lang]}</label>
            <input
              type="date"
              required
              value={passingDate}
              onChange={(e) => setPassingDate(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
            />
            <div className={`text-[10px] text-label mt-0.5 ${teClass}`}>{TITHI_ANNIV.dateHint[lang]}</div>
          </div>

          {/* City at time of passing */}
          <div className="relative">
            <label className={`block text-xs text-label mb-1 ${teClass}`}>{TITHI_ANNIV.originCityLabel[lang]}</label>
            <input
              type="text"
              required
              value={originCity}
              onChange={(e) => handleOriginInput(e.target.value)}
              placeholder={TITHI_ANNIV.originCityPlaceholder[lang]}
              className={`w-full px-3 py-2 rounded-md border border-label/20 bg-cream text-text-primary text-sm focus:outline-none focus:border-accent ${teClass}`}
            />
            <div className={`text-[10px] text-label mt-0.5 ${teClass}`}>{TITHI_ANNIV.originCityHint[lang]}</div>
            {originGeo && (
              <div className={`text-[10px] text-auspicious mt-0.5 ${teClass}`}>&#x2714; {originCity} {TITHI_ANNIV.selected[lang]}</div>
            )}
            {originResults.length > 0 && !originGeo && (
              <ul className="absolute z-10 w-full mt-1 bg-cream border border-label/20 rounded-lg shadow-lg max-h-40 overflow-y-auto">
                {originResults.map((r, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => selectOrigin(r)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-label/10 text-text-primary"
                    >
                      {r.displayName}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {originSearching && <div className={`text-[10px] text-label mt-1 ${teClass}`}>{TITHI_ANNIV.searching[lang]}</div>}
          </div>

          {/* Current city — editable override */}
          {city && (
            <div>
              <label className={`block text-xs text-label mb-1 ${teClass}`}>{TITHI_ANNIV.currentCityLabel[lang]}</label>
              {!editingCurrentCity ? (
                <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-md border border-accent/20 bg-cream">
                  <span className="font-lora text-text-secondary text-sm truncate">
                    &#x1F4CD; {city.name}
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
              <div className={`text-[10px] text-label mt-0.5 ${teClass}`}>{TITHI_ANNIV.currentCityHint[lang]}</div>
            </div>
          )}

          {/* Year range */}
          <div>
            <label className={`block text-xs text-label mb-1 ${teClass}`}>{TITHI_ANNIV.yearsLabel[lang]}</label>
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
            disabled={!originGeo || !passingDate}
            className={`w-full py-2.5 rounded-md bg-header-grad text-white text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed ${teClass}`}
          >
            {TITHI_ANNIV.findButton[lang]}
          </button>
        </form>
      </div>
    );
  }

  // ─── STATE 2: Loading ───
  if (viewState === "loading") {
    return (
      <div className="flex flex-col items-center justify-center py-16 space-y-4">
        <div className="text-4xl animate-moon-pulse">&#x1F311;</div>
        <div className={`text-text-secondary ${lang === "te" ? "font-noto-telugu" : "font-playfair italic"}`}>{TITHI_ANNIV.loadingText[lang]}</div>
        <div className={`text-label text-sm ${teClass}`}>{TITHI_ANNIV.loadingSub[lang]}</div>
      </div>
    );
  }

  // ─── STATE 3: Results ───
  return (
    <div className="space-y-6">
      {/* Result header */}
      {tithiIdentity && (
        <div className="bg-header-grad rounded-xl p-6 text-center text-white">
          <div className="text-sm opacity-80 mb-1">{originalDate}</div>
          <div className="font-noto-telugu text-2xl font-bold mb-1">
            {tithiIdentity.masa.te} {tithiIdentity.paksha === "shukla" ? "శుక్ల" : "కృష్ణ"} {tithiIdentity.tithi.te}
          </div>
          <div className="font-playfair italic text-sm opacity-90 mb-2">
            {tithiIdentity.description}
          </div>
          <div className="text-xs opacity-70">
            {tithiIdentity.samvatsaram.en} Samvatsaram
          </div>
          <div className={`text-xs opacity-60 mt-2 italic ${teClass}`}>
            {TITHI_ANNIV.sacredTithi[lang]}
          </div>
        </div>
      )}

      <button
        onClick={() => setViewState("form")}
        className={`text-sm text-accent hover:underline ${teClass}`}
      >
        &larr; {TITHI_ANNIV.searchAgain[lang]}
      </button>

      {/* Anniversary list */}
      <div>
        <h3 className={`text-xs font-semibold uppercase tracking-wider text-label mb-1 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {TITHI_ANNIV.resultsTitle[lang]}
        </h3>
        {city && (
          <div className={`text-[10px] text-text-secondary mb-3 ${teClass}`}>
            {TITHI_ANNIV.resultsSubtitle[lang]} — {city.name}
          </div>
        )}

        <div className="space-y-3">
          {occurrences.map((occ) => {
            const isPast = occ.daysFromNow < 0;
            const isSent = reminderSent.has(occ.year);

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
                      {TITHI_ANNIV.thisYear[lang]}
                    </span>
                  )}
                  {isPast && (
                    <span className={`text-[10px] text-label ${teClass}`}>
                      {Math.abs(occ.daysFromNow)} {TITHI_ANNIV.daysAgo[lang]}
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
                  &#x1F305; {TITHI_ANNIV.sunriseLabel[lang]}: {occ.sunriseTime}
                  {occ.daysFromNow === 0 && (
                    <span className="ml-2 text-gold font-bold">
                      &middot; &#x1FA94; {TITHI_ANNIV.todayLabel[lang]}
                    </span>
                  )}
                  {occ.daysFromNow > 0 && (
                    <span className="ml-2 text-auspicious">
                      &middot; {occ.daysFromNow} {TITHI_ANNIV.inDays[lang]}
                    </span>
                  )}
                  {occ.daysFromNow < 0 && (
                    <span className="ml-2 text-label/60 italic">
                      &middot; {Math.abs(occ.daysFromNow)} {TITHI_ANNIV.daysAgo[lang]}
                    </span>
                  )}
                </div>

                {/* Set Reminder (future dates only) */}
                {!isPast && !isSent && (
                  <div className="mt-2">
                    {reminderIdx === occ.year ? (
                      <div className="space-y-2 p-3 rounded-md bg-label/5 border border-label/10">
                        <input
                          type="email"
                          required
                          value={reminderEmail}
                          onChange={(e) => setReminderEmail(e.target.value)}
                          placeholder={TITHI_ANNIV.reminderEmailPlaceholder[lang]}
                          className="w-full px-2 py-1.5 rounded border border-label/20 bg-cream text-sm font-lora focus:outline-none focus:border-accent"
                        />
                        <textarea
                          value={reminderNote}
                          onChange={(e) => setReminderNote(e.target.value)}
                          maxLength={300}
                          rows={2}
                          placeholder={TITHI_ANNIV.reminderNotePlaceholder[lang]}
                          className={`w-full px-2 py-1.5 rounded border border-label/20 bg-cream text-sm focus:outline-none focus:border-accent resize-none ${teClass}`}
                        />
                        <select
                          value={reminderDays}
                          onChange={(e) => setReminderDays(parseInt(e.target.value, 10))}
                          className={`w-full px-2 py-1.5 rounded border border-label/20 bg-cream text-sm focus:outline-none focus:border-accent ${teClass}`}
                        >
                          <option value={0}>{TITHI_ANNIV.onTheDay[lang]}</option>
                          <option value={1}>{TITHI_ANNIV.oneDayBefore[lang]}</option>
                          <option value={2}>{TITHI_ANNIV.twoDaysBefore[lang]}</option>
                        </select>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => sendReminder(occ)}
                            disabled={reminderSending || !reminderEmail}
                            className={`flex-1 py-1.5 rounded bg-accent text-white text-xs font-semibold disabled:opacity-50 ${teClass}`}
                          >
                            {reminderSending ? TITHI_ANNIV.sending[lang] : TITHI_ANNIV.confirmReminder[lang]}
                          </button>
                          <button
                            type="button"
                            onClick={() => setReminderIdx(null)}
                            className={`px-3 py-1.5 rounded border border-label/20 text-xs text-label ${teClass}`}
                          >
                            {TITHI_ANNIV.cancel[lang]}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={() => setReminderIdx(occ.year)}
                        className={`text-xs text-accent hover:underline ${teClass}`}
                      >
                        {TITHI_ANNIV.setReminderBtn[lang]}
                      </button>
                    )}
                  </div>
                )}
                {isSent && (
                  <div className={`mt-2 text-xs text-auspicious ${teClass}`}>&#x2714; {TITHI_ANNIV.reminderSet[lang]}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Annual reminder */}
      <div className="rounded-xl border-2 border-gold/30 p-5 bg-gold/5">
        <h3 className="font-noto-telugu text-gold text-sm font-semibold mb-1">
          {TITHI_ANNIV.annualReminder.te}
        </h3>
        <p className={`text-text-secondary text-xs mb-3 ${teClass}`}>
          {TITHI_ANNIV.annualReminderDesc[lang]}
        </p>
        <div className="space-y-2">
          <input
            type="email"
            value={reminderEmail}
            onChange={(e) => setReminderEmail(e.target.value)}
            placeholder={TITHI_ANNIV.reminderEmailPlaceholder[lang]}
            className="w-full px-3 py-2 rounded-md border border-gold/20 bg-cream text-sm font-lora focus:outline-none focus:border-gold"
          />
          <textarea
            value={reminderNote}
            onChange={(e) => setReminderNote(e.target.value)}
            maxLength={300}
            rows={2}
            placeholder={TITHI_ANNIV.annualNotePlaceholder[lang]}
            className={`w-full px-3 py-2 rounded-md border border-gold/20 bg-cream text-sm focus:outline-none focus:border-gold resize-none ${teClass}`}
          />
          <select
            value={reminderDays}
            onChange={(e) => setReminderDays(parseInt(e.target.value, 10))}
            className={`w-full px-3 py-2 rounded-md border border-gold/20 bg-cream text-sm focus:outline-none focus:border-gold ${teClass}`}
          >
            <option value={0}>{TITHI_ANNIV.onTheDay[lang]}</option>
            <option value={1}>{TITHI_ANNIV.oneDayBefore[lang]}</option>
            <option value={2}>{TITHI_ANNIV.twoDaysBefore[lang]}</option>
          </select>
          <button
            type="button"
            onClick={() => {
              if (occurrences[0]) sendReminder(occurrences[0]);
            }}
            disabled={!reminderEmail || reminderSending}
            className={`w-full py-2.5 rounded-md bg-gold text-white text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 ${teClass}`}
          >
            {reminderSending ? TITHI_ANNIV.setting[lang] : TITHI_ANNIV.setAnnual[lang]}
          </button>
          <div className={`text-[10px] text-label text-center ${teClass}`}>{TITHI_ANNIV.oncePerYear[lang]}</div>
        </div>
      </div>
    </div>
  );
}
