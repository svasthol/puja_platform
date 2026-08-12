import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Telugu Panchangam";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

interface Props {
  params: { year: string; month: string; day: string };
}

export default async function OGImage({ params }: Props) {
  const { year, month, day } = params;
  const date = new Date(`${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`);
  const dateStr = date.toLocaleDateString("en-AU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  let tithiEn = "Panchangam";
  let nakshatraEn = "";
  try {
    const res = await fetch(
      `https://telugupanchangam.app/api/panchangam?date=${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}&lat=-37.8136&lng=144.9631&tz=Australia/Melbourne`,
      { next: { revalidate: 86400 } }
    );
    if (res.ok) {
      const json = (await res.json()) as { data?: { tithi?: { en?: string }; nakshatra?: { en?: string } } };
      tithiEn = json.data?.tithi?.en ?? tithiEn;
      nakshatraEn = json.data?.nakshatra?.en ?? "";
    }
  } catch {
    // fall back to defaults
  }

  return new ImageResponse(
    (
      <div
        style={{
          width: "1200px",
          height: "630px",
          background: "#FFF6EE",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "serif",
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "12px",
            background: "linear-gradient(90deg, #D4603A, #E8875A, #D4A547)",
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            height: "12px",
            background: "linear-gradient(90deg, #D4603A, #E8875A, #D4A547)",
          }}
        />
        <div style={{ fontSize: "36px", color: "#8B4020", marginBottom: "8px", opacity: 0.85 }}>
          Telugu Panchangam
        </div>
        <div style={{ fontSize: "28px", color: "#6B3010", marginBottom: "32px", fontStyle: "italic" }}>
          {dateStr}
        </div>
        <div
          style={{
            fontSize: "88px",
            color: "#C04020",
            fontWeight: "bold",
            lineHeight: 1.1,
            marginBottom: "8px",
          }}
        >
          {tithiEn}
        </div>
        {nakshatraEn && (
          <div style={{ fontSize: "36px", color: "#8B4020", fontStyle: "italic", marginBottom: "24px" }}>
            {nakshatraEn}
          </div>
        )}
        <div style={{ fontSize: "20px", color: "#8B4020", opacity: 0.6, marginTop: "16px" }}>
          telugupanchangam.app
        </div>
      </div>
    ),
    { ...size }
  );
}
