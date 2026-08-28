import { type ReactNode } from 'react';

interface CardGroupProps {
  title: string;
  children: ReactNode;
  className?: string;
}

export default function CardGroup({ title, children, className = '' }: CardGroupProps) {
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <h3 className="text-xs font-medium text-warm-400 uppercase tracking-wider px-1">
        {title}
      </h3>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
