import { getPanchangam, Observer } from '@ishubhamx/panchangam-js';

const LAT = 17.385, LNG = 78.486, ALT = 542, TZ = 330;
const observer = new Observer(LAT, LNG, ALT);
const days = [14, 15, 16, 17, 18, 19, 20, 30];

for (const day of days) {
  const date = new Date(Date.UTC(2026, 6, day, 0, 0, 0));
  const p = getPanchangam(date, observer, { timezoneOffset: TZ });
  console.log(day, JSON.stringify({ tithi: p.tithi, nakshatra: p.nakshatra, vara: p.vara }));
}
