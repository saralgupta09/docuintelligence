/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', 'ui-sans-serif', 'system-ui'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
        display: ['"Syne"', 'ui-sans-serif'],
      },
      colors: {
        ink: {
          50:  '#f0f0f5',
          100: '#e0e1ed',
          200: '#c2c3db',
          300: '#9b9dc0',
          400: '#7476a4',
          500: '#565886',
          600: '#44466e',
          700: '#333555',
          800: '#22233c',
          900: '#141526',
          950: '#0b0c17',
        },
        ember: {
          400: '#fb923c',
          500: '#f97316',
          600: '#ea6a10',
        },
        jade: {
          400: '#34d399',
          500: '#10b981',
        },
        rose: {
          400: '#fb7185',
          500: '#f43f5e',
        },
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          '0%': { opacity: '0', transform: 'translateX(-12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'dot-bounce': {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.25s ease-out',
        'slide-in': 'slide-in 0.2s ease-out',
        'dot1': 'dot-bounce 1.4s infinite 0ms',
        'dot2': 'dot-bounce 1.4s infinite 160ms',
        'dot3': 'dot-bounce 1.4s infinite 320ms',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        shimmer: 'shimmer 1.8s linear infinite',
      },
    },
  },
  plugins: [],
}
