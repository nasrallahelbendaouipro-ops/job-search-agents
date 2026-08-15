import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Le bleu de l'en-tête des lettres de motivation : le dashboard et les
        // documents produits partagent la même identité.
        brand: {
          DEFAULT: "#1F3C73",
          light: "#2E56A3",
          dark: "#152A52",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
