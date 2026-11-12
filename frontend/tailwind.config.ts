import type { Config } from "tailwindcss";
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { navy: { 900: "#0b1b34", 700: "#1d3557" }, brand: { 600: "#1f5fd1", 50: "#eef4ff" } } } },
  plugins: [],
} satisfies Config;
