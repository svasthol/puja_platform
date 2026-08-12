import { getTithiInfo, isEkadashi, isAmavasya, isPurnima } from "./tithi";

describe("getTithiInfo", () => {
  it("returns Shukla Pratipada for index 0", () => {
    const result = getTithiInfo(0, null);
    expect(result.number).toBe(1);
    expect(result.name.en).toBe("Pratipada");
    expect(result.name.te).toBe("పాడ్యమి");
    expect(result.paksha).toBe("shukla");
  });

  it("returns Purnima for index 14", () => {
    const result = getTithiInfo(14, null);
    expect(result.number).toBe(15);
    expect(result.name.en).toBe("Purnima");
    expect(result.name.te).toBe("పౌర్ణమి");
    expect(result.paksha).toBe("shukla");
  });

  it("returns Amavasya for index 29", () => {
    const result = getTithiInfo(29, null);
    expect(result.number).toBe(30);
    expect(result.name.en).toBe("Amavasya");
    expect(result.name.te).toBe("అమావాస్య");
    expect(result.paksha).toBe("krishna");
  });

  it("returns Krishna Pratipada for index 15", () => {
    const result = getTithiInfo(15, null);
    expect(result.number).toBe(16);
    expect(result.name.en).toBe("Pratipada");
    expect(result.paksha).toBe("krishna");
  });

  it("calculates next tithi correctly", () => {
    const result = getTithiInfo(14, null); // Purnima
    expect(result.nextTithi.en).toBe("Pratipada"); // Krishna Pratipada
    expect(result.nextTithi.number).toBe(16);
  });

  it("wraps next tithi from Amavasya to Pratipada", () => {
    const result = getTithiInfo(29, null); // Amavasya
    expect(result.nextTithi.en).toBe("Pratipada");
    expect(result.nextTithi.number).toBe(1);
  });

  it("throws for invalid index", () => {
    expect(() => getTithiInfo(30, null)).toThrow("Invalid tithi index");
    expect(() => getTithiInfo(-1, null)).toThrow("Invalid tithi index");
  });
});

describe("tithi type checks", () => {
  it("identifies Ekadashi correctly", () => {
    expect(isEkadashi(11)).toBe(true);  // Shukla Ekadashi
    expect(isEkadashi(26)).toBe(true);  // Krishna Ekadashi
    expect(isEkadashi(10)).toBe(false);
  });

  it("identifies Amavasya correctly", () => {
    expect(isAmavasya(30)).toBe(true);
    expect(isAmavasya(15)).toBe(false);
  });

  it("identifies Purnima correctly", () => {
    expect(isPurnima(15)).toBe(true);
    expect(isPurnima(30)).toBe(false);
  });
});
