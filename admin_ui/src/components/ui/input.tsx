import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "w-full rounded-lg border border-surface-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus-ring",
          className,
        )}
        data-gramm="false"
        data-gramm_editor="false"
        data-enable-grammarly="false"
        {...props}
      />
    );
  },
);
