import React from 'react';
import { cn } from './Card'; // reuse utility

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'outline';
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  const variants = {
    default: "bg-surface-container-highest text-on-surface-variant",
    success: "bg-[#004d40]/20 text-[#1de9b6] border border-[#004d40]/50",
    warning: "bg-warning/20 text-warning border border-warning/50",
    danger: "bg-error-container/20 text-error border border-error-container/50",
    info: "bg-primary-container/20 text-primary border border-primary-container/50",
    outline: "border border-outline-variant text-on-surface-variant",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium tracking-wide font-mono uppercase whitespace-nowrap",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
