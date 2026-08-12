"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAdminMe } from "@/lib/hooks/use-admin-me";
import { isAuthenticated } from "@/lib/auth/tokens";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState(false);
  const { isError, isLoading } = useAdminMe({ enabled: mounted && authed });

  useEffect(() => {
    setMounted(true);
    setAuthed(isAuthenticated());
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!authed) {
      router.replace("/login");
      return;
    }
    if (isError) {
      router.replace("/login");
    }
  }, [mounted, authed, isError, router]);

  if (!mounted || !authed || isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-muted">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          <p className="text-sm">Verifying session…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
