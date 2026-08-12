import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

type AlertTone = "default" | "success" | "warning" | "error";

const toneClass: Record<AlertTone, string> = {
  default: "border-surface-border bg-surface-raised text-ink-muted",
  success: "border-emerald-800/50 bg-emerald-950/40 text-emerald-100",
  warning: "border-amber-700/50 bg-amber-950/40 text-amber-100",
  error: "border-red-800/50 bg-red-950/40 text-red-100",
};

export function Alert({
  tone = "default",
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { tone?: AlertTone }) {
  return (
    <div
      role="status"
      className={cn("rounded-lg border px-4 py-3 text-sm", toneClass[tone], className)}
      {...props}
    />
  );
}
