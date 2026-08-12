"use client";

import { AuthGuard } from "@/components/auth-guard";
import { Sidebar } from "@/components/layout/sidebar";

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex min-h-screen flex-1 flex-col">{children}</main>
      </div>
    </AuthGuard>
  );
}
