export const runtime = "edge";

export async function GET() {
  return new Response(
    `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Unsubscribed</title></head>
<body style="margin:0;padding:0;background:#FFF6EE;font-family:'Lora',Georgia,serif;text-align:center;padding:60px 24px;color:#1A0800">
  <h1 style="color:#C04020;font-size:24px;margin-bottom:12px">పితృ స్మరణ రద్దు అయింది</h1>
  <p style="font-size:16px;color:#6B3010">Your reminders have been cancelled.</p>
  <p style="font-size:14px;color:#6B3010;margin-top:8px">నమస్కారం — we hope the app continues to serve you.</p>
  <a href="/" style="display:inline-block;margin-top:24px;color:#C04020;font-size:14px">Return to Panchangam</a>
</body>
</html>`,
    {
      headers: { "Content-Type": "text/html" },
    }
  );
}
