/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral, professional fintech palette (slate + blue accent).
        // Generic on purpose — carries no specific institution's brand identity.
        brand: {
          primary:      '#1e293b',  // slate-800  — headers, primary surfaces
          'primary-dk': '#0f172a',  // slate-900  — sidebar / deep background
          'primary-md': '#334155',  // slate-700  — hover / mid surfaces
          accent:       '#3b82f6',  // blue-500   — interactive accent
          'accent-lt':  '#60a5fa',  // blue-400
          'accent-dk':  '#2563eb',  // blue-600
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
