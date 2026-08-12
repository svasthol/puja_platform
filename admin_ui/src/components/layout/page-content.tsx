import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils/cn";

export function PageContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mx-auto w-full max-w-7xl space-y-6 p-6 sm:p-8", className)}
      {...props}
    />
  );
}
