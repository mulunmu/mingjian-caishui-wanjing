import { type InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label className="text-xs font-medium text-warm-500">{label}</label>
        )}
        <input
          ref={ref}
          className={`
            px-3 py-2 text-sm bg-white border rounded-md
            text-warm-800 placeholder:text-warm-400
            outline-none transition-all duration-200
            border-warm-200
            focus:border-amber focus:shadow-[0_0_0_3px_rgba(161,138,95,0.12)]
            ${error ? 'border-terracotta' : ''}
            ${className}
          `}
          {...props}
        />
        {error && <span className="text-xs text-terracotta">{error}</span>}
      </div>
    );
  }
);

Input.displayName = 'Input';
export default Input;
