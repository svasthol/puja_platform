import { getPanchangam, Observer, tithiNames, nakshatraNames } from '@ishubhamx/panchangam-js';

const LAT = 17.385;
const LNG = 78.486;
const ALT = 542; // Hyderabad approx elevation m
const TZ = 330; // IST

const weekdaysTe = ['ఆదివారం', 'సోమవారం', 'మంగళవారం', 'బుధవారం', 'గురువారం', 'శుక్రవారం', 'శనివారం'];

function fmtTime(d) {
  if (!d) return '';
  const local = new Date(d.getTime() + TZ * 60 * 1000);
  const h = String(local.getUTCHours()).padStart(2, '0');
  const m = String(local.getUTCMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

const observer = new Observer(LAT, LNG, ALT);

for (let day = 1; day <= 30; day++) {
  const date = new Date(Date.UTC(2026, 6, day, 0, 0, 0));
  const p = getPanchangam(date, observer, { timezoneOffset: TZ });
  const wd = weekdaysTe[p.vara ?? p.weekday ?? 0] ?? '';
  const tithiNum = p.tithi;
  const nakNum = p.nakshatra;
  const tithiTe = tithiNames?.te?.[tithiNum] ?? String(tithiNum);
  const nakTe = nakshatraNames?.te?.[nakNum] ?? String(nakNum);
  console.log(
    [
      `2026-07-${String(day).padStart(2, '0')}`,
      wd,
      `tithi#${tithiNum}`,
      tithiTe,
      `nak#${nakNum}`,
      nakTe,
      fmtTime(p.sunrise),
      fmtTime(p.sunset),
    ].join(' | '),
  );
}
