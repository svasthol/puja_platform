interface ConfirmationParams {
  name: string;
  tithi_types: string[];
  remind_days_before: number;
  remind_time: string;
  city_name: string;
  personal_note?: string;
  unsubscribe_url: string;
}

interface ReminderParams {
  name: string;
  tithi: { te: string; en: string };
  date: string;
  gregorianDate: string;
  sunriseTime: string;
  city_name: string;
  personal_note?: string;
  isMahalaya: boolean;
  isSomavati: boolean;
  daysUntil: number;
  unsubscribe_url: string;
  app_url: string;
}

interface UnsubscribeParams {
  name: string;
}

const WRAPPER_START = `
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#FFF6EE;font-family:'Lora',Georgia,serif;color:#1A0800">
<div style="max-width:560px;margin:0 auto;padding:32px 24px">
<div style="background:linear-gradient(135deg,#D4603A,#E8875A,#D4A547);padding:20px;border-radius:12px 12px 0 0;text-align:center">
  <div style="font-size:24px;color:#fff;font-weight:600">పితృ స్మరణ</div>
  <div style="font-size:13px;color:rgba(255,255,255,0.8);font-style:italic;margin-top:4px">Ancestor Remembrance</div>
</div>
<div style="background:#fff;padding:28px 24px;border:1px solid #e8d5c4;border-top:none;border-radius:0 0 12px 12px">
`;

const WRAPPER_END = `
</div>
<div style="text-align:center;padding:20px;font-size:11px;color:#8B4020">
  <div>తెలుగు పంచాంగం — Telugu Panchangam</div>
  <div style="margin-top:4px">Free, open-source. For the community.</div>
</div>
</div>
</body>
</html>`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function confirmationEmail(
  params: ConfirmationParams
): { subject: string; html: string } {
  const noteSection = params.personal_note
    ? `<div style="margin:16px 0;padding:12px 16px;background:#FFF6EE;border-left:3px solid #D4A547;border-radius:4px;font-style:italic;color:#6B3010;font-size:14px">"${escapeHtml(params.personal_note)}"</div>`
    : "";

  const html = `${WRAPPER_START}
<p style="font-size:16px;margin:0 0 16px">నమస్కారం <strong>${escapeHtml(params.name)}</strong>,</p>
<p style="font-size:14px;color:#6B3010;margin:0 0 20px">Your ancestor remembrance reminder is set.</p>

<div style="background:#FFF6EE;border-radius:8px;padding:16px;margin:0 0 20px">
  <div style="font-size:12px;color:#8B4020;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Reminder Details</div>
  <div style="font-size:14px;margin:4px 0"><strong>Tithis:</strong> ${params.tithi_types.join(", ")}</div>
  <div style="font-size:14px;margin:4px 0"><strong>City:</strong> ${escapeHtml(params.city_name)}</div>
  <div style="font-size:14px;margin:4px 0"><strong>When:</strong> ${params.remind_days_before} day(s) before, at ${params.remind_time}</div>
</div>

${noteSection}

<div style="text-align:center;margin:24px 0;padding-top:16px;border-top:1px solid #e8d5c4">
  <div style="font-size:15px;color:#1A0800">పితృ దేవతలకు నమస్కారం</div>
  <div style="font-size:12px;color:#6B3010;font-style:italic;margin-top:4px">Remembering those who came before us.</div>
</div>

<div style="text-align:center;margin-top:20px">
  <a href="${params.unsubscribe_url}" style="font-size:11px;color:#8B4020">Unsubscribe</a>
</div>
${WRAPPER_END}`;

  return {
    subject: "పితృ స్మరణ సెట్ అయింది — Reminder registered ✓",
    html,
  };
}

export function reminderEmail(
  params: ReminderParams
): { subject: string; html: string } {
  let subject: string;
  if (params.daysUntil === 0) {
    subject = `నేడు ${params.tithi.te} — ${params.tithi.en} today, ${params.gregorianDate}`;
  } else if (params.daysUntil === 1) {
    subject = `${params.tithi.te} రేపు — ${params.tithi.en} tomorrow, ${params.gregorianDate}`;
  } else {
    subject = `${params.tithi.te} ${params.daysUntil} రోజుల్లో — ${params.tithi.en} in ${params.daysUntil} days`;
  }

  const noteSection = params.personal_note
    ? `<div style="margin:16px 0;padding:12px 16px;background:#FFF6EE;border-left:3px solid #D4A547;border-radius:4px;font-style:italic;color:#6B3010;font-size:14px">"${escapeHtml(params.personal_note)}"</div>`
    : "";

  const badges: string[] = [];
  if (params.isMahalaya) {
    badges.push(
      `<div style="display:inline-block;background:#A07000;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px;margin:4px">✨ Mahalaya Amavasya — most sacred Amavasya of the year</div>`
    );
  }
  if (params.isSomavati) {
    badges.push(
      `<div style="display:inline-block;background:#A07000;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px;margin:4px">✨ Somavati Amavasya — Amavasya on Monday, especially auspicious</div>`
    );
  }

  const html = `${WRAPPER_START}
<div style="text-align:center;margin-bottom:20px">
  <div style="font-size:28px;font-weight:700;color:#C04020">${params.tithi.te}</div>
  <div style="font-size:16px;font-style:italic;color:#6B3010;margin-top:4px">${params.tithi.en}</div>
  <div style="font-size:14px;color:#1A0800;margin-top:8px">${params.date}</div>
  <div style="font-size:13px;color:#6B3010">${params.gregorianDate}</div>
</div>

${badges.length > 0 ? `<div style="text-align:center;margin:12px 0">${badges.join("")}</div>` : ""}

<div style="background:#FFF6EE;border-radius:8px;padding:16px;text-align:center;margin:16px 0">
  <div style="font-size:20px;margin-bottom:4px">🌅</div>
  <div style="font-size:14px"><strong>Sunrise in ${escapeHtml(params.city_name)}:</strong> ${params.sunriseTime}</div>
  <div style="font-size:12px;color:#8B4020;margin-top:4px;font-style:italic">Tarpan is traditionally performed at sunrise</div>
</div>

<p style="font-size:14px;margin:16px 0">నమస్కారం <strong>${escapeHtml(params.name)}</strong>,</p>

${noteSection}

<div style="text-align:center;margin:24px 0">
  <a href="${params.app_url}" style="display:inline-block;background:#C04020;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px">View full Panchangam →</a>
</div>

<div style="text-align:center;margin:20px 0;padding-top:16px;border-top:1px solid #e8d5c4">
  <div style="font-size:15px;color:#1A0800">పితృ దేవతలకు నమస్కారం</div>
</div>

<div style="text-align:center;margin-top:20px">
  <a href="${params.unsubscribe_url}" style="font-size:11px;color:#8B4020">Unsubscribe</a>
</div>
${WRAPPER_END}`;

  return { subject, html };
}

export function unsubscribeConfirmationEmail(
  params: UnsubscribeParams
): { subject: string; html: string } {
  const html = `${WRAPPER_START}
<p style="font-size:16px;margin:0 0 16px">నమస్కారం <strong>${escapeHtml(params.name)}</strong>,</p>
<p style="font-size:14px;color:#6B3010;margin:0 0 20px">Your ancestor remembrance reminders have been cancelled.</p>
<p style="font-size:14px;color:#6B3010">You can set up reminders again any time by visiting the app.</p>

<div style="text-align:center;margin:24px 0">
  <a href="/" style="display:inline-block;background:#C04020;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px">Visit Telugu Panchangam</a>
</div>
${WRAPPER_END}`;

  return {
    subject: "Reminder cancelled — Telugu Panchangam",
    html,
  };
}

interface AnniversaryReminderParams {
  name: string;
  tithi: { te: string; en: string };
  tithiDescription: string;
  date: string;
  gregorianDate: string;
  sunriseTime: string;
  city_name: string;
  personal_note?: string;
  daysUntil: number;
  yearNumber?: number;
  unsubscribe_url: string;
  app_url: string;
}

export function anniversaryReminderEmail(
  params: AnniversaryReminderParams
): { subject: string; html: string } {
  let subject: string;
  if (params.daysUntil === 0) {
    subject = `నేడు తిథి వార్షికం — ${params.tithiDescription} today`;
  } else if (params.daysUntil === 1) {
    subject = `తిథి వార్షికం రేపు — ${params.tithiDescription} tomorrow`;
  } else {
    subject = `తిథి వార్షికం ${params.daysUntil} రోజుల్లో — ${params.tithiDescription} in ${params.daysUntil} days`;
  }

  const noteSection = params.personal_note
    ? `<div style="margin:16px 0;padding:12px 16px;background:#FFF6EE;border-left:3px solid #D4A547;border-radius:4px;font-style:italic;color:#6B3010;font-size:14px">"${escapeHtml(params.personal_note)}"</div>`
    : "";

  const yearSection = params.yearNumber
    ? `<div style="text-align:center;font-size:13px;color:#6B3010;margin:12px 0">This is the ${params.yearNumber}th year of remembrance.</div>`
    : "";

  const html = `${WRAPPER_START}
<p style="font-size:14px;margin:0 0 16px">నమస్కారం <strong>${escapeHtml(params.name)}</strong>,</p>

<div style="text-align:center;margin:20px 0">
  <div style="font-size:28px;font-weight:700;color:#C04020">${params.tithi.te}</div>
  <div style="font-size:15px;font-style:italic;color:#6B3010;margin-top:4px">${escapeHtml(params.tithiDescription)}</div>
  <div style="font-size:18px;color:#1A0800;margin-top:12px;font-weight:600">${escapeHtml(params.gregorianDate)}</div>
</div>

${yearSection}

<div style="background:#FFF6EE;border-radius:8px;padding:16px;text-align:center;margin:16px 0">
  <div style="font-size:20px;margin-bottom:4px">🌅</div>
  <div style="font-size:14px"><strong>Sunrise in ${escapeHtml(params.city_name)}:</strong> ${params.sunriseTime}</div>
  <div style="font-size:12px;color:#8B4020;margin-top:4px;font-style:italic">Tarpan is traditionally performed at sunrise</div>
</div>

${noteSection}

<div style="text-align:center;margin:24px 0;padding:16px 0;border-top:1px solid #e8d5c4;border-bottom:1px solid #e8d5c4">
  <div style="font-size:16px;color:#1A0800">పితృ దేవతలకు నమస్కారం</div>
  <div style="font-size:13px;color:#6B3010;font-style:italic;margin-top:6px">Those who came before us are never truly gone.</div>
</div>

<div style="text-align:center;margin:20px 0">
  <a href="${params.app_url}" style="display:inline-block;background:#C04020;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-size:14px">View Panchangam for this day →</a>
</div>

<div style="text-align:center;margin-top:20px">
  <a href="${params.unsubscribe_url}" style="font-size:11px;color:#8B4020">Unsubscribe</a>
</div>
${WRAPPER_END}`;

  return { subject, html };
}
