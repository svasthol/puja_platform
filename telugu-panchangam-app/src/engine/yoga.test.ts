import { getYogaInfo } from "./yoga";

describe("getYogaInfo", () => {
  it("returns Vishkambha for index 0 (inauspicious)", () => {
    const result = getYogaInfo(0, null);
    expect(result.name.en).toBe("Vishkambha");
    expect(result.name.te).toBe("విష్కంభ");
    expect(result.number).toBe(1);
    expect(result.isAuspicious).toBe(false);
  });

  it("returns Priti for index 1 (auspicious)", () => {
    const result = getYogaInfo(1, null);
    expect(result.name.en).toBe("Priti");
    expect(result.isAuspicious).toBe(true);
  });

  it("returns Vaidhriti for index 26 (highly inauspicious)", () => {
    const result = getYogaInfo(26, null);
    expect(result.name.en).toBe("Vaidhriti");
    expect(result.name.te).toBe("వైధృతి");
    expect(result.isAuspicious).toBe(false);
  });

  it("returns Vyatipata as inauspicious", () => {
    const result = getYogaInfo(16, null);
    expect(result.name.en).toBe("Vyatipata");
    expect(result.isAuspicious).toBe(false);
  });

  it("throws for invalid index", () => {
    expect(() => getYogaInfo(27, null)).toThrow("Invalid yoga index");
  });
});
