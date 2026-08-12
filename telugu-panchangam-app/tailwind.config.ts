import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: "#FFF6EE",
        "text-primary": "#1A0800",
        "text-secondary": "#6B3010",
        accent: "#C04020",
        label: "#8B4020",
        gold: "#A07000",
        danger: "#8B0000",
        auspicious: "#167040",
      },
      backgroundImage: {
        "header-grad":
          "linear-gradient(135deg, #D4603A, #E8875A, #D4A547)",
      },
      fontFamily: {
        "noto-telugu": ["'Noto Sans Telugu'", "sans-serif"],
        playfair: ["'Playfair Display'", "serif"],
        lora: ["'Lora'", "serif"],
      },
    },
  },
  plugins: [],
};
export default config;
