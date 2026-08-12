/**
 * Daily reminder cron worker.
 *
 * Hit by an external scheduler (GitHub Actions cron — see
 * .github/workflows/daily-reminders.yml) once a day. Authenticated by
 * a Bearer token whose value lives in the CRON_SECRET secret.
 *
 * For each active reminder row in D1 it computes today's panchangam
 * (or today + remind_days_before) at the user's city and, if the day
 * matches the user's chosen tithi types, sends an email via Resend.
 *
 * Idempotent within a calendar day: each row tracks last_sent_date
 * and is skipped if it has already fired today.
 */

export const runtime = "edge";

import { NextRequest, NextResponse } from "next/server";
import { Resend } from "resend";
import { calculateDayPanchangam } from "@/engine/panchangam";
import {
  matchReminder,
  todayInTimezone,
  addDaysISO,
  type StoredReminder,
} from "@/engine/reminderMatcher";
import { reminderEmail, anniversaryReminderEmail } from "@/lib/emailTemplates";
import { getDB, getEnvVar } from "@/lib/cloudflare";
import { APP_URL } from "@/lib/constants";

interface CronSummary {
  ok: true;
  scanned: number;
  sent: number;
  skipped_already_sent: number;
  no_match: number;
  errors: number;
  details: Array<{
    id: string;
    email: string;
    result: "sent" | "already_sent" | "no_match" | "error";
    kind?: string;
    error?: string;
  }>;
}

function unauthorized(msg: string) {
  return NextResponse.json({ error: msg, code: "UNAUTHORIZED" }, { status: 401 });
}

export async function POST(request: NextRequest) {
  // ─── 1. Authenticate ──────────────────────────────────────────
  const expected = getEnvVar("CRON_SECRET");
  if (!expected) {
    return NextResponse.json(
      { error: "CRON_SECRET not configured", code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }
  const authHeader = request.headers.get("authorization") ?? "";
  const provided = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (provided !== expected) return unauthorized("invalid bearer token");

  // ─── 2. Resolve dependencies ──────────────────────────────────
  const apiKey = getEnvVar("RESEND_API_KEY");
  const fromEmail = getEnvVar("RESEND_FROM_EMAIL");
  if (!apiKey || !fromEmail) {
    return NextResponse.json(
      { error: "Email service not configured", code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }

  const db = getDB();
  if (!db) {
    return NextResponse.json(
      { error: "Database not configured", code: "ENGINE_ERROR" },
      { status: 500 }
    );
  }

  // ─── 3. Load active reminders ─────────────────────────────────
  // We fetch ALL active rows (the table is small for v1; if it grows,
  // add an index on (active, last_sent_date) and filter server-side).
  type Row = {
    id: string;
    email: string;
    name: string;
    city_name: string;
    lat: number;
    lng: number;
    tz: string;
    tithi_types: string;
    reminder_type: string;
    remind_days_before: number;
    remind_time: string;
    personal_note: string | null;
    tithi_masa_number: number | null;
    tithi_paksha: string | null;
    tithi_number: number | null;
    tithi_description: string | null;
    unsubscribe_token: string;
    active: number;
    last_sent_date: string | null;
  };

  const queryResult = (await db
    .prepare("SELECT * FROM reminders WHERE active = 1")
    .all()) as { results: Row[] };
  const results = queryResult.results;

  const resend = new Resend(apiKey);
  const summary: CronSummary = {
    ok: true,
    scanned: results.length,
    sent: 0,
    skipped_already_sent: 0,
    no_match: 0,
    errors: 0,
    details: [],
  };

  // ─── 4. Process each row ──────────────────────────────────────
  for (const row of results) {
    try {
      // Hydrate the row into a typed StoredReminder
      let parsedTypes: string[] = [];
      try {
        parsedTypes = JSON.parse(row.tithi_types);
        if (!Array.isArray(parsedTypes)) parsedTypes = [];
      } catch {
        parsedTypes = [];
      }

      const reminder: StoredReminder = {
        id: row.id,
        email: row.email,
        name: row.name,
        city_name: row.city_name,
        lat: row.lat,
        lng: row.lng,
        tz: row.tz,
        tithi_types: parsedTypes,
        reminder_type:
          row.reminder_type === "ekadashi" ||
          row.reminder_type === "tithi_anniversary"
            ? row.reminder_type
            : "amavasya",
        remind_days_before: row.remind_days_before,
        remind_time: row.remind_time,
        personal_note: row.personal_note,
        tithi_masa_number: row.tithi_masa_number,
        tithi_paksha:
          row.tithi_paksha === "shukla" || row.tithi_paksha === "krishna"
            ? row.tithi_paksha
            : null,
        tithi_number: row.tithi_number,
        tithi_description: row.tithi_description,
        unsubscribe_token: row.unsubscribe_token,
        active: row.active,
        last_sent_date: row.last_sent_date,
      };

      // Compute the date this row is asking about: today + N in user's tz
      const todayLocal = todayInTimezone(reminder.tz);
      if (reminder.last_sent_date === todayLocal) {
        summary.skipped_already_sent += 1;
        summary.details.push({
          id: reminder.id,
          email: reminder.email,
          result: "already_sent",
        });
        continue;
      }

      const targetDate = addDaysISO(todayLocal, reminder.remind_days_before);

      // Calculate panchangam for the target date at user's city
      const p = calculateDayPanchangam(targetDate, {
        lat: reminder.lat,
        lng: reminder.lng,
        tz: reminder.tz,
      });

      const match = matchReminder(reminder, p);
      if (!match.matched) {
        summary.no_match += 1;
        summary.details.push({
          id: reminder.id,
          email: reminder.email,
          result: "no_match",
        });
        continue;
      }

      // Build the email
      const unsubscribeUrl = `${APP_URL}/api/reminders/unsubscribe?token=${reminder.unsubscribe_token}`;
      const sunriseTime = p.sunrise
        ? new Date(p.sunrise).toLocaleTimeString("en-AU", {
            hour: "2-digit",
            minute: "2-digit",
            timeZone: reminder.tz,
          })
        : "--:--";
      const isMahalaya =
        match.kind === "amavasya" &&
        p.masa.number === 7 &&
        p.paksha.value === "krishna";
      const isSomavati = match.kind === "amavasya" && p.vara.number === 1;

      const template =
        match.kind === "tithi_anniversary"
          ? anniversaryReminderEmail({
              name: reminder.name,
              tithi: { te: match.te ?? p.tithi.te, en: match.en ?? p.tithi.en },
              tithiDescription:
                reminder.tithi_description ??
                `${p.masa.en} ${p.paksha.value === "shukla" ? "Shukla" : "Krishna"} ${p.tithi.en}`,
              date: targetDate,
              gregorianDate: targetDate,
              sunriseTime,
              city_name: reminder.city_name,
              personal_note: reminder.personal_note ?? undefined,
              daysUntil: reminder.remind_days_before,
              unsubscribe_url: unsubscribeUrl,
              app_url: APP_URL,
            })
          : reminderEmail({
              name: reminder.name,
              tithi: { te: match.te ?? p.tithi.te, en: match.en ?? p.tithi.en },
              date: targetDate,
              gregorianDate: targetDate,
              sunriseTime,
              city_name: reminder.city_name,
              personal_note: reminder.personal_note ?? undefined,
              isMahalaya,
              isSomavati,
              daysUntil: reminder.remind_days_before,
              unsubscribe_url: unsubscribeUrl,
              app_url: APP_URL,
            });

      await resend.emails.send({
        from: fromEmail,
        to: reminder.email,
        subject: template.subject,
        html: template.html,
      });

      // Mark sent
      await db
        .prepare(
          "UPDATE reminders SET last_sent_date = ?, last_sent_kind = ?, updated_at = ? WHERE id = ?"
        )
        .bind(todayLocal, match.kind ?? "unknown", new Date().toISOString(), reminder.id)
        .run();

      summary.sent += 1;
      summary.details.push({
        id: reminder.id,
        email: reminder.email,
        result: "sent",
        kind: match.kind,
      });
    } catch (err) {
      summary.errors += 1;
      summary.details.push({
        id: row.id,
        email: row.email,
        result: "error",
        error: err instanceof Error ? err.message : "unknown",
      });
    }
  }

  return NextResponse.json(summary);
}
