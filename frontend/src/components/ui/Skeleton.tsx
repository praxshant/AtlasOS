import { cn } from "./Card"

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-variant/50", className)}
      {...props}
    />
  )
}
