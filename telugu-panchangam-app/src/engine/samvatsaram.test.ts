import { getSamvatsaram, getSamvatsaramForDate } from "./samvatsaram";

describe("getSamvatsaram", () => {
  it("finds Parabhava by name", () => {
    const result = getSamvatsaram("Parabhava");
    expect(result.name.en).toBe("Parabhava");
    expect(result.name.te).toBe("పరాభవ");
    expect(result.number).toBe(40);
  });

  it("finds Vishvavasu by name (case-insensitive)", () => {
    const result = getSamvatsaram("Vishvavasu");
    expect(result.name.en).toBe("Vishvavasu");
    expect(result.name.te).toBe("విశ్వావసు");
    expect(result.number).toBe(39);
  });

  it("falls back for unknown name", () => {
    const result = getSamvatsaram("Unknown");
    expect(result.number).toBe(0);
  });
});

describe("getSamvatsaramForDate", () => {
  it("returns Parabhava for 2026 after March (Ugadi 2026)", () => {
    const result = getSamvatsaramForDate(2026, 4); // April 2026
    expect(result.name.en).toBe("Parabhava");
    expect(result.number).toBe(40);
  });

  it("returns Vishvavasu for Jan 2026 (before Ugadi)", () => {
    const result = getSamvatsaramForDate(2026, 1);
    expect(result.name.en).toBe("Vishvavasu");
    expect(result.number).toBe(39);
  });

  it("returns Plavanga for 2027 after March", () => {
    const result = getSamvatsaramForDate(2027, 4);
    expect(result.name.en).toBe("Plavanga");
    expect(result.number).toBe(41);
  });
});
