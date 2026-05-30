/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        // Display / titres / gros chiffres patrimoine — serif éditorial
        serif: ['Newsreader', 'Libre Bodoni', 'Georgia', 'serif'],
        // Corps / UI
        sans: ['Public Sans', 'system-ui', '-apple-system', 'sans-serif'],
        // Chiffres tabulaires
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        border: "oklch(var(--border) / <alpha-value>)",
        input: "oklch(var(--input) / <alpha-value>)",
        ring: "oklch(var(--ring) / <alpha-value>)",
        background: "oklch(var(--background) / <alpha-value>)",
        foreground: "oklch(var(--foreground) / <alpha-value>)",
        primary: {
          DEFAULT: "oklch(var(--primary) / <alpha-value>)",
          foreground: "oklch(var(--primary-foreground) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "oklch(var(--secondary) / <alpha-value>)",
          foreground: "oklch(var(--secondary-foreground) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "oklch(var(--destructive) / <alpha-value>)",
          foreground: "oklch(var(--destructive-foreground) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "oklch(var(--muted) / <alpha-value>)",
          foreground: "oklch(var(--muted-foreground) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "oklch(var(--accent) / <alpha-value>)",
          foreground: "oklch(var(--accent-foreground) / <alpha-value>)",
        },
        popover: {
          DEFAULT: "oklch(var(--popover) / <alpha-value>)",
          foreground: "oklch(var(--popover-foreground) / <alpha-value>)",
        },
        card: {
          DEFAULT: "oklch(var(--card) / <alpha-value>)",
          foreground: "oklch(var(--card-foreground) / <alpha-value>)",
        },
        // Sémantique financière — gain (sapin) / perte (bordeaux) / alerte (ambre)
        gain: {
          DEFAULT: "oklch(var(--gain) / <alpha-value>)",
          foreground: "oklch(var(--gain-foreground) / <alpha-value>)",
        },
        loss: {
          DEFAULT: "oklch(var(--loss) / <alpha-value>)",
          foreground: "oklch(var(--loss-foreground) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "oklch(var(--warning) / <alpha-value>)",
          foreground: "oklch(var(--warning-foreground) / <alpha-value>)",
        },
        // Alias success → gain (rétro-compat)
        success: {
          DEFAULT: "oklch(var(--gain) / <alpha-value>)",
          foreground: "oklch(var(--gain-foreground) / <alpha-value>)",
        },
        // Alias legacy remappés vers la palette A (laiton / sapin)
        emerald: {
          DEFAULT: "oklch(var(--emerald, 0.52 0.09 150) / <alpha-value>)",
          glow: "oklch(0.52 0.09 150 / 0.15)",
        },
        indigo: {
          DEFAULT: "oklch(var(--indigo, 0.64 0.10 78) / <alpha-value>)",
          glow: "oklch(0.64 0.10 78 / 0.15)",
        },
        gold: {
          DEFAULT: "oklch(var(--gold, 0.64 0.10 78) / <alpha-value>)",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 oklch(0.64 0.10 78 / 0)" },
          "50%": { boxShadow: "0 0 16px 4px oklch(0.64 0.10 78 / 0.22)" },
        },
        "counter-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        shimmer: "shimmer 2.4s linear infinite",
        float: "float 3s ease-in-out infinite",
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "counter-in": "counter-in 0.4s cubic-bezier(0.23,1,0.32,1) forwards",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
