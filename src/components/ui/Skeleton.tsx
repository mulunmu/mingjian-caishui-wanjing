interface SkeletonProps {
  width?: string;
  height?: string;
  rounded?: boolean;
  className?: string;
}

export default function Skeleton({
  width = '100%',
  height = '16px',
  rounded = false,
  className = '',
}: SkeletonProps) {
  return (
    <div
      className={`skeleton-shimmer ${rounded ? 'rounded-full' : 'rounded-md'} ${className}`}
      style={{ width, height }}
    />
  );
}
