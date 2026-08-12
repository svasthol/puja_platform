export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getJanmaNakshatra } from "@/engine/nakshatra";

const querySchema = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Date must be YYYY-MM-DD"),
  time: z.string().regex(/^\d{2}:\d{2}$/, "Time must be HH:MM"),
  lat: z.coerce.number().min(-90).max(90),
  lng: z.coerce.number().min(-180).max(180),
  tz: z.string().min(1, "Timezone is required"),
  today_lat: z.coerce.number().min(-90).max(90).optional(),
  today_lng: z.coerce.number().min(-180).max(180).optional(),
  today_tz: z.string().min(1).optional(),
});

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    date: searchParams.get("date"),
    time: searchParams.get("time"),
    lat: searchParams.get("lat"),
    lng: searchParams.get("lng"),
    tz: searchParams.get("tz"),
    today_lat: searchParams.get("today_lat") ?? undefined,
    today_lng: searchParams.get("today_lng") ?? undefined,
    today_tz: searchParams.get("today_tz") ?? undefined,
  });

  if (!parsed.success) {
    const firstError = parsed.error.issues[0];
    return NextResponse.json(
      { error: firstError.message, code: "MISSING_PARAM" },
      { status: 400 }
    );
  }

  const { date, time, lat, lng, tz, today_lat, today_lng, today_tz } =
    parsed.data;

  try {
    Intl.DateTimeFormat("en", { timeZone: tz });
    if (today_tz) Intl.DateTimeFormat("en", { timeZone: today_tz });
  } catch {
    return NextResponse.json(
      { error: "Unrecognised timezone", code: "INVALID_TIMEZONE" },
      { status: 400 }
    );
  }

  // Build today's date string
  const now = new Date();
  const todayDate = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

  try {
    const result = getJanmaNakshatra(
      date,
      time,
      Number(lat.toFixed(5)),
      Number(lng.toFixed(5)),
      tz,
      today_lat !== undefined ? Number(today_lat.toFixed(5)) : undefined,
      today_lng !== undefined ? Number(today_lng.toFixed(5)) : undefined,
      today_tz,
      today_lat !== undefined ? todayDate : undefined
    );

    return NextResponse.json(
      {
        data: result,
        disclaimer:
          "Nakshatra is calculated from the Moon's position at birth. This is time-based astronomy. No predictions are made.",
        computedAt: new Date().toISOString(),
      },
      {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "public, max-age=86400",
        },
      }
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { error: message, code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }
}
