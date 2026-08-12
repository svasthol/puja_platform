import { calculateDayPanchangam } from "../src/engine/panchangam";
import type { Location } from "../src/engine/types";

/**
 * Regression tests for the Telugu Panchangam calculation engine.
 *
 * Ground truth: Venkatrama & Co. 2026 printed calendar (Eluru, Andhra Pradesh).
 *
 * Key convention: The Panchangam day runs from sunrise to sunrise.
 * The "sunrise tithi" is the tithi prevailing at the moment of local sunrise.
 * Festivals may be assigned to a day where the relevant tithi begins
 * after sunrise but before the next sunrise.
 */

const hyderabad: Location = {
  lat: 17.385,
  lng: 78.486,
  tz: "Asia/Kolkata",
};

const melbourne: Location = {
  lat: -37.814,
  lng: 144.9633,
  tz: "Australia/Melbourne",
};

describe("Venkatrama 2026 Regression — Ugadi", () => {
  const result = calculateDayPanchangam("2026-03-19", hyderabad);

  it("March 19, 2026 is Thursday", () => {
    expect(result.vara.en).toBe("Thursday");
    expect(result.vara.te).toBe("గురువారం");
  });

  it("sunrise tithi is Amavasya (Phalguna Krishna)", () => {
    // Pratipada starts ~30 min after sunrise on this day
    expect(result.tithi.en).toBe("Amavasya");
    expect(result.tithi.number).toBe(30);
    expect(result.paksha.value).toBe("krishna");
  });

  it("masa at sunrise is Phalguna (before Chaitra begins)", () => {
    expect(result.masa.en).toBe("Phalguna");
    expect(result.masa.number).toBe(12);
  });

  it("samvatsaram at sunrise is still Vishvavasu (Parabhava starts with Pratipada)", () => {
    expect(result.samvatsaram.en).toBe("Vishvavasu");
    expect(result.samvatsaram.number).toBe(39);
  });
});

describe("Venkatrama 2026 Regression — Day after Ugadi", () => {
  const result = calculateDayPanchangam("2026-03-20", hyderabad);

  it("March 20 is Chaitra Shukla Dwitiya", () => {
    expect(result.tithi.en).toBe("Dwitiya");
    expect(result.tithi.number).toBe(2);
    expect(result.paksha.value).toBe("shukla");
  });

  it("masa transitions to Chaitra", () => {
    expect(result.masa.en).toBe("Chaitra");
    expect(result.masa.number).toBe(1);
  });

  it("samvatsaram is now Parabhava", () => {
    expect(result.samvatsaram.en).toBe("Parabhava");
    expect(result.samvatsaram.number).toBe(40);
  });
});

describe("Venkatrama 2026 Regression — Maha Sivaratri", () => {
  const result = calculateDayPanchangam("2026-02-15", hyderabad);

  it("Feb 15 is Sunday", () => {
    expect(result.vara.en).toBe("Sunday");
  });

  it("sunrise tithi is Trayodashi (Magha Krishna)", () => {
    // Chaturdashi begins after sunrise — Sivaratri observed this night
    expect(result.tithi.en).toBe("Trayodashi");
    expect(result.tithi.number).toBe(28);
    expect(result.paksha.value).toBe("krishna");
  });

  it("masa is Magha", () => {
    expect(result.masa.en).toBe("Magha");
    expect(result.masa.number).toBe(11);
  });

  it("samvatsaram is Vishvavasu (before Ugadi 2026)", () => {
    expect(result.samvatsaram.en).toBe("Vishvavasu");
  });
});

describe("Venkatrama 2026 Regression — Sri Rama Navami", () => {
  const result = calculateDayPanchangam("2026-03-27", hyderabad);

  it("March 27 is Friday", () => {
    expect(result.vara.en).toBe("Friday");
  });

  it("tithi is Chaitra Shukla Navami", () => {
    expect(result.tithi.en).toBe("Navami");
    expect(result.tithi.number).toBe(9);
    expect(result.paksha.value).toBe("shukla");
  });

  it("masa is Chaitra with Parabhava samvatsaram", () => {
    expect(result.masa.en).toBe("Chaitra");
    expect(result.samvatsaram.en).toBe("Parabhava");
  });
});

describe("Venkatrama 2026 Regression — Melbourne Rahukalam (Monday)", () => {
  const result = calculateDayPanchangam("2026-03-23", melbourne);

  it("March 23 is Monday", () => {
    expect(result.vara.en).toBe("Monday");
    expect(result.vara.number).toBe(1);
  });

  it("sunrise is approximately 07:26 AEDT", () => {
    // Extract hour from ISO string
    const hour = parseInt(result.sunrise.split("T")[1].split(":")[0], 10);
    expect(hour).toBe(7);
  });

  it("Rahukalam starts in 2nd slot after sunrise", () => {
    // Monday = 2nd slot. Sunrise ~07:26, slot ~90 min
    // Rahukalam should start ~08:57
    const startHour = parseInt(
      result.rahukalam.start.split("T")[1].split(":")[0],
      10
    );
    expect(startHour).toBeGreaterThanOrEqual(8);
    expect(startHour).toBeLessThanOrEqual(9);
    expect(result.rahukalam.te).toBe("రాహుకాలం");
  });

  it("has correct Chaitra masa and Shukla paksha", () => {
    expect(result.masa.en).toBe("Chaitra");
    expect(result.paksha.value).toBe("shukla");
    expect(result.tithi.en).toBe("Panchami");
  });
});

describe("Engine output structure", () => {
  const result = calculateDayPanchangam("2026-03-23", hyderabad);

  it("all timestamps contain correct IST offset", () => {
    expect(result.sunrise).toContain("+05:30");
    expect(result.sunset).toContain("+05:30");
  });

  it("nakshatra has pada 1-4", () => {
    expect(result.nakshatra.pada).toBeGreaterThanOrEqual(1);
    expect(result.nakshatra.pada).toBeLessThanOrEqual(4);
  });

  it("yoga has auspicious boolean", () => {
    expect(typeof result.yoga.isAuspicious).toBe("boolean");
  });

  it("tithi number is 1-30", () => {
    expect(result.tithi.number).toBeGreaterThanOrEqual(1);
    expect(result.tithi.number).toBeLessThanOrEqual(30);
  });

  it("ritu and ayana are populated", () => {
    expect(result.ritu.te).toBeTruthy();
    expect(result.ritu.en).toBeTruthy();
    expect(result.ayana.te).toBeTruthy();
    expect(result.ayana.en).toBeTruthy();
  });

  it("moon phase has illumination", () => {
    expect(result.moonPhase.illuminationPercent).toBeGreaterThanOrEqual(0);
    expect(result.moonPhase.illuminationPercent).toBeLessThanOrEqual(100);
    expect(result.moonPhase.phase).toBeGreaterThanOrEqual(0);
    expect(result.moonPhase.phase).toBeLessThanOrEqual(1);
  });
});

describe("Melbourne AEDT timezone", () => {
  const result = calculateDayPanchangam("2026-03-23", melbourne);

  it("timestamps contain +11:00 offset", () => {
    expect(result.sunrise).toContain("+11:00");
    expect(result.sunset).toContain("+11:00");
    expect(result.rahukalam.start).toContain("+11:00");
  });
});

describe("Cross-date consistency", () => {
  it("consecutive days have incrementing tithis (with possible skips)", () => {
    const day1 = calculateDayPanchangam("2026-03-23", hyderabad);
    const day2 = calculateDayPanchangam("2026-03-24", hyderabad);

    // Tithi should increment by 1 or 2 (kshaya possible)
    const diff = ((day2.tithi.number - day1.tithi.number + 30) % 30);
    expect(diff).toBeGreaterThanOrEqual(1);
    expect(diff).toBeLessThanOrEqual(2);
  });
});
