import { getKaranaInfo, isVishtiKarana } from "./karana";

describe("getKaranaInfo", () => {
  it("returns Bava with Telugu name", () => {
    const result = getKaranaInfo("Bava", null);
    expect(result.name.en).toBe("Bava");
    expect(result.name.te).toBe("బవ");
    expect(result.number).toBe(1);
  });

  it("returns Vishti with Telugu name", () => {
    const result = getKaranaInfo("Vishti", null);
    expect(result.name.en).toBe("Vishti");
    expect(result.name.te).toBe("విష్టి");
  });

  it("handles case-insensitive lookup", () => {
    const result = getKaranaInfo("BAVA", null);
    expect(result.name.en).toBe("Bava");
  });

  it("handles Gara as alias for Garija", () => {
    const result = getKaranaInfo("Gara", null);
    expect(result.name.en).toBe("Garija");
    expect(result.name.te).toBe("గరజ");
  });

  it("falls back gracefully for unknown karana name", () => {
    const result = getKaranaInfo("Unknown", null);
    expect(result.name.en).toBe("Unknown");
    expect(result.number).toBe(0);
  });
});

describe("isVishtiKarana", () => {
  it("identifies Vishti", () => {
    expect(isVishtiKarana("Vishti")).toBe(true);
    expect(isVishtiKarana("Bhadra")).toBe(true);
    expect(isVishtiKarana("vishti")).toBe(true);
  });

  it("rejects non-Vishti", () => {
    expect(isVishtiKarana("Bava")).toBe(false);
  });
});
