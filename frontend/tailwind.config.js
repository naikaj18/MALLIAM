/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        textPrimary: "#1C1C1E",
        textSecondary: "#6E6E73",
        accentBlue: "#007AFF",
      },
      fontFamily: {
        inter: ["Inter", "sans-serif"],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out both',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: 0 },
          '100%': { opacity: 1 },
        },
      },
    },
  },
  plugins: [],
};