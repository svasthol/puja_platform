import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/utils/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary:
    "bg-brand text-surface font-semibold hover:bg-brand-glow shadow-sm shadow-brand/20",
  secondary:
    "bg-surface-raised border border-surface-border text-ink hover:border-brand/40",
  ghost: "text-ink-muted hover:text-ink hover:bg-surface-raised",
  danger: "bg-red-900/40 border border-red-700/50 text-red-200 hover:bg-red-900/60",
};

const sizes: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }
>(function Button(
  { className, variant = "primary", size = "md", disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg transition focus-ring disabled:cursor-not-allowed disabled:opacity-45",
        sizes[size],
        variants[variant],
        className,
      )}
      {...props}
    />
  );
});
