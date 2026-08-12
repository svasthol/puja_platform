"use client";

import { cn } from "@/lib/utils/cn";

export function Tabs({
  tabs,
  active,
  onChange,
  className,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex gap-1 overflow-x-auto rounded-lg border border-surface-border bg-surface p-1",
        className,
      )}
      role="tablist"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition",
            active === tab.id
              ? "bg-brand/15 text-brand-glow shadow-sm"
              : "text-ink-muted hover:bg-surface-raised hover:text-ink",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
