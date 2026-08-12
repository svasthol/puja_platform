import {
  calculateRahukalam,
  calculateGulikaKalam,
  calculateYamagandam,
} from "./rahukalam";

describe("calculateRahukalam", () => {
  // Use a fixed sunrise/sunset for predictable testing
  // Sunrise 06:00, Sunset 18:00 → 12h daylight → 90min slots
  const sunrise = new Date("2026-03-23T06:00:00Z");
  const sunset = new Date("2026-03-23T18:00:00Z");
  const tz = "UTC";

  it("returns 2nd slot for Monday (weekday 1)", () => {
    const result = calculateRahukalam(sunrise, sunset, 1, tz);
    // Slot 2: 06:00 + 90min = 07:30 to 09:00
    expect(result.start).toContain("T07:30:00");
    expect(result.end).toContain("T09:00:00");
    expect(result.te).toBe("రాహుకాలం");
    expect(result.en).toBe("Rahukalam");
  });

  it("returns 8th slot for Sunday (weekday 0)", () => {
    const result = calculateRahukalam(sunrise, sunset, 0, tz);
    // Slot 8: 06:00 + 7*90min = 16:30 to 18:00
    expect(result.start).toContain("T16:30:00");
    expect(result.end).toContain("T18:00:00");
  });

  it("returns 1st slot for Saturday (weekday 6)", () => {
    const result = calculateRahukalam(sunrise, sunset, 6, tz);
    // Slot 1: 06:00 to 07:30
    expect(result.start).toContain("T06:00:00");
    expect(result.end).toContain("T07:30:00");
  });
});

describe("calculateGulikaKalam", () => {
  const sunrise = new Date("2026-03-23T06:00:00Z");
  const sunset = new Date("2026-03-23T18:00:00Z");

  it("returns 1st slot for Monday", () => {
    const result = calculateGulikaKalam(sunrise, sunset, 1, "UTC");
    expect(result.start).toContain("T06:00:00");
    expect(result.end).toContain("T07:30:00");
    expect(result.te).toBe("గులికకాలం");
  });
});

describe("calculateYamagandam", () => {
  const sunrise = new Date("2026-03-23T06:00:00Z");
  const sunset = new Date("2026-03-23T18:00:00Z");

  it("returns 5th slot for Monday", () => {
    const result = calculateYamagandam(sunrise, sunset, 1, "UTC");
    // Slot 5: 06:00 + 4*90min = 12:00 to 13:30
    expect(result.start).toContain("T12:00:00");
    expect(result.end).toContain("T13:30:00");
    expect(result.te).toBe("యమగండం");
  });
});
