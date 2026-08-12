"use client";

interface MoonPhaseProps {
  illumination: number; // 0-100
  isWaxing: boolean;
  size?: number;
  phaseName?: { te: string; en: string };
  lang?: "te" | "en";
}

/**
 * SVG moon phase visual component.
 * Renders the actual shape of the moon — not an emoji.
 * Dark fill #1A0800, lit fill #F5E6C8.
 * Includes glow effect and optional phase label.
 */
export default function MoonPhase({
  illumination,
  isWaxing,
  size = 64,
  phaseName,
  lang = "en",
}: MoonPhaseProps) {
  const r = size / 2;
  const cx = r;
  const cy = r;

  // Normalize illumination to 0-1
  const frac = Math.max(0, Math.min(100, illumination)) / 100;

  // Calculate the terminator curve
  // When frac=0: new moon (all dark). frac=0.5: half. frac=1: full (all lit).
  // The terminator is an ellipse whose x-radius varies with illumination.
  const terminatorRx = Math.abs(2 * frac - 1) * r;
  const isMoreThanHalf = frac > 0.5;

  // Build the lit portion path
  // We draw an arc for the outer edge (always a semicircle) and an arc for the terminator
  let litPath: string;

  if (frac < 0.01) {
    // New moon — no lit portion
    litPath = "";
  } else if (frac > 0.99) {
    // Full moon — entire circle lit
    litPath = `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${r} ${r} 0 1 1 ${cx} ${cy - r}`;
  } else if (isWaxing) {
    // Waxing: lit portion is on the right
    // Right semicircle (outer edge)
    const outerSweep = `M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx} ${cy + r}`;
    // Terminator (inner edge) — curves left or right depending on phase
    const innerSweep = isMoreThanHalf
      ? `A ${terminatorRx} ${r} 0 0 1 ${cx} ${cy - r}`
      : `A ${terminatorRx} ${r} 0 0 0 ${cx} ${cy - r}`;
    litPath = `${outerSweep} ${innerSweep}`;
  } else {
    // Waning: lit portion is on the left
    // Left semicircle (outer edge)
    const outerSweep = `M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx} ${cy + r}`;
    // Terminator
    const innerSweep = isMoreThanHalf
      ? `A ${terminatorRx} ${r} 0 0 0 ${cx} ${cy - r}`
      : `A ${terminatorRx} ${r} 0 0 1 ${cx} ${cy - r}`;
    litPath = `${outerSweep} ${innerSweep}`;
  }

  // Glow intensity: stronger at full moon, subtle otherwise
  const glowOpacity = 0.2 + frac * 0.4;
  const glowRadius = 4 + frac * 6;

  // Height for label area
  const labelHeight = phaseName ? 16 : 0;
  const totalHeight = size + labelHeight;

  return (
    <svg
      width={size}
      height={totalHeight}
      viewBox={`0 0 ${size} ${totalHeight}`}
      aria-label={`Moon phase: ${Math.round(illumination)}% illuminated`}
    >
      <defs>
        <filter id={`moon-glow-${size}`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={glowRadius} result="blur" />
          <feFlood floodColor="#F5E6C8" floodOpacity={glowOpacity} result="color" />
          <feComposite in="color" in2="blur" operator="in" result="glow" />
          <feMerge>
            <feMergeNode in="glow" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g filter={`url(#moon-glow-${size})`}>
        {/* Dark base circle */}
        <circle cx={cx} cy={cy} r={r - 0.5} fill="#1A0800" />
        {/* Lit portion with smooth transition */}
        {litPath && (
          <path
            d={litPath}
            fill="#F5E6C8"
            style={{ transition: "d 0.6s ease-in-out" }}
          />
        )}
        {/* Subtle border */}
        <circle
          cx={cx}
          cy={cy}
          r={r - 0.5}
          fill="none"
          stroke="#8B4020"
          strokeWidth="0.5"
          opacity="0.3"
        />
      </g>

      {/* Phase label */}
      {phaseName && (
        <text
          x={cx}
          y={size + 12}
          textAnchor="middle"
          fontSize={Math.max(8, size / 8)}
          fill="#8B4020"
          opacity="0.7"
          fontFamily={lang === "te" ? "'Noto Sans Telugu', sans-serif" : "'Lora', serif"}
        >
          {lang === "te" ? phaseName.te : phaseName.en}
        </text>
      )}
    </svg>
  );
}
