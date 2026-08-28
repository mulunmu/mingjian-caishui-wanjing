interface BadgeProps {
  level: 'high' | 'medium' | 'low' | 'info';
  children: React.ReactNode;
}

const levelStyles = {
  high: 'bg-terracotta/10 text-terracotta border-terracotta/20',
  medium: 'bg-amber/10 text-amber border-amber/20',
  low: 'bg-sage/10 text-sage border-sage/20',
  info: 'bg-mist/10 text-mist border-mist/20',
};

export default function Badge({ level, children }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center px-2 py-0.5 text-xs font-medium
        border rounded-sm ${levelStyles[level]}
      `}
    >
      {children}
    </span>
  );
}
