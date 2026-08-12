"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getCity, getLang } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";
import { ABOUT, ABOUT_ANGAS } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

// ─────────────────────────────────────────────────────────
// Section 2 — Engine step-by-step player
// ─────────────────────────────────────────────────────────

interface EngineStep {
  num: number;
  titleEn: string;
  titleTe: string;
  bodyEn: string;
  bodyTe: string;
  formula?: string;
}

const ENGINE_STEPS: EngineStep[] = [
  {
    num: 1,
    titleEn: "Find local sunrise",
    titleTe: "స్థానిక సూర్యోదయం కనుగొనండి",
    bodyEn:
      "Every Panchangam day starts at sunrise — not midnight. SunCalc computes sunrise for the user's exact lat/lng on the requested date.",
    bodyTe:
      "ప్రతి పంచాంగ రోజు సూర్యోదయంతో మొదలవుతుంది — అర్ధరాత్రి కాదు. SunCalc నగరం ఆధారంగా సూర్యోదయ సమయం లెక్కిస్తుంది.",
  },
  {
    num: 2,
    titleEn: "Compute Sun and Moon longitude",
    titleTe: "సూర్య చంద్ర రేఖాంశాలు లెక్కించండి",
    bodyEn:
      "Using the VSOP87 planetary theory, the engine computes the tropical ecliptic longitude of the Sun and Moon at sunrise — accurate to better than 1 arc-minute.",
    bodyTe:
      "VSOP87 గ్రహ సిద్ధాంతం ఉపయోగించి, సూర్యోదయ సమయంలో సూర్య మరియు చంద్ర స్థానాలను 1 ఆర్క్ నిమిషం ఖచ్చితత్వంతో లెక్కిస్తుంది.",
    formula: "λ_sun, λ_moon (tropical, J2000 ecliptic)",
  },
  {
    num: 3,
    titleEn: "Subtract Lahiri Ayanamsa",
    titleTe: "లాహిరి అయనాంశం తీసివేయండి",
    bodyEn:
      "Telugu Panchangam uses sidereal positions, not tropical. Subtract the Lahiri Ayanamsa (~24°) from each longitude to convert tropical → sidereal. This is the standard followed by Venkatrama & Co.",
    bodyTe:
      "తెలుగు పంచాంగం సైడెరియల్ స్థానాలు ఉపయోగిస్తుంది. ప్రతి రేఖాంశం నుండి లాహిరి అయనాంశం (~24°) తీసివేయండి.",
    formula: "λ_sidereal = λ_tropical − Ayanamsa",
  },
  {
    num: 4,
    titleEn: "Compute Tithi from elongation",
    titleTe: "ఎలాంగేషన్ నుండి తిథి లెక్కించండి",
    bodyEn:
      "Tithi is the angular difference between the Moon and Sun, measured in 12° units. There are 30 Tithis per lunar month — 15 Shukla (waxing) and 15 Krishna (waning).",
    bodyTe:
      "తిథి అనేది చంద్రుడు మరియు సూర్యుడి మధ్య కోణీయ తేడా, 12° యూనిట్లలో. ప్రతి చాంద్రమానం నెలలో 30 తిథులు ఉంటాయి.",
    formula: "tithi = floor((λ_moon − λ_sun) / 12°) + 1",
  },
  {
    num: 5,
    titleEn: "Compute Nakshatra from Moon",
    titleTe: "చంద్రుని నుండి నక్షత్రం లెక్కించండి",
    bodyEn:
      "The 360° ecliptic is divided into 27 Nakshatras of 13°20′ each. The Moon's sidereal longitude maps directly to one of them.",
    bodyTe:
      "360° ఎక్లిప్టిక్ 27 నక్షత్రాలుగా విభజించబడింది (ప్రతిది 13°20′). చంద్రుని సైడెరియల్ రేఖాంశం వాటిలో ఒకదానికి సంబంధిస్తుంది.",
    formula: "nakshatra = floor(λ_moon / 13°20′) + 1",
  },
  {
    num: 6,
    titleEn: "Yoga, Karana, Vara",
    titleTe: "యోగం, కరణం, వారం",
    bodyEn:
      "Yoga = (λ_sun + λ_moon) / 13°20′ → 27 yogas. Karana is half a Tithi → 11 karanas cycle. Vara is the weekday at sunrise (Sunday=1).",
    bodyTe:
      "యోగం = (λ_sun + λ_moon) / 13°20′ → 27 యోగాలు. కరణం = తిథిలో సగం → 11 కరణాలు. వారం = సూర్యోదయంలో వారపు రోజు.",
  },
];

// ─────────────────────────────────────────────────────────
// Section 3 — Five Panchanga elements (accordion)
// ─────────────────────────────────────────────────────────

type AngaKey = "tithi" | "nakshatra" | "yoga" | "karana" | "vara";

interface AngaItem {
  key: AngaKey;
  iconEn: string;
  nameEn: string;
  nameTe: string;
  shortEn: string;
  shortTe: string;
}

// The accordion's expanded what / how / example content lives in
// `ABOUT_ANGAS` in src/lib/i18n.ts, fully bilingual. This array
// only carries the chrome (icon, name, short subtitle).
const ANGAS: AngaItem[] = [
  {
    key: "tithi",
    iconEn: "🌑",
    nameEn: "Tithi",
    nameTe: "తిథి",
    shortEn: "Lunar day",
    shortTe: "చాంద్ర దినం",
  },
  {
    key: "nakshatra",
    iconEn: "✨",
    nameEn: "Nakshatra",
    nameTe: "నక్షత్రం",
    shortEn: "Lunar mansion",
    shortTe: "చంద్రుని ఇల్లు",
  },
  {
    key: "yoga",
    iconEn: "🧘",
    nameEn: "Yoga",
    nameTe: "యోగం",
    shortEn: "Sun + Moon angular sum",
    shortTe: "సూర్య + చంద్ర మొత్తం",
  },
  {
    key: "karana",
    iconEn: "⏳",
    nameEn: "Karana",
    nameTe: "కరణం",
    shortEn: "Half a Tithi",
    shortTe: "తిథిలో సగం",
  },
  {
    key: "vara",
    iconEn: "📅",
    nameEn: "Vara",
    nameTe: "వారం",
    shortEn: "Weekday at sunrise",
    shortTe: "సూర్యోదయంలో వారపు రోజు",
  },
];

// ─────────────────────────────────────────────────────────
// Section 4 — Live calculator
// ─────────────────────────────────────────────────────────

interface LivePanchangam {
  tithi: { te: string; en: string };
  nakshatra: { te: string; en: string };
  yoga: { te: string; en: string };
  karana: { te: string; en: string };
  vara: { te: string; en: string };
  sunrise: string;
}

// ─────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────

export default function AboutPage() {
  const [lang, setLang] = useState<Lang>("en");
  const [city, setCity] = useState<CityInfo | null>(null);

  // Engine player state
  const [stepIndex, setStepIndex] = useState(0);

  // Accordion state
  const [openAnga, setOpenAnga] = useState<string | null>(null);

  // Live calculator state
  const [live, setLive] = useState<LivePanchangam | null>(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    setLang(getLang());
    setCity(getCity());
  }, []);

  const fetchLive = useCallback(async () => {
    if (!city) return;
    setLiveLoading(true);
    setLiveError(null);
    try {
      const today = new Date();
      const date = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
      const res = await fetch(
        `/api/panchangam?date=${date}&lat=${city.lat}&lng=${city.lng}&tz=${encodeURIComponent(city.tz)}`
      );
      if (!res.ok) throw new Error("Failed to load");
      const json = await res.json();
      setLive(json.data);
    } catch (err) {
      setLiveError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLiveLoading(false);
    }
  }, [city]);

  useEffect(() => {
    if (city) fetchLive();
  }, [city, fetchLive]);

  const teClass = lang === "te" ? "font-noto-telugu" : "font-lora";
  const step = ENGINE_STEPS[stepIndex];

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      {/* Back link */}
      <Link
        href="/"
        className={`inline-flex items-center text-sm text-accent hover:underline mb-6 ${teClass}`}
      >
        ← {lang === "te" ? "పంచాంగానికి తిరిగి" : "Back to Panchangam"}
      </Link>

      {/* ─── Section 1 — Hero + Solar system ─── */}
      <section className="text-center mb-12">
        <h1 className="font-noto-telugu text-3xl text-accent mb-1">
          ఇది ఎలా పని చేస్తుంది
        </h1>
        <p className={`text-text-secondary text-lg italic mb-2 ${lang === "te" ? "font-noto-telugu" : "font-playfair"}`}>
          {lang === "te" ? "ఎలా పని చేస్తుంది" : "How it works"}
        </p>
        <div className="w-16 h-px bg-accent mx-auto mb-6" />

        {/* Solar system animation — pure CSS */}
        <div className="relative mx-auto mb-6" style={{ width: "260px", height: "260px" }}>
          {/* Sun */}
          <div className="absolute top-1/2 left-1/2 w-12 h-12 -mt-6 -ml-6 rounded-full bg-header-grad shadow-lg" />
          {/* Earth orbit */}
          <div
            className="absolute top-1/2 left-1/2 rounded-full border border-accent/20 animate-spin"
            style={{
              width: "200px",
              height: "200px",
              marginTop: "-100px",
              marginLeft: "-100px",
              animationDuration: "20s",
            }}
          >
            <div className="absolute top-0 left-1/2 -ml-3 -mt-3 w-6 h-6 rounded-full bg-text-primary/80" />
          </div>
          {/* Moon orbit (faster) */}
          <div
            className="absolute top-1/2 left-1/2 rounded-full border border-label/15 animate-spin"
            style={{
              width: "260px",
              height: "260px",
              marginTop: "-130px",
              marginLeft: "-130px",
              animationDuration: "5s",
            }}
          >
            <div className="absolute top-0 left-1/2 -ml-2 -mt-2 w-4 h-4 rounded-full bg-label/40" />
          </div>
        </div>

        <p className={`max-w-xl mx-auto text-text-secondary leading-relaxed ${teClass}`}>
          {lang === "te"
            ? "పంచాంగం అంటే ఆకాశం యొక్క గణితం — సూర్యుడు మరియు చంద్రుడి ఖచ్చితమైన స్థానాల నుండి మీ నగరంలో సూర్యోదయ సమయంలో లెక్కించబడుతుంది. కింది ఇంటరాక్టివ్ వివరణ ద్వారా చూడండి."
            : "A Panchangam is the mathematics of the sky — calculated from the precise positions of the Sun and Moon at sunrise in your city. Walk through the engine step by step below."}
        </p>
      </section>

      {/* ─── Section 2 — Engine player ─── */}
      <section className="mb-12">
        <h2 className={`text-xs font-semibold uppercase tracking-wider text-label mb-3 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {lang === "te" ? "ఇంజిన్ — దశల వారీ" : "The engine — step by step"}
        </h2>

        <div className="rounded-xl border border-accent/20 bg-cream p-6 shadow-sm">
          {/* Step badge */}
          <div className="flex items-center justify-between mb-4">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-header-grad text-white font-playfair text-lg font-bold">
              {step.num}
            </div>
            <div className="text-xs text-label/70 font-mono">
              {stepIndex + 1} / {ENGINE_STEPS.length}
            </div>
          </div>

          <h3 className="font-noto-telugu text-xl text-text-primary mb-1">
            {step.titleTe}
          </h3>
          <p className="font-playfair italic text-text-secondary mb-3">
            {step.titleEn}
          </p>

          <p className={`text-text-secondary text-sm leading-relaxed mb-4 ${teClass}`}>
            {lang === "te" ? step.bodyTe : step.bodyEn}
          </p>

          {step.formula && (
            <div className="font-mono text-xs bg-text-primary/[0.04] border border-label/10 rounded-md px-3 py-2 text-text-secondary mb-4 overflow-x-auto">
              {step.formula}
            </div>
          )}

          {/* Step 1 sunrise dot animation */}
          {step.num === 1 && (
            <div className="relative h-12 mb-4 overflow-hidden rounded-lg bg-gradient-to-r from-text-primary/10 via-header-grad/20 to-cream">
              <div className="absolute top-1/2 -mt-2 w-4 h-4 rounded-full bg-header-grad shadow-md animate-slide-in" />
            </div>
          )}

          {/* Player controls */}
          <div className="flex items-center justify-between mt-6">
            <button
              onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
              disabled={stepIndex === 0}
              className={`px-4 py-2 rounded-md border border-accent/30 text-sm text-accent disabled:opacity-30 disabled:cursor-not-allowed ${teClass}`}
            >
              ← {lang === "te" ? "వెనుకకు" : "Back"}
            </button>
            <button
              onClick={() => setStepIndex((i) => Math.min(ENGINE_STEPS.length - 1, i + 1))}
              disabled={stepIndex === ENGINE_STEPS.length - 1}
              className={`px-4 py-2 rounded-md bg-accent text-white text-sm disabled:opacity-30 disabled:cursor-not-allowed ${teClass}`}
            >
              {lang === "te" ? "తరువాత" : "Next"} →
            </button>
          </div>
        </div>
      </section>

      {/* ─── Section 3 — Five Panchanga elements ─── */}
      <section className="mb-12">
        <h2 className={`text-xs font-semibold uppercase tracking-wider text-label mb-3 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {lang === "te" ? "పంచాంగం యొక్క ఐదు అంగాలు" : "The five elements"}
        </h2>

        <div className="space-y-2">
          {ANGAS.map((a) => {
            const isOpen = openAnga === a.key;
            return (
              <div
                key={a.key}
                className="rounded-lg border border-label/10 bg-cream overflow-hidden"
              >
                <button
                  onClick={() => setOpenAnga(isOpen ? null : a.key)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-accent/[0.03] transition-colors"
                >
                  <span className="flex items-center gap-3">
                    <span className="text-2xl">{a.iconEn}</span>
                    <span>
                      <span className="font-noto-telugu text-text-primary block">
                        {a.nameTe}
                      </span>
                      <span className="font-playfair italic text-text-secondary text-sm">
                        {a.nameEn} — {lang === "te" ? a.shortTe : a.shortEn}
                      </span>
                    </span>
                  </span>
                  <span className="text-accent text-lg">{isOpen ? "−" : "+"}</span>
                </button>
                {isOpen && (
                  <div className="px-4 pb-4 border-t border-label/10 pt-3 space-y-3">
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider text-label mb-1 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
                        {ABOUT.whatLabel[lang]}
                      </div>
                      <p className={`text-sm text-text-secondary leading-relaxed ${teClass}`}>
                        {ABOUT_ANGAS[a.key].what[lang]}
                      </p>
                    </div>
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider text-label mb-1 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
                        {ABOUT.howLabel[lang]}
                      </div>
                      <p className={`text-sm text-text-secondary leading-relaxed ${teClass}`}>
                        {ABOUT_ANGAS[a.key].how[lang]}
                      </p>
                    </div>
                    <div>
                      <div className={`text-[10px] uppercase tracking-wider text-label mb-1 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
                        {ABOUT.exampleLabel[lang]}
                      </div>
                      <p className={`text-sm text-text-secondary leading-relaxed font-mono ${lang === "te" ? "font-noto-telugu" : ""}`}>
                        {ABOUT_ANGAS[a.key].example[lang]}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── Section 4 — Live calculator ─── */}
      <section className="mb-12">
        <h2 className={`text-xs font-semibold uppercase tracking-wider text-label mb-3 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {lang === "te" ? "ప్రత్యక్ష గణకం" : "Live calculator"}
        </h2>

        <div className="rounded-xl border-2 border-accent/30 bg-cream p-6">
          <p className={`text-xs text-label mb-3 ${teClass}`}>
            {lang === "te"
              ? `ఈ సంఖ్యలు ప్రత్యక్ష /api/panchangam నుండి${city ? ` — ${city.name}` : ""}`
              : `These numbers are live from /api/panchangam${city ? ` — ${city.name}` : ""}`}
          </p>

          {liveLoading && (
            <div className="text-center py-8 text-label animate-pulse">
              {lang === "te" ? "లోడ్ అవుతోంది..." : "Loading..."}
            </div>
          )}
          {liveError && (
            <div className="text-center py-8 text-danger text-sm">{liveError}</div>
          )}
          {live && !liveLoading && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              {(["tithi", "nakshatra", "yoga", "karana", "vara"] as const).map((key) => {
                const value = live[key];
                if (!value) return null;
                return (
                  <div
                    key={key}
                    className="p-3 rounded-lg border border-label/10 bg-text-primary/[0.02]"
                  >
                    <div className="text-[10px] uppercase tracking-wider text-label mb-1">
                      {key}
                    </div>
                    <div className="font-noto-telugu text-text-primary text-sm">
                      {value.te}
                    </div>
                    <div className="font-playfair italic text-text-secondary text-xs">
                      {value.en}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <button
            onClick={fetchLive}
            className={`mt-4 text-xs text-accent hover:underline ${teClass}`}
          >
            ↻ {lang === "te" ? "మళ్ళీ లెక్కించండి" : "Recalculate"}
          </button>
        </div>
      </section>

      {/* ─── Section 5 — Why this is different ─── */}
      <section className="mb-12">
        <h2 className={`text-xs font-semibold uppercase tracking-wider text-label mb-3 ${lang === "te" ? "font-noto-telugu normal-case" : ""}`}>
          {lang === "te" ? "ఇది ఎందుకు భిన్నం" : "Why this is different"}
        </h2>

        <div className="grid sm:grid-cols-2 gap-3">
          {[
            {
              icon: "🌍",
              en: "Any city",
              te: "ఏ నగరమైనా",
              body:
                "Worldwide accuracy — Sydney, London, Hyderabad, Vijayawada, anywhere. Sunrise computed at your exact lat/lng.",
            },
            {
              icon: "♾️",
              en: "Any date",
              te: "ఏ తేదీ అయినా",
              body:
                "No date limit. Past or future. The VSOP87 engine works from year 4000 BCE to year 8000 CE.",
            },
            {
              icon: "💰",
              en: "Free forever",
              te: "ఎప్పటికీ ఉచితం",
              body:
                "No ads. No subscriptions. No login. The mission is community service, not commerce.",
            },
            {
              icon: "🔓",
              en: "Open source (MIT)",
              te: "ఓపెన్ సోర్స్ (MIT)",
              body:
                "Every line of code is public. Fork it, embed it, study it, improve it. No proprietary lock-in.",
            },
            {
              icon: "🔌",
              en: "Free public API",
              te: "ఉచిత పబ్లిక్ API",
              body:
                "Seven endpoints, no API key, CORS enabled. Build your own apps on top of the same engine.",
            },
            {
              icon: "🙏",
              en: "Accuracy first",
              te: "ఖచ్చితత్వం మొదట",
              body:
                "Validated against the Venkatrama & Co. printed calendar. 127 unit tests. 26 regression assertions.",
            },
          ].map((card) => (
            <div key={card.en} className="rounded-lg border border-label/10 bg-cream p-4">
              <div className="text-2xl mb-1">{card.icon}</div>
              <div className="font-noto-telugu text-text-primary font-semibold">
                {card.te}
              </div>
              <div className="font-playfair italic text-text-secondary text-sm mb-2">
                {card.en}
              </div>
              <p className="text-xs text-text-secondary leading-relaxed font-lora">
                {card.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Footer call to action ─── */}
      <section className="text-center py-8 border-t border-label/10">
        <Link
          href="/"
          className={`inline-block px-6 py-3 rounded-lg bg-accent text-white text-sm font-semibold hover:opacity-90 transition-opacity ${teClass}`}
        >
          {lang === "te" ? "ఈ రోజు పంచాంగం తెరవండి →" : "Open today's Panchangam →"}
        </Link>
      </section>
    </main>
  );
}
