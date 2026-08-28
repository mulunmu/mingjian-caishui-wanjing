import { type ReactNode } from 'react';

interface ChipProps {
  children: ReactNode;
  selected?: boolean;
  onClick?: () => void;
  color?: 'default' | 'amber' | 'copper' | 'sage' | 'mist';
  size?: 'sm' | 'md';
}

const colorStyles = {
  default: {
    base: 'bg-warm-100 text-warm-600 border-warm-200',
    selected: 'bg-amber/10 text-amber border-amber',
  },
  amber: {
    base: 'bg-amber/5 text-amber border-amber/20',
    selected: 'bg-amber/15 text-amber-dark border-amber',
  },
  copper: {
    base: 'bg-copper/5 text-copper border-copper/20',
    selected: 'bg-copper/15 text-copper border-copper',
  },
  sage: {
    base: 'bg-sage/5 text-sage border-sage/20',
    selected: 'bg-sage/15 text-sage border-sage',
  },
  mist: {
    base: 'bg-mist/5 text-mist border-mist/20',
    selected: 'bg-mist/15 text-mist border-mist',
  },
};

export default function Chip({
  children,
  selected = false,
  onClick,
  color = 'default',
  size = 'md',
}: ChipProps) {
  const styles = colorStyles[color];
  return (
    <button
      onClick={onClick}
      className={`
        inline-flex items-center gap-1 border rounded-full
        transition-all duration-150 cursor-pointer select-none
        ${size === 'sm' ? 'px-2.5 py-0.5 text-xs' : 'px-3 py-1 text-sm'}
        ${selected ? styles.selected : styles.base}
        hover:opacity-80
      `}
    >
      {children}
    </button>
  );
}
