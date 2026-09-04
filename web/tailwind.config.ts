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
        background: "var(--background)",
        foreground: "var(--foreground)",
        agent: {
          dark: "#0a0d14",
          card: "rgba(18, 24, 38, 0.75)",
          border: "rgba(255, 255, 255, 0.08)",
          accent: "#6366f1",
          cyan: "#06b6d4",
          purple: "#a855f7",
          emerald: "#10b981",
        },
      },
    },
  },
  plugins: [],
};
export default config;
