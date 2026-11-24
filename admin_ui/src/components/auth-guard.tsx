"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAdminMe } from "@/lib/hooks/use-admin-me";
import { clearTokens, isAuthenticated } from "@/lib/auth/tokens";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
  }, []);

  const tokenPresent = hydrated && isAuthenticated();
  const meQuery = useAdminMe({ enabled: tokenPresent });

  // Fixed-length dependency array (React 19) — never add/remove deps across saves/HMR.
  useEffect(() => {
    if (!hydrated) return;
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    if (meQuery.isError) {
      clearTokens();
      router.replace("/login");
    }
    // #region agent log
    fetch("http://127.0.0.1:7654/ingest/3666bc3a-f5d5-4e97-9312-8addb48dd2d4", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "e7cdae" },
      body: JSON.stringify({
        sessionId: "e7cdae",
        hypothesisId: "H4-stable-deps",
        location: "auth-guard.tsx:redirect-effect",
        message: "redirect effect ran",
        data: {
          hydrated,
          hasToken: isAuthenticated(),
          isError: meQuery.isError,
          status: meQuery.status,
        },
        timestamp: Date.now(),
        runId: "post-fix",
      }),
    }).catch(() => {});
    // #endregion
  }, [hydrated, meQuery.isError, router]);

  if (!hydrated) {
    return null;
  }

  if (!isAuthenticated()) {
    return null;
  }

  if (meQuery.isError) {
    return null;
  }

  if (meQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-muted">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          <p className="text-sm">Verifying session…</p>
          <p className="max-w-xs text-center text-xs text-ink-faint">
            Waiting for API. Ensure the backend is up and NEXT_PUBLIC_API_URL matches
            (e.g. http://127.0.0.1:8000/v1).
          </p>
        </div>
      </div>
    );
  }

  if (!meQuery.isSuccess) {
    return null;
  }

  return <>{children}</>;
}