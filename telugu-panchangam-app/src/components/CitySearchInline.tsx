"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CityInfo } from "@/lib/cache";

interface GeocodeResult {
  displayName: string;
  lat: number;
  lng: number;
  timezone: string;
}

interface CitySearchInlineProps {
  placeholder: string;
  cancelLabel: string;
  searchingLabel: string;
  onSelect: (city: CityInfo) => void;
  onCancel: () => void;
}

/**
 * Minimal inline city search used by the anniversary / birthday forms
 * to override the saved app city for a single calculation. Does not
 * touch localStorage — the parent component decides what to do with
 * the selected city.
 */
export default function CitySearchInline({
  placeholder,
  cancelLabel,
  searchingLabel,
  onSelect,
  onCancel,
}: CitySearchInlineProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) setResults(Array.isArray(json.data) ? json.data : [json.data]);
      }
    } catch {
      /* ignore */
    } finally {
      setSearching(false);
    }
  }, []);

  const handleInput = useCallback(
    (value: string) => {
      setQuery(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => search(value), 300);
    },
    [search]
  );

  return (
    <div className="relative">
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          placeholder={placeholder}
          className="flex-1 px-3 py-2 rounded-md border border-accent/30 bg-cream text-text-primary text-sm font-lora focus:outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-2 rounded-md border border-label/20 text-xs text-label hover:bg-label/5 font-lora"
        >
          {cancelLabel}
        </button>
      </div>
      {searching && <div className="text-[10px] text-label mt-1">{searchingLabel}</div>}
      {results.length > 0 && (
        <ul className="absolute z-20 left-0 right-0 mt-1 bg-cream border border-label/20 rounded-lg shadow-lg max-h-40 overflow-y-auto">
          {results.map((r, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() =>
                  onSelect({
                    name: r.displayName.split(",")[0],
                    lat: r.lat,
                    lng: r.lng,
                    tz: r.timezone,
                  })
                }
                className="w-full text-left px-3 py-2 text-sm hover:bg-label/10 text-text-primary"
              >
                {r.displayName}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
