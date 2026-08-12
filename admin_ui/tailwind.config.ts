import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#14121a",
          raised: "#1c1924",
          border: "#2e2a38",
        },
        brand: {
          DEFAULT: "#e8a317",
          muted: "#b8860b",
          glow: "#f5c842",
        },
        ink: {
          DEFAULT: "#f4f0e8",
          muted: "#a8a0b4",
          faint: "#6b6378",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        panel: "0 4px 24px rgba(0, 0, 0, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;
