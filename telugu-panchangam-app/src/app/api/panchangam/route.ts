import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { calculateDayPanchangam } from "@/engine/panchangam";
import { getDB } from "@/lib/cloudflare";
import type { Location } from "@/engine/types";

export const runtime = "edge";

const querySchema = z.object({
  date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Date must be YYYY-MM-DD format"),
  lat: z.coerce
    .number()
    .min(-90, "Latitude must be between -90 and 90")
    .max(90),
  lng: z.coerce
    .number()
    .min(-180, "Longitude must be between -180 and 180")
    .max(180),
  tz: z.string().min(1, "Timezone is required"),
  lang: z.enum(["te", "en", "both"]).optional().default("both"),
});

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    date: searchParams.get("date"),
    lat: searchParams.get("lat"),
    lng: searchParams.get("lng"),
    tz: searchParams.get("tz"),
    lang: searchParams.get("lang") ?? undefined,
  });

  if (!parsed.success) {
    const firstError = parsed.error.issues[0];
    return NextResponse.json(
      {
        error: firstError.message,
        code: "MISSING_PARAM",
      },
      { status: 400 }
    );
  }

  const { date, lat, lng, tz } = parsed.data;

  // Validate the date is a real calendar date
  const [year, month, day] = date.split("-").map(Number);
  const testDate = new Date(year, month - 1, day);
  if (
    testDate.getFullYear() !== year ||
    testDate.getMonth() !== month - 1 ||
    testDate.getDate() !== day
  ) {
    return NextResponse.json(
      { error: "Invalid calendar date", code: "INVALID_DATE" },
      { status: 400 }
    );
  }

  // Validate timezone string
  try {
    Intl.DateTimeFormat("en", { timeZone: tz });
  } catch {
    return NextResponse.json(
      { error: `Unrecognised timezone: ${tz}`, code: "INVALID_TIMEZONE" },
      { status: 400 }
    );
  }

  try {
    const location: Location = {
      lat: Number(lat.toFixed(5)),
      lng: Number(lng.toFixed(5)),
      tz,
    };

    const cacheKey = `panchangam:${date}:${location.lat}:${location.lng}:${tz}`;
    const headers = {
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "public, max-age=86400",
    };

    // Check D1 cache
    const db = getDB();
    if (db) {
      try {
        const cached = await db
          .prepare("SELECT data FROM panchangam_cache WHERE cache_key = ?")
          .bind(cacheKey)
          .first();

        if (cached) {
          return NextResponse.json(
            {
              data: JSON.parse(cached.data),
              source: "cache" as const,
              computedAt: new Date().toISOString(),
            },
            { headers }
          );
        }
      } catch {
        // Cache miss or error — proceed to compute
      }
    }

    const data = calculateDayPanchangam(date, location);

    // Store in D1 cache (fire and forget)
    if (db) {
      db.prepare(
        "INSERT OR REPLACE INTO panchangam_cache (cache_key, data, created_at) VALUES (?, ?, ?)"
      )
        .bind(cacheKey, JSON.stringify(data), new Date().toISOString())
        .run()
        .catch(() => {});
    }

    return NextResponse.json(
      {
        data,
        source: "engine" as const,
        computedAt: new Date().toISOString(),
      },
      { headers }
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: message, code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }
}
