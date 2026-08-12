export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getEnvVar } from "@/lib/cloudflare";

const querySchema = z.object({
  q: z.string().min(1, "Query is required"),
});

const OPENCAGE_BASE = "https://api.opencagedata.com/geocode/v1/json";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    q: searchParams.get("q"),
  });

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0].message, code: "MISSING_PARAM" },
      { status: 400 }
    );
  }

  const apiKey = getEnvVar("OPENCAGE_API_KEY");
  if (!apiKey) {
    return NextResponse.json(
      { error: "Geocoding service not configured", code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }

  try {
    // Bias OpenCage toward city-level results — no street addresses,
    // POIs, or shop names — and ask for higher confidence.
    const url =
      `${OPENCAGE_BASE}?q=${encodeURIComponent(parsed.data.q)}` +
      `&key=${apiKey}` +
      `&limit=10` +
      `&no_annotations=0` +
      `&min_confidence=3`;
    const res = await fetch(url);

    if (!res.ok) {
      return NextResponse.json(
        { error: "Geocoding service error", code: "ENGINE_ERROR" },
        { status: 502 }
      );
    }

    interface OpenCageComponent {
      _type?: string;
      city?: string;
      town?: string;
      village?: string;
      municipality?: string;
      county?: string;
      state_district?: string;
      state?: string;
      country?: string;
    }
    interface OpenCageResult {
      formatted: string;
      geometry: { lat: number; lng: number };
      annotations?: { timezone?: { name?: string } };
      components?: OpenCageComponent;
    }

    const CITY_TYPES = new Set([
      "city",
      "town",
      "village",
      "municipality",
      "county",
      "state_district",
    ]);

    const json = await res.json();
    const raw: OpenCageResult[] = json.results ?? [];

    // Keep only city-level entries; fall back to all results if none.
    const cityResults = raw.filter((r) => {
      const t = r.components?._type;
      return t ? CITY_TYPES.has(t) : false;
    });
    const filtered = cityResults.length > 0 ? cityResults : raw;

    // Build clean "City, State, Country" labels and de-duplicate by name.
    const seen = new Set<string>();
    const results = filtered
      .map((r) => {
        const c = r.components ?? {};
        // Strip "City of " prefix that some councils use as the legal name
        // (e.g. "City of Melbourne" → "Melbourne").
        const rawCity =
          c.city || c.town || c.village || c.municipality || c.county || c.state_district || "";
        const cityName = rawCity.replace(/^City of /i, "");
        const parts = [cityName, c.state, c.country].filter(Boolean);
        const displayName = parts.length > 0 ? parts.join(", ") : r.formatted;
        return {
          displayName,
          lat: r.geometry.lat,
          lng: r.geometry.lng,
          timezone: r.annotations?.timezone?.name ?? "UTC",
          country: c.country ?? "",
          state: c.state ?? "",
        };
      })
      .filter((city) => {
        if (!city.displayName || seen.has(city.displayName)) return false;
        seen.add(city.displayName);
        return true;
      })
      .slice(0, 5);

    return NextResponse.json(
      { data: results, source: "opencage" },
      {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "public, max-age=86400",
        },
      }
    );
  } catch {
    return NextResponse.json(
      { error: "Geocoding request failed", code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }
}
