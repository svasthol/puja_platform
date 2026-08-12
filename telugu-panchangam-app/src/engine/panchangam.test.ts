import { calculateDayPanchangam } from "./panchangam";
import type { Location } from "./types";

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

describe("calculateDayPanchangam", () => {
  it("returns a complete DayPanchangam for Hyderabad", () => {
    const result = calculateDayPanchangam("2026-03-19", hyderabad);

    expect(result.date).toBe("2026-03-19");
    expect(result.vara.en).toBe("Thursday");
    expect(result.samvatsaram).toBeDefined();
    expect(result.masa).toBeDefined();
    expect(result.tithi).toBeDefined();
    expect(result.nakshatra).toBeDefined();
    expect(result.yoga).toBeDefined();
    expect(result.karana).toBeDefined();
    expect(result.sunrise).toBeTruthy();
    expect(result.sunset).toBeTruthy();
    expect(result.rahukalam).toBeDefined();
    expect(result.gulikaKalam).toBeDefined();
    expect(result.yamagandam).toBeDefined();
    expect(result.moonPhase).toBeDefined();
  });

  it("returns a complete DayPanchangam for Melbourne", () => {
    const result = calculateDayPanchangam("2026-03-23", melbourne);

    expect(result.date).toBe("2026-03-23");
    expect(result.vara.en).toBe("Monday");
    expect(result.sunrise).toBeTruthy();
  });

  it("has bilingual names for all panchanga elements", () => {
    const result = calculateDayPanchangam("2026-03-19", hyderabad);

    // All elements should have both te and en
    expect(result.tithi.te).toBeTruthy();
    expect(result.tithi.en).toBeTruthy();
    expect(result.nakshatra.te).toBeTruthy();
    expect(result.nakshatra.en).toBeTruthy();
    expect(result.yoga.te).toBeTruthy();
    expect(result.yoga.en).toBeTruthy();
    expect(result.karana.te).toBeTruthy();
    expect(result.karana.en).toBeTruthy();
    expect(result.vara.te).toBeTruthy();
    expect(result.vara.en).toBeTruthy();
    expect(result.samvatsaram.te).toBeTruthy();
    expect(result.samvatsaram.en).toBeTruthy();
    expect(result.masa.te).toBeTruthy();
    expect(result.masa.en).toBeTruthy();
  });

  it("returns valid paksha values", () => {
    const result = calculateDayPanchangam("2026-03-19", hyderabad);

    expect(["shukla", "krishna"]).toContain(result.paksha.value);
    expect(result.paksha.te).toBeTruthy();
    expect(result.paksha.en).toBeTruthy();
  });
});
