import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          cyan: "#31e1ff",
          teal: "#14b8a6",
          purple: "#7b2cff",
        },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        // Paleta semântica de status/classificação
        status: {
          success: "#34d399",
          warning: "#fbbf24",
          danger: "#f87171",
          info: "#60a5fa",
          critical: "#ef4444",
        },
        classification: {
          routine: "#34d399",
          attention: "#fbbf24",
          urgent: "#fb923c",
          critical: "#ef4444",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glass: "0 4px 24px rgba(0, 0, 0, 0.30), inset 0 1px 0 rgba(255, 255, 255, 0.03)",
        "glass-hover":
          "0 4px 24px rgba(0, 0, 0, 0.30), 0 0 20px rgba(49, 225, 255, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.03)",
        elevated: "0 8px 32px rgba(0, 0, 0, 0.45)",
        "glow-cyan": "0 0 20px rgba(49, 225, 255, 0.15)",
        "glow-teal": "0 0 20px rgba(20, 184, 166, 0.18)",
        "glow-critical": "0 0 20px rgba(239, 68, 68, 0.35)",
        "neon-active": "0 0 8px rgba(49, 225, 255, 0.50)",
      },
      backgroundImage: {
        "deep-space":
          "linear-gradient(160deg, #050b1f 0%, #0a1028 35%, #0d1f2b 70%, #081018 100%)",
        "accent-gradient": "linear-gradient(135deg, #31e1ff 0%, #14b8a6 100%)",
        "critical-pulse":
          "linear-gradient(135deg, rgba(239,68,68,0.25) 0%, rgba(239,68,68,0.05) 100%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 5px rgba(239, 68, 68, 0.35)" },
          "50%": { boxShadow: "0 0 20px rgba(239, 68, 68, 0.70)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.3s ease-out",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        shimmer: "shimmer 3s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
