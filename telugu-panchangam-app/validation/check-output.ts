import { calculateDayPanchangam } from "../src/engine/panchangam";

const hyderabad = { lat: 17.385, lng: 78.486, tz: "Asia/Kolkata" };

const dates = [
  "2026-03-19", // Ugadi
  "2026-03-15", // Amavasya
  "2026-02-15", // Maha Sivaratri
  "2026-03-27", // Sri Rama Navami
  "2026-03-23", // A Monday (Rahukalam check)
];

for (const d of dates) {
  const r = calculateDayPanchangam(d, hyderabad);
  console.log(`\n=== ${d} ===`);
  console.log(`Vara: ${r.vara.en} (${r.vara.te})`);
  console.log(`Samvatsaram: ${r.samvatsaram.en} (#${r.samvatsaram.number})`);
  console.log(`Masa: ${r.masa.en} (#${r.masa.number}), Adhika: ${r.masa.isAdhika}`);
  console.log(`Paksha: ${r.paksha.value}`);
  console.log(`Tithi: ${r.tithi.en} (#${r.tithi.number}) - ${r.tithi.te}`);
  console.log(`Nakshatra: ${r.nakshatra.en} (#${r.nakshatra.number}) pada ${r.nakshatra.pada} - ${r.nakshatra.te}`);
  console.log(`Yoga: ${r.yoga.en} (#${r.yoga.number}) auspicious: ${r.yoga.isAuspicious}`);
  console.log(`Karana: ${r.karana.en}`);
  console.log(`Sunrise: ${r.sunrise}`);
  console.log(`Sunset: ${r.sunset}`);
  console.log(`Ritu: ${r.ritu.en}`);
  console.log(`Ayana: ${r.ayana.en}`);
}
