import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Telugu Panchangam Calendar";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const MONTH_NAMES = [
  "",
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

interface Props {
  params: { year: string; month: string };
}

export default function OGImage({ params }: Props) {
  const { year, month } = params;
  const monthName = MONTH_NAMES[parseInt(month, 10)] ?? "";

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
        <div style={{ fontSize: "40px", color: "#8B4020", marginBottom: "16px" }}>
          Telugu Panchangam
        </div>
        <div style={{ fontSize: "80px", color: "#C04020", fontWeight: "bold" }}>
          {monthName} {year}
        </div>
        <div style={{ fontSize: "32px", color: "#6B3010", fontStyle: "italic", marginTop: "16px" }}>
          Calendar
        </div>
        <div style={{ fontSize: "20px", color: "#8B4020", opacity: 0.6, marginTop: "32px" }}>
          telugupanchangam.app
        </div>
      </div>
    ),
    { ...size }
  );
}
