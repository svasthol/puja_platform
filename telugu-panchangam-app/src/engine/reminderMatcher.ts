/**
 * Pure matching logic for the daily reminder cron worker.
 *
 * Given a stored reminder row and a calculated DayPanchangam for the
 * target date (today + remind_days_before, in the user's timezone),
 * decide whether the reminder should fire today and what label to use
 * in the email subject.
 *
 * Kept as a pure function so it can be unit-tested without running the
 * Cloudflare edge runtime, D1, or Resend.
 */

import type { DayPanchangam } from "./types";

export type ReminderKind =
  | "amavasya"
  | "ekadashi"
  | "purnima"
  | "tithi_anniversary";

export interface StoredReminder {
  id: string;
  email: string;
  name: string;
  city_name: string;
  lat: number;
  lng: number;
  tz: string;
  /** Parsed JSON array — e.g. ["amavasya", "ekadashi"] */
  tithi_types: string[];
  reminder_type: ReminderKind;
  remind_days_before: number;
  remind_time: string;
  personal_note?: string | null;
  /** For tithi_anniversary rows: the original masa+paksha+tithi to match */
  tithi_masa_number?: number | null;
  tithi_paksha?: "shukla" | "krishna" | null;
  /**
   * Paksha-relative tithi number (1-15). Matches the convention used by
   * `TithiIdentity` and the POST /api/reminders schema. The matcher
   * converts this to the absolute 1-30 number used by `DayPanchangam.tithi.number`
   * before comparison: `absolute = paksha === 'shukla' ? n : n + 15`.
   */
  tithi_number?: number | null;
  tithi_description?: string | null;
  unsubscribe_token: string;
  active: number;
  /** YYYY-MM-DD of the day a reminder was last sent for this row */
  last_sent_date?: string | null;
}

export interface MatchResult {
  matched: boolean;
  kind?: ReminderKind;
  /** Telugu label for the email subject */
  te?: string;
  /** English label for the email subject */
  en?: string;
}

/**
 * Decide whether the reminder should fire for the given panchangam.
 *
 * For an Amavasya/Ekadashi/Purnima monthly reminder, this returns
 * matched=true when the panchangam tithi is the matching one and the
 * user opted in to that tithi type.
 *
 * For a tithi_anniversary row, returns matched=true when the panchangam
 * masa+paksha+tithi exactly equal the stored target. Adhika months are
 * skipped — the anniversary always falls in the regular month.
 */
export function matchReminder(
  reminder: StoredReminder,
  p: DayPanchangam
): MatchResult {
  // 1. Tithi anniversary — match on exact (masa, paksha, tithi)
  if (reminder.reminder_type === "tithi_anniversary") {
    if (
      reminder.tithi_masa_number != null &&
      reminder.tithi_paksha != null &&
      reminder.tithi_number != null &&
      p.masa.number === reminder.tithi_masa_number &&
      !p.masa.isAdhika &&
      p.paksha.value === reminder.tithi_paksha
    ) {
      // Convert paksha-relative (1-15) to absolute (1-30) for comparison
      // against DayPanchangam.tithi.number which is always absolute.
      const absoluteTarget =
        reminder.tithi_paksha === "shukla"
          ? reminder.tithi_number
          : reminder.tithi_number + 15;
      if (p.tithi.number === absoluteTarget) {
        return {
          matched: true,
          kind: "tithi_anniversary",
          te: p.tithi.te,
          en: reminder.tithi_description ?? p.tithi.en,
        };
      }
    }
    return { matched: false };
  }

  // 2. Monthly tithi reminders — Amavasya / Ekadashi / Purnima
  // tithi_types is the user's opt-in list. We fire on the FIRST match.
  for (const want of reminder.tithi_types) {
    if (want === "amavasya" && p.tithi.number === 30) {
      return { matched: true, kind: "amavasya", te: p.tithi.te, en: p.tithi.en };
    }
    if (want === "ekadashi" && (p.tithi.number === 11 || p.tithi.number === 26)) {
      return { matched: true, kind: "ekadashi", te: p.tithi.te, en: p.tithi.en };
    }
    if (want === "purnima" && p.tithi.number === 15) {
      return { matched: true, kind: "purnima", te: p.tithi.te, en: p.tithi.en };
    }
  }

  return { matched: false };
}

/**
 * Add `days` to a YYYY-MM-DD string, returning the new date string.
 * Used by the cron loop to compute today + remind_days_before in the
 * user's local timezone.
 */
export function addDaysISO(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  const ny = dt.getUTCFullYear();
  const nm = String(dt.getUTCMonth() + 1).padStart(2, "0");
  const nd = String(dt.getUTCDate()).padStart(2, "0");
  return `${ny}-${nm}-${nd}`;
}

/**
 * Returns today's date as YYYY-MM-DD in the given IANA timezone.
 * Edge runtime cron jobs always run in UTC; this lets us pin "today"
 * to the user's local calendar so a Melbourne user gets their reminder
 * on the right day.
 */
export function todayInTimezone(tz: string, now: Date = new Date()): string {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  // en-CA produces YYYY-MM-DD
  return formatter.format(now);
}
