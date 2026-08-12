import { getNakshatraInfo, getJanmaNakshatra } from "./nakshatra";

describe("getNakshatraInfo", () => {
  it("returns Ashwini for index 0", () => {
    const result = getNakshatraInfo(0, 0, null);
    expect(result.name.en).toBe("Ashwini");
    expect(result.name.te).toBe("అశ్వని");
    expect(result.number).toBe(1);
    expect(result.pada).toBe(1);
  });

  it("returns Revati for index 26", () => {
    const result = getNakshatraInfo(26, 3, null);
    expect(result.name.en).toBe("Revati");
    expect(result.name.te).toBe("రేవతి");
    expect(result.number).toBe(27);
    expect(result.pada).toBe(4);
  });

  it("converts 0-indexed pada to 1-indexed", () => {
    expect(getNakshatraInfo(5, 0, null).pada).toBe(1);
    expect(getNakshatraInfo(5, 1, null).pada).toBe(2);
    expect(getNakshatraInfo(5, 2, null).pada).toBe(3);
    expect(getNakshatraInfo(5, 3, null).pada).toBe(4);
  });

  it("throws for invalid index", () => {
    expect(() => getNakshatraInfo(27, 0, null)).toThrow(
      "Invalid nakshatra index"
    );
  });
});

describe("getJanmaNakshatra", () => {
  const hyderabad = {
    lat: 17.385,
    lng: 78.4867,
    tz: "Asia/Kolkata",
  };

  it("returns a valid nakshatra result", () => {
    const result = getJanmaNakshatra(
      "1985-04-14",
      "06:30",
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz
    );
    expect(result.nakshatraNumber).toBeGreaterThan(0);
    expect(result.nakshatraNumber).toBeLessThanOrEqual(27);
    expect(result.pada).toBeGreaterThanOrEqual(1);
    expect(result.pada).toBeLessThanOrEqual(4);
    expect(result.nakshatra).toHaveProperty("te");
    expect(result.nakshatra).toHaveProperty("en");
    expect(result.raasi).toHaveProperty("te");
    expect(result.raasi).toHaveProperty("en");
    expect(result.deity).toBeDefined();
  });

  it("calculates Tarabalam when today params given", () => {
    const result = getJanmaNakshatra(
      "1985-04-14",
      "06:30",
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz,
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz,
      "2026-03-25"
    );
    expect(result.tarabalam).toBeDefined();
    expect(result.tarabalam?.taraNumber).toBeGreaterThanOrEqual(1);
    expect(result.tarabalam?.taraNumber).toBeLessThanOrEqual(9);
    expect([
      "highly_auspicious",
      "auspicious",
      "neutral",
      "inauspicious",
      "highly_inauspicious",
    ]).toContain(result.tarabalam?.quality);
    expect(result.tarabalam?.todaysNakshatra).toHaveProperty("te");
    expect(result.tarabalam?.taraName).toBeDefined();
  });

  it("same birth details always give same result", () => {
    const result1 = getJanmaNakshatra(
      "1990-01-01",
      "12:00",
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz
    );
    const result2 = getJanmaNakshatra(
      "1990-01-01",
      "12:00",
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz
    );
    expect(result1.nakshatraNumber).toBe(result2.nakshatraNumber);
    expect(result1.pada).toBe(result2.pada);
    expect(result1.raasi.en).toBe(result2.raasi.en);
  });

  it("does not include Tarabalam when today params not given", () => {
    const result = getJanmaNakshatra(
      "1990-01-01",
      "12:00",
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz
    );
    expect(result.tarabalam).toBeUndefined();
  });

  it("works for Melbourne timezone", () => {
    const result = getJanmaNakshatra(
      "2000-06-15",
      "08:00",
      -37.8136,
      144.9631,
      "Australia/Melbourne"
    );
    expect(result.nakshatraNumber).toBeGreaterThan(0);
    expect(result.nakshatraNumber).toBeLessThanOrEqual(27);
  });
});
