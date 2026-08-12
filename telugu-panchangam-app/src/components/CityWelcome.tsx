"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { hasCity, setCity } from "@/lib/cache";
import type { CityInfo } from "@/lib/cache";
import { isNonIndianTimezone } from "@/engine/timezone";

interface GeocodeResult {
  displayName: string;
  lat: number;
  lng: number;
  timezone: string;
}

interface CityWelcomeProps {
  /** If true, show "Change your city" mode with dismiss button */
  isChanging?: boolean;
  onDismiss?: () => void;
}

const QUICK_CITIES: (CityInfo & { country: string })[] = [
  { name: "Melbourne", lat: -37.8136, lng: 144.9631, tz: "Australia/Melbourne", country: "Australia" },
  { name: "Sydney", lat: -33.8688, lng: 151.2093, tz: "Australia/Sydney", country: "Australia" },
  { name: "Hyderabad", lat: 17.385, lng: 78.4867, tz: "Asia/Kolkata", country: "India" },
  { name: "Vijayawada", lat: 16.5062, lng: 80.648, tz: "Asia/Kolkata", country: "India" },
  { name: "London", lat: 51.5074, lng: -0.1278, tz: "Europe/London", country: "UK" },
  { name: "New York", lat: 40.7128, lng: -74.006, tz: "America/New_York", country: "USA" },
  { name: "Singapore", lat: 1.3521, lng: 103.8198, tz: "Asia/Singapore", country: "Singapore" },
  { name: "Dubai", lat: 25.2048, lng: 55.2708, tz: "Asia/Dubai", country: "UAE" },
];

export default function CityWelcome({ isChanging, onDismiss }: CityWelcomeProps) {
  const [needsCity, setNeedsCity] = useState(false);
  const [selectedCity, setSelectedCity] = useState<CityInfo | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isChanging) {
      setNeedsCity(true);
    } else if (!hasCity()) {
      setNeedsCity(true);
    }

    // Listen for "change city" requests from header
    const handler = () => {
      setNeedsCity(true);
      setSelectedCity(null);
    };
    window.addEventListener("city-change-requested", handler);
    return () => window.removeEventListener("city-change-requested", handler);
  }, [isChanging]);

  useEffect(() => {
    if (needsCity && inputRef.current) {
      inputRef.current.focus();
    }
  }, [needsCity]);

  const searchCity = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) setResults(Array.isArray(json.data) ? json.data : [json.data]);
      }
    } catch { /* ignore */ }
    finally { setSearching(false); }
  }, []);

  const handleInput = useCallback((value: string) => {
    setQuery(value);
    setSelectedCity(null);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => searchCity(value), 300);
  }, [searchCity]);

  const selectCity = useCallback((city: CityInfo) => {
    setSelectedCity(city);
    setQuery("");
    setResults([]);
  }, []);

  const confirm = useCallback(() => {
    if (!selectedCity) return;
    setCity(selectedCity);
    setNeedsCity(false);
    if (onDismiss) onDismiss();
    window.location.reload();
  }, [selectedCity, onDismiss]);

  if (!needsCity) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      data-testid="city-welcome"
      className="fixed inset-0 z-[200] bg-cream flex flex-col items-center overflow-y-auto"
    >
      {/* Header gradient bar */}
      <div className="w-full bg-header-grad py-4 text-center">
        <div className="font-noto-telugu text-white text-xl">తెలుగు పంచాంగం</div>
        <div className="font-playfair italic text-white/80 text-sm">Telugu Panchangam</div>
      </div>

      <div className="w-full max-w-md px-6 py-8">
        {/* Heading */}
        <div className="text-center mb-6">
          {/* Show close button if user already has a city (changing mode) */}
          {hasCity() && (
            <button
              onClick={() => { setNeedsCity(false); if (onDismiss) onDismiss(); }}
              className="fixed top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-label/10 text-text-secondary hover:bg-label/20 text-lg z-[201]"
              aria-label="Close"
            >
              &times;
            </button>
          )}
          <h1 className="font-playfair text-2xl text-text-primary mb-2">
            {isChanging || hasCity() ? "Change your city" : (
              <><span className="font-noto-telugu">నమస్కారం</span> — Welcome</>
            )}
          </h1>
          <p className="font-lora text-text-secondary text-sm leading-relaxed">
            To show accurate sunrise times and Panchangam data, we need to know your city.
          </p>
          <p className="font-lora italic text-label/60 text-xs mt-2 leading-relaxed">
            Panchangam timings vary by location. A puja in Melbourne and a puja in Hyderabad start at different times.
          </p>
          <a
            href="/about"
            className="inline-block font-lora text-xs text-accent hover:underline mt-3"
          >
            See how it works →
          </a>
        </div>

        {/* Quick select cities */}
        {!selectedCity && (
          <>
            <div className="flex flex-wrap justify-center gap-2 mb-6">
              {QUICK_CITIES.map((c) => (
                <button
                  key={c.name}
                  onClick={() => selectCity(c)}
                  className="px-3 py-1.5 text-sm rounded-full border border-accent/40 text-text-secondary hover:bg-accent hover:text-white hover:border-accent transition-all font-lora"
                >
                  {c.name}
                  <span className="text-xs text-label/50 ml-1">{c.country}</span>
                </button>
              ))}
            </div>

            {/* Divider */}
            <div className="flex items-center gap-3 mb-4">
              <div className="h-px flex-1 bg-label/15" />
              <span className="font-lora italic text-xs text-label/50">or search for your city</span>
              <div className="h-px flex-1 bg-label/15" />
            </div>

            {/* Search */}
            <div className="relative mb-4">
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => handleInput(e.target.value)}
                placeholder="Search any city worldwide..."
                className="w-full px-4 py-3 rounded-lg border border-label/20 bg-white text-text-primary text-sm font-lora focus:outline-none focus:border-accent placeholder:text-label/40"
              />
              {searching && (
                <div className="absolute right-3 top-3 text-xs text-label animate-pulse">Searching...</div>
              )}
              {results.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-label/20 rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
                  {results.map((r, i) => (
                    <button
                      key={i}
                      onClick={() => selectCity({
                        name: r.displayName.split(",")[0],
                        lat: r.lat,
                        lng: r.lng,
                        tz: r.timezone,
                      })}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-label/5 text-text-primary transition-colors border-b border-label/5 last:border-b-0"
                    >
                      {r.displayName}
                    </button>
                  ))}
                </div>
              )}
              {query.length >= 2 && !searching && results.length === 0 && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-label/20 rounded-lg px-4 py-2 text-sm text-label">
                  No results found
                </div>
              )}
            </div>
          </>
        )}

        {/* Confirmation */}
        {selectedCity && (
          <div className="text-center mt-4">
            <div className="inline-flex items-center gap-2 bg-auspicious/10 text-auspicious px-4 py-2 rounded-full text-sm font-semibold mb-4">
              <span>&#x1F4CD;</span>
              <span className="font-lora">{selectedCity.name}</span>
            </div>
            <p className="font-lora text-text-secondary text-sm mb-2">
              Showing Panchangam for <strong>{selectedCity.name}</strong>
            </p>
            {isNonIndianTimezone(selectedCity.tz) && (
              <p className="text-xs font-lora text-text-secondary italic mt-2 mb-6">
                &#x1F30D; Timings will be shown for {selectedCity.name}. Festival dates may differ by one day from Indian printed calendars.
              </p>
            )}
            <button
              onClick={confirm}
              className="w-full py-3 rounded-lg bg-header-grad text-white font-lora text-sm font-semibold hover:opacity-90 transition-opacity"
            >
              Continue &rarr;
            </button>
            <button
              onClick={() => setSelectedCity(null)}
              className="mt-3 text-xs text-label hover:text-accent transition-colors font-lora"
            >
              Choose a different city
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
