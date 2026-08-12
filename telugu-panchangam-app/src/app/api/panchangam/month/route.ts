export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { calculateDayPanchangam } from "@/engine/panchangam";
import { isEkadashi, isAmavasya, isPurnima } from "@/engine/tithi";
import type { Location } from "@/engine/types";

const querySchema = z.object({
  year: z.coerce.number().int(),
  month: z.coerce.number().int().min(1).max(12),
  lat: z.coerce.number().min(-90).max(90),
  lng: z.coerce.number().min(-180).max(180),
  tz: z.string().min(1, "Timezone is required"),
});

/** Moon phase to emoji */
function moonEmoji(phase: number): string {
  if (phase < 0.03 || phase >= 0.97) return "\u{1F311}"; // new moon
  if (phase < 0.22) return "\u{1F312}"; // waxing crescent
  if (phase < 0.28) return "\u{1F313}"; // first quarter
  if (phase < 0.47) return "\u{1F314}"; // waxing gibbous
  if (phase < 0.53) return "\u{1F315}"; // full moon
  if (phase < 0.72) return "\u{1F316}"; // waning gibbous
  if (phase < 0.78) return "\u{1F317}"; // last quarter
  return "\u{1F318}"; // waning crescent
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;

  const parsed = querySchema.safeParse({
    year: searchParams.get("year"),
    month: searchParams.get("month"),
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

  const { year, month, lat, lng, tz } = parsed.data;

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

    const daysInMonth = new Date(year, month, 0).getDate();
    const days = [];

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const p = calculateDayPanchangam(dateStr, location);

      days.push({
        date: dateStr,
        gregorianDay: day,
        vara: p.vara,
        tithi: {
          te: p.tithi.te,
          en: p.tithi.en,
          number: p.tithi.number,
        },
        nakshatra: {
          te: p.nakshatra.te,
          en: p.nakshatra.en,
          number: p.nakshatra.number,
        },
        paksha: p.paksha.value,
        moonPhaseEmoji: moonEmoji(p.moonPhase.phase),
        moonPhase: {
          illuminationPercent: p.moonPhase.illuminationPercent,
          phase: p.moonPhase.phase,
        },
        festivals: p.festivals,
        isEkadashi: isEkadashi(p.tithi.number),
        isAmavasya: isAmavasya(p.tithi.number),
        isPurnima: isPurnima(p.tithi.number),
      });
    }

    // Get samvatsaram and masa from first day
    const firstDay = calculateDayPanchangam(
      `${year}-${String(month).padStart(2, "0")}-01`,
      location
    );

    return NextResponse.json(
      {
        data: {
          year,
          month,
          samvatsaram: firstDay.samvatsaram,
          masa: firstDay.masa,
          days,
        },
        source: "engine" as const,
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
