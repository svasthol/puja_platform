export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { getMuhurtamWindows } from "@/engine/muhurtam";

const querySchema = z.object({
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Date must be YYYY-MM-DD"),
  days: z.coerce.number().int().min(1).max(30).default(7),
  lat: z.coerce.number().min(-90).max(90),
  lng: z.coerce.number().min(-180).max(180),
  tz: z.string().min(1, "Timezone is required"),
});

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    from: searchParams.get("from"),
    days: searchParams.get("days") ?? 7,
    lat: searchParams.get("lat"),
    lng: searchParams.get("lng"),
    tz: searchParams.get("tz"),
  });

  if (!parsed.success) {
    const firstError = parsed.error.issues[0];
    return NextResponse.json(
      { error: firstError.message, code: "MISSING_PARAM" },
      { status: 400 }
    );
  }

  const { from, days, lat, lng, tz } = parsed.data;

  try {
    Intl.DateTimeFormat("en", { timeZone: tz });
  } catch {
    return NextResponse.json(
      { error: `Unrecognised timezone: ${tz}`, code: "INVALID_TIMEZONE" },
      { status: 400 }
    );
  }

  try {
    const windows = getMuhurtamWindows(
      from,
      days,
      Number(lat.toFixed(5)),
      Number(lng.toFixed(5)),
      tz
    );

    return NextResponse.json(
      { data: windows, computedAt: new Date().toISOString() },
      {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Cache-Control": "public, max-age=3600",
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
