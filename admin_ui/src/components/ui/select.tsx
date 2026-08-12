import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...props }, ref) {
    return (
      <select
        ref={ref}
        className={cn(
          "w-full rounded-lg border border-surface-border bg-surface px-3 py-2.5 text-sm text-ink focus-ring",
          className,
        )}
        {...props}
      >
        {children}
      </select>
    );
  },
);
