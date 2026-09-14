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
        /* 纸底中性阶（沿用 warm-* 类名，值对齐 ivory） */
        warm: {
          50: '#F7F4EE',
          100: '#EFEBE3',
          200: '#E4DED3',
          300: '#D0C9BC',
          400: '#8A9099',
          500: '#4A5568',
          600: '#3A4558',
          700: '#2A3548',
          800: '#152446',
          900: '#0B1C3E',
        },
        /* amber-* = 古铜金强调色（兼容既有类名） */
        amber: {
          DEFAULT: '#A18A5F',
          light: '#B8A078',
          dark: '#8F7850',
        },
        navy: {
          DEFAULT: '#152446',
          deep: '#0B1C3E',
          soft: '#3B5B7A',
        },
        copper: '#8F7850',
        terracotta: '#DC2626',
        sage: '#059669',
        mist: '#3B5B7A',
        warn: '#F57C00',
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      boxShadow: {
        'warm-sm': '0 1px 3px rgba(11, 28, 62, 0.04)',
        'warm-md': '0 4px 16px rgba(11, 28, 62, 0.08)',
        'warm-lg': '0 8px 32px rgba(11, 28, 62, 0.12)',
        'warm-accent': '0 0 0 1px #A18A5F, 0 4px 16px rgba(161, 138, 95, 0.14)',
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
