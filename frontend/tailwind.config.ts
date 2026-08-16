import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { surface: "#ffffff" } } },
  plugins: [],
} satisfies Config;
