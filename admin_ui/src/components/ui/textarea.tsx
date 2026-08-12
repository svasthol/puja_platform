import { forwardRef, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          "min-h-[88px] w-full resize-y rounded-lg border border-surface-border bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus-ring",
          className,
        )}
        data-gramm="false"
        {...props}
      />
    );
  },
);
