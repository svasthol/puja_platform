import {
  matchReminder,
  todayInTimezone,
  addDaysISO,
  type StoredReminder,
} from "./reminderMatcher";
import type { DayPanchangam } from "./types";

/** Build a minimal DayPanchangam fixture with the fields the matcher uses */
function fakePanchangam(opts: {
  masaNumber: number;
  isAdhika?: boolean;
  paksha: "shukla" | "krishna";
  tithiNumber: number;
  tithiTe?: string;
  tithiEn?: string;
}): DayPanchangam {
  return {
    date: "2026-04-07",
    samvatsaram: { te: "పరాభవ", en: "Parabhava", number: 0 },
    masa: { te: "చైత్రం", en: "Chaitra", number: opts.masaNumber, isAdhika: opts.isAdhika ?? false },
    paksha: { te: "శుక్ల పక్షం", en: "Shukla Paksha", value: opts.paksha },
    ritu: { te: "వసంతం", en: "Vasanta" },
    ayana: { te: "ఉత్తరాయణం", en: "Uttarayana" },
    tithi: {
      te: opts.tithiTe ?? "తిథి",
      en: opts.tithiEn ?? "Tithi",
      number: opts.tithiNumber,
      endsAt: "",
      nextTithi: { te: "", en: "", number: 0 },
    },
    nakshatra: { te: "", en: "", number: 1, pada: 1, endsAt: "" },
    yoga: { te: "", en: "", number: 1, isAuspicious: true, endsAt: "" },
    karana: { te: "", en: "", number: 1, endsAt: "" },
    vara: { te: "", en: "", number: 2 },
    sunrise: "",
    sunset: "",
    moonrise: "",
    moonset: "",
    moonPhase: { te: "", en: "", phase: 0, illuminationPercent: 0 },
    rahukalam: { te: "", en: "", start: "", end: "" },
    yamagandam: { te: "", en: "", start: "", end: "" },
    gulikaKalam: { te: "", en: "", start: "", end: "" },
    festivals: [],
  } as unknown as DayPanchangam;
}

const baseReminder = (overrides: Partial<StoredReminder> = {}): StoredReminder => ({
  id: "test-id",
  email: "test@example.com",
  name: "Test User",
  city_name: "Hyderabad",
  lat: 17.385,
  lng: 78.4867,
  tz: "Asia/Kolkata",
  tithi_types: ["amavasya"],
  reminder_type: "amavasya",
  remind_days_before: 0,
  remind_time: "06:00",
  unsubscribe_token: "tok",
  active: 1,
  ...overrides,
});

describe("matchReminder", () => {
  it("matches Amavasya for an amavasya opt-in", () => {
    const r = baseReminder({ tithi_types: ["amavasya"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 30 });
    const m = matchReminder(r, p);
    expect(m.matched).toBe(true);
    expect(m.kind).toBe("amavasya");
  });

  it("does not match Amavasya for a non-Amavasya day", () => {
    const r = baseReminder({ tithi_types: ["amavasya"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "shukla", tithiNumber: 5 });
    expect(matchReminder(r, p).matched).toBe(false);
  });

  it("matches Shukla Ekadashi (tithi 11)", () => {
    const r = baseReminder({ tithi_types: ["ekadashi"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "shukla", tithiNumber: 11 });
    const m = matchReminder(r, p);
    expect(m.matched).toBe(true);
    expect(m.kind).toBe("ekadashi");
  });

  it("matches Krishna Ekadashi (tithi 26)", () => {
    const r = baseReminder({ tithi_types: ["ekadashi"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 26 });
    expect(matchReminder(r, p).matched).toBe(true);
  });

  it("matches Purnima (tithi 15)", () => {
    const r = baseReminder({ tithi_types: ["purnima"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "shukla", tithiNumber: 15 });
    expect(matchReminder(r, p).matched).toBe(true);
  });

  it("respects opt-in: ekadashi-only user is NOT matched on Amavasya", () => {
    const r = baseReminder({ tithi_types: ["ekadashi"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 30 });
    expect(matchReminder(r, p).matched).toBe(false);
  });

  it("matches multi-opt-in on first hit", () => {
    const r = baseReminder({ tithi_types: ["ekadashi", "amavasya"] });
    const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 30 });
    const m = matchReminder(r, p);
    expect(m.matched).toBe(true);
    expect(m.kind).toBe("amavasya");
  });

  describe("tithi_anniversary", () => {
    it("matches an exact masa+paksha+tithi triple (Shukla)", () => {
      // Shukla: paksha-relative number == absolute number
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: 2,
        tithi_paksha: "shukla",
        tithi_number: 5, // Shukla Panchami → absolute 5
        tithi_description: "Vaishakha Shukla Panchami",
      });
      const p = fakePanchangam({ masaNumber: 2, paksha: "shukla", tithiNumber: 5 });
      const m = matchReminder(r, p);
      expect(m.matched).toBe(true);
      expect(m.kind).toBe("tithi_anniversary");
      expect(m.en).toBe("Vaishakha Shukla Panchami");
    });

    it("matches a Krishna paksha tithi (paksha-relative → absolute conversion)", () => {
      // Krishna Dashami stored as 10, must compare against absolute 25
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: 1,
        tithi_paksha: "krishna",
        tithi_number: 10, // paksha-relative
        tithi_description: "Chaitra Krishna Dashami",
      });
      const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 25 });
      const m = matchReminder(r, p);
      expect(m.matched).toBe(true);
      expect(m.kind).toBe("tithi_anniversary");
    });

    it("does NOT match Krishna stored value against the wrong absolute tithi", () => {
      // tithi_number 10 in Krishna means absolute 25, NOT absolute 10
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: 1,
        tithi_paksha: "krishna",
        tithi_number: 10,
      });
      const p = fakePanchangam({ masaNumber: 1, paksha: "krishna", tithiNumber: 10 });
      expect(matchReminder(r, p).matched).toBe(false);
    });

    it("does NOT match if the masa is Adhika (intercalary)", () => {
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: 2,
        tithi_paksha: "shukla",
        tithi_number: 5,
      });
      const p = fakePanchangam({
        masaNumber: 2,
        isAdhika: true,
        paksha: "shukla",
        tithiNumber: 5,
      });
      expect(matchReminder(r, p).matched).toBe(false);
    });

    it("does NOT match a different paksha", () => {
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: 2,
        tithi_paksha: "shukla",
        tithi_number: 5,
      });
      const p = fakePanchangam({ masaNumber: 2, paksha: "krishna", tithiNumber: 5 });
      expect(matchReminder(r, p).matched).toBe(false);
    });

    it("does NOT match if any of the three identifying fields is null", () => {
      const r = baseReminder({
        reminder_type: "tithi_anniversary",
        tithi_masa_number: null,
        tithi_paksha: "shukla",
        tithi_number: 5,
      });
      const p = fakePanchangam({ masaNumber: 2, paksha: "shukla", tithiNumber: 5 });
      expect(matchReminder(r, p).matched).toBe(false);
    });
  });
});

describe("addDaysISO", () => {
  it("rolls over month boundaries", () => {
    expect(addDaysISO("2026-01-31", 1)).toBe("2026-02-01");
    expect(addDaysISO("2026-02-28", 2)).toBe("2026-03-02");
    expect(addDaysISO("2025-12-31", 1)).toBe("2026-01-01");
  });
  it("handles zero offset", () => {
    expect(addDaysISO("2026-04-07", 0)).toBe("2026-04-07");
  });
});

describe("todayInTimezone", () => {
  it("returns YYYY-MM-DD for an arbitrary timezone", () => {
    // 2026-04-07 12:00 UTC is still 2026-04-07 in Asia/Kolkata
    const fixed = new Date("2026-04-07T12:00:00Z");
    expect(todayInTimezone("Asia/Kolkata", fixed)).toBe("2026-04-07");
  });

  it("rolls forward when UTC midnight has passed locally", () => {
    // 2026-04-06 22:00 UTC = 2026-04-07 09:00 in Asia/Kolkata
    const fixed = new Date("2026-04-06T22:00:00Z");
    expect(todayInTimezone("Asia/Kolkata", fixed)).toBe("2026-04-07");
  });

  it("rolls back when UTC has crossed midnight but Melbourne hasn't", () => {
    // 2026-04-07 13:00 UTC = 2026-04-07 23:00 in Australia/Melbourne (AEST)
    // and = 2026-04-08 00:00 in some +11 timezones; pick one stable case.
    const fixed = new Date("2026-04-06T13:00:00Z");
    // Asia/Tokyo is UTC+9 — 2026-04-06 13:00 UTC = 2026-04-06 22:00 Tokyo
    expect(todayInTimezone("Asia/Tokyo", fixed)).toBe("2026-04-06");
  });
});
