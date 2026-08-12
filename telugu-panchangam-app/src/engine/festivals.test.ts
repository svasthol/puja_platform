import { getFestivalsForYear } from "./festivals";

const hyderabad = {
  lat: 17.385,
  lng: 78.4867,
  tz: "Asia/Kolkata",
};

const melbourne = {
  lat: -37.8136,
  lng: 144.9631,
  tz: "Australia/Melbourne",
};

describe("getFestivalsForYear", () => {
  // Cache results — this function is slow (scans 365 days)
  let festivals2026: ReturnType<typeof getFestivalsForYear>;
  let festivals2026Melb: ReturnType<typeof getFestivalsForYear>;

  beforeAll(() => {
    festivals2026 = getFestivalsForYear(
      2026,
      hyderabad.lat,
      hyderabad.lng,
      hyderabad.tz
    );
    festivals2026Melb = getFestivalsForYear(
      2026,
      melbourne.lat,
      melbourne.lng,
      melbourne.tz
    );
  }, 120000);

  it("finds Ugadi 2026 on March 19", () => {
    const ugadi = festivals2026.find((f) => f.en === "Ugadi");
    expect(ugadi).toBeDefined();
    expect(ugadi?.date).toBe("2026-03-19");
    expect(ugadi?.tier).toBe(1);
  });

  it("finds Maha Sivaratri 2026 on Feb 15", () => {
    const sivaratri = festivals2026.find((f) =>
      f.en.includes("Sivaratri")
    );
    expect(sivaratri).toBeDefined();
    expect(sivaratri?.date).toBe("2026-02-15");
  });

  it("finds 12+ Amavasyas in a year", () => {
    const amavasyas = festivals2026.filter((f) =>
      f.en.endsWith("Amavasya")
    );
    expect(amavasyas.length).toBeGreaterThanOrEqual(12);
    expect(amavasyas.length).toBeLessThanOrEqual(13);
  });

  it("finds 23-26 Ekadashis in a year", () => {
    const ekadashis = festivals2026.filter((f) =>
      f.en.includes("Ekadashi")
    );
    expect(ekadashis.length).toBeGreaterThanOrEqual(23);
    expect(ekadashis.length).toBeLessThanOrEqual(26);
  });

  it("returns festivals sorted by date", () => {
    for (let i = 1; i < festivals2026.length; i++) {
      expect(
        (festivals2026[i].date ?? "") >= (festivals2026[i - 1].date ?? "")
      ).toBe(true);
    }
  });

  it("Sankranti 2026 is on January 14 or 15", () => {
    const sankranti = festivals2026.find((f) =>
      f.en.includes("Sankranti")
    );
    expect(sankranti).toBeDefined();
    expect(["2026-01-14", "2026-01-15"]).toContain(sankranti?.date);
  });

  it("finds Deepavali", () => {
    const deepavali = festivals2026.find((f) => f.en === "Deepavali");
    expect(deepavali).toBeDefined();
    expect(deepavali?.tier).toBe(1);
  });

  it("finds fixed holidays (Republic Day, Independence Day)", () => {
    const republic = festivals2026.find((f) => f.en === "Republic Day");
    expect(republic).toBeDefined();
    expect(republic?.date).toBe("2026-01-26");

    const independence = festivals2026.find(
      (f) => f.en === "Independence Day"
    );
    expect(independence).toBeDefined();
    expect(independence?.date).toBe("2026-08-15");
  });

  it("finds festivals for Melbourne too", () => {
    const ugadi = festivals2026Melb.find((f) => f.en === "Ugadi");
    expect(ugadi).toBeDefined();
    // Ugadi may differ by a day due to timezone
    expect(ugadi?.date).toMatch(/^2026-03-(18|19|20)$/);
  });

  it("finds Sri Rama Navami", () => {
    const ramNavami = festivals2026.find((f) =>
      f.en.includes("Rama Navami")
    );
    expect(ramNavami).toBeDefined();
    expect(ramNavami?.date).toBe("2026-03-27");
  });
});

describe("Significant Ekadashi detection", () => {
  let festivals2026: ReturnType<typeof getFestivalsForYear>;

  beforeAll(() => {
    festivals2026 = getFestivalsForYear(2026, hyderabad.lat, hyderabad.lng, hyderabad.tz);
  }, 120000);

  it("marks Vaikunta Ekadashi as significant", () => {
    const vaikunta = festivals2026.find((f) => f.en.includes("Vaikunta"));
    expect(vaikunta).toBeDefined();
    expect(vaikunta?.isSignificantEkadashi).toBe(true);
    expect(vaikunta?.tier).toBe(1);
    expect(vaikunta?.significance?.en).toContain("most sacred");
    expect(vaikunta?.significance?.te).toBeTruthy();
  });

  it("marks Nirjala Ekadashi as significant", () => {
    const nirjala = festivals2026.find((f) => f.en.includes("Nirjala"));
    expect(nirjala).toBeDefined();
    expect(nirjala?.isSignificantEkadashi).toBe(true);
    expect(nirjala?.tier).toBe(1);
    expect(nirjala?.significance?.en.toLowerCase()).toContain("water");
  });

  it("marks Devshayani Ekadashi as significant", () => {
    const devshayani = festivals2026.find((f) => f.en.includes("Devshayani"));
    expect(devshayani).toBeDefined();
    expect(devshayani?.isSignificantEkadashi).toBe(true);
    expect(devshayani?.tier).toBe(1);
  });

  it("marks Prabodhini Ekadashi as significant", () => {
    const prabodhini = festivals2026.find((f) => f.en.includes("Prabodhini"));
    expect(prabodhini).toBeDefined();
    expect(prabodhini?.isSignificantEkadashi).toBe(true);
    expect(prabodhini?.tier).toBe(1);
  });

  it("regular Ekadashis are not marked significant and are tier 2", () => {
    const regular = festivals2026.filter(
      (f) => f.en.includes("Ekadashi") && !f.isSignificantEkadashi
    );
    expect(regular.length).toBeGreaterThan(15);
    regular.forEach((e) => {
      expect(e.tier).toBe(2);
    });
  });

  it("significant Ekadashis have bilingual names and significance", () => {
    const significant = festivals2026.filter((f) => f.isSignificantEkadashi);
    expect(significant.length).toBeGreaterThanOrEqual(1);
    significant.forEach((f) => {
      expect(f.te).toBeTruthy();
      expect(f.en).toBeTruthy();
      expect(f.significance?.te).toBeTruthy();
      expect(f.significance?.en).toBeTruthy();
    });
  });
});
