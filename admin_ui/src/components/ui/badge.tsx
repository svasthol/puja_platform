import { cn } from "@/lib/utils/cn";

type Tone = "default" | "success" | "warning" | "error";

const tones: Record<Tone, string> = {
  default: "bg-surface-raised border-surface-border text-ink-muted",
  success: "bg-emerald-950/40 border-emerald-800/50 text-emerald-200",
  warning: "bg-amber-950/40 border-amber-800/50 text-amber-200",
  error: "bg-red-950/40 border-red-800/50 text-red-200",
};

export function Badge({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
