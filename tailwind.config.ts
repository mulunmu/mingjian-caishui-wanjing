import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        body: ['Inter', 'sans-serif'],
        headline: ['Inter', 'sans-serif'],
        code: ['"Source Code Pro"', 'monospace'],
        sans: ['Inter', 'PingFang SC', 'sans-serif'],
        number: ['DIN Alternate', 'monospace'],
      },
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))',
        },
        warm: {
          50: '#FAF6F1',
          100: '#F3ECE3',
          200: '#E8DFD3',
          300: '#D4CABC',
          400: '#B5A898',
          500: '#7A6E5E',
          600: '#5A4E3E',
          700: '#3E3428',
          800: '#2C2418',
          900: '#1A1410',
        },
        amber: {
          DEFAULT: '#C08B30',
          light: '#D4A853',
          dark: '#A87A28',
        },
        copper: '#D4763A',
        terracotta: '#C45A3A',
        sage: '#5A9E6F',
        mist: '#6A8FA8',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        'warm-sm': '0 1px 3px rgba(44, 36, 24, 0.04)',
        'warm-md': '0 4px 16px rgba(44, 36, 24, 0.08)',
        'warm-lg': '0 8px 32px rgba(44, 36, 24, 0.12)',
        'warm-accent': '0 0 0 1px #C08B30, 0 4px 16px rgba(192, 139, 48, 0.12)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        'fade-scale': {
          '0%': {
            opacity: '0',
            transform: 'translateY(-50%) scale(0.95)',
          },
          '100%': {
            opacity: '1',
            transform: 'translateY(-50%) scale(1)',
          },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        'fade-scale': 'fade-scale 0.2s ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
