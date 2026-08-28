interface DividerProps {
  className?: string;
  vertical?: boolean;
}

export default function Divider({ className = '', vertical = false }: DividerProps) {
  return vertical ? (
    <div className={`w-px h-full bg-warm-200 ${className}`} />
  ) : (
    <div className={`h-px w-full bg-warm-200 ${className}`} />
  );
}
