import { getMasaInfo, getRituInfo, getAyanaInfo } from "./masa";

describe("getMasaInfo", () => {
  it("returns Chaitra for index 0", () => {
    const result = getMasaInfo(0, false);
    expect(result.name.en).toBe("Chaitra");
    expect(result.name.te).toBe("చైత్రం");
    expect(result.number).toBe(1);
    expect(result.isAdhika).toBe(false);
  });

  it("returns Phalguna for index 11", () => {
    const result = getMasaInfo(11, false);
    expect(result.name.en).toBe("Phalguna");
    expect(result.name.te).toBe("ఫాల్గుణం");
    expect(result.number).toBe(12);
  });

  it("prefixes Adhika when isAdhika is true", () => {
    const result = getMasaInfo(3, true);
    expect(result.name.en).toBe("Adhika Ashadha");
    expect(result.name.te).toBe("అధిక ఆషాఢం");
    expect(result.isAdhika).toBe(true);
  });

  it("throws for invalid index", () => {
    expect(() => getMasaInfo(12, false)).toThrow("Invalid masa index");
  });
});

describe("getRituInfo", () => {
  it("returns Vasanta with Telugu", () => {
    const result = getRituInfo("Vasanta");
    expect(result.te).toBe("వసంత ఋతువు");
    expect(result.en).toBe("Vasanta (Spring)");
  });

  it("falls back for unknown ritu", () => {
    const result = getRituInfo("Unknown");
    expect(result.en).toBe("Unknown");
  });
});

describe("getAyanaInfo", () => {
  it("returns Uttarayana with Telugu", () => {
    const result = getAyanaInfo("Uttarayana");
    expect(result.te).toBe("ఉత్తరాయణం");
  });

  it("returns Dakshinayana with Telugu", () => {
    const result = getAyanaInfo("Dakshinayana");
    expect(result.te).toBe("దక్షిణాయనం");
  });
});
