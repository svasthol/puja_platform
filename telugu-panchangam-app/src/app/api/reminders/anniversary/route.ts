export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getTithiForDate, findTithiAnniversaries } from "@/engine/reminders";
import { getKV } from "@/lib/cloudflare";

const querySchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  origin_lat: z.coerce.number().min(-90).max(90),
  origin_lng: z.coerce.number().min(-180).max(180),
  origin_tz: z.string().min(1),
  lat: z.coerce.number().min(-90).max(90),
  lng: z.coerce.number().min(-180).max(180),
  tz: z.string().min(1),
  from_year: z.coerce.number().int().optional(),
  to_year: z.coerce.number().int().optional(),
});

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Cache-Control": "public, max-age=86400",
};

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    date: sp.get("date"),
    origin_lat: sp.get("origin_lat"),
    origin_lng: sp.get("origin_lng"),
    origin_tz: sp.get("origin_tz"),
    lat: sp.get("lat"),
    lng: sp.get("lng"),
    tz: sp.get("tz"),
    from_year: sp.get("from_year") ?? undefined,
    to_year: sp.get("to_year") ?? undefined,
  });

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues[0].message, code: "MISSING_PARAM" },
      { status: 400, headers: CORS_HEADERS }
    );
  }

  const { date, origin_lat, origin_lng, origin_tz, lat, lng, tz } = parsed.data;
  const now = new Date();
  const currentYear = now.getFullYear();
  const fromYear = parsed.data.from_year ?? currentYear;
  // Default span reduced from 10 → 5 years so a first uncached request
  // fits inside the Cloudflare edge CPU budget. Users can still pick
  // 10/15/25 from the dropdown — those hits will rely on KV cache below.
  const toYear = parsed.data.to_year ?? currentYear + 4;
  const todayDate = `${currentYear}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

  // KV cache key — anniversary Tithis for a given (date, origin, span)
  // do not change, so we can cache aggressively.
  // The "v2" version tag invalidates pre-fix cache entries that were
  // computed with the old samvatsaram-relative year semantics for
  // masas 11/12 (Magha/Phalguna) and the narrower 41-day scan window.
  const cacheKey =
    `anniversary-v2:${date}:${origin_lat.toFixed(3)}:${origin_lng.toFixed(3)}` +
    `:${lat.toFixed(3)}:${lng.toFixed(3)}:${fromYear}:${toYear}`;

  const kv = getKV();
  if (kv) {
    try {
      const cached = await kv.get(cacheKey);
      if (cached) {
        return NextResponse.json(JSON.parse(cached), {
          headers: { ...CORS_HEADERS, "X-Cache": "HIT" },
        });
      }
    } catch {
      // ignore cache read failures
    }
  }

  try {
    const tithiIdentity = getTithiForDate(date, origin_lat, origin_lng, origin_tz);
    const occurrences = findTithiAnniversaries(
      tithiIdentity, fromYear, toYear, lat, lng, tz, todayDate
    );

    const payload = {
      data: {
        tithiIdentity,
        occurrences,
        originalDate: date,
      },
    };

    // Write-through cache (24 h) — best-effort, never blocks the response
    if (kv) {
      try {
        await kv.put(cacheKey, JSON.stringify(payload), { expirationTtl: 86400 });
      } catch {
        // ignore cache write failures
      }
    }

    return NextResponse.json(payload, {
      headers: { ...CORS_HEADERS, "X-Cache": "MISS" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: message, code: "ENGINE_ERROR" },
      { status: 500, headers: CORS_HEADERS }
    );
  }
}
