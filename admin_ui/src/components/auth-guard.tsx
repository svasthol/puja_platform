"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAdminMe } from "@/lib/hooks/use-admin-me";
import { clearTokens, isAuthenticated } from "@/lib/auth/tokens";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [authed, setAuthed] = useState(false);
  const { isError, isPending, isFetching, isSuccess } = useAdminMe({
    enabled: mounted && authed,
  });

  useEffect(() => {
    setMounted(true);
    setAuthed(isAuthenticated());
    // #region agent log
    fetch("http://127.0.0.1:7654/ingest/3666bc3a-f5d5-4e97-9312-8addb48dd2d4", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "e7cdae" },
      body: JSON.stringify({
        sessionId: "e7cdae",
        hypothesisId: "H3-auth-guard",
        location: "auth-guard.tsx:mount",
        message: "AuthGuard mounted",
        data: { authed: isAuthenticated() },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (!authed) {
      router.replace("/login");
      return;
    }
    if (isError) {
      clearTokens();
      router.replace("/login");
    }
    // #region agent log
    fetch("http://127.0.0.1:7654/ingest/3666bc3a-f5d5-4e97-9312-8addb48dd2d4", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "e7cdae" },
      body: JSON.stringify({
        sessionId: "e7cdae",
        hypothesisId: "H3-auth-guard",
        location: "auth-guard.tsx:session-state",
        message: "AuthGuard session query state",
        data: { authed, isError, isPending, isFetching, isSuccess },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
  }, [mounted, authed, isError, isPending, isFetching, isSuccess, router]);

  if (!mounted) {
    return null;
  }

  if (!authed) {
    return null;
  }

  if (isError) {
    return null;
  }

  if (!isSuccess && (isPending || isFetching)) {
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

  if (!isSuccess) {
    return null;
  }

  return <>{children}</>;
}
