import { type LabelHTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("block text-xs font-medium uppercase tracking-wide text-ink-muted", className)}
      {...props}
    />
  );
}
