interface CuteEyeLogoProps {
  size?: number;
  className?: string;
}

export function CuteEyeLogo({ size = 32, className = '' }: CuteEyeLogoProps) {
  return (
    <img
      src="/logo.jpg"
      alt="明鉴・财税票・万景"
      width={size}
      height={size}
      className={`rounded-lg object-cover ${className}`}
    />
  );
}
