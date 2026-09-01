/** @type {import('tailwindcss').DefaultConfig} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#12151C",
        panel: "#1A1F2A",
        edge: "#2A3142",
        ink: "#E8EAF0",
        muted: "#8A93A6",
        proof: "#E2564A",
        verified: "#4CC38A",
        suspect: "#E5A54B",
        codebg: "#0D1017",
      },
      fontFamily: {
        latin: ["Space Grotesk", "sans-serif"],
        farsi: ["Vazirmatn", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      borderRadius: {
        DEFAULT: "8px",
      },
      boxShadow: {
        panel: "0 8px 24px rgba(0,0,0,0.35)",
        scan: "0 0 32px rgba(232,234,240,0.08)",
      },
    },
  },
  plugins: [],
};
