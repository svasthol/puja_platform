"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { logout } from "@/lib/api/admin";
import { roleLabel } from "@/lib/auth/roles";
import { clearTokens } from "@/lib/auth/tokens";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export function Header({ title, description }: { title: string; description?: string }) {
  const router = useRouter();
  const { data: me } = useAdminMe();

  async function handleLogout() {
    await logout();
    clearTokens();
    router.replace("/login");
  }

  return (
    <header className="flex items-start justify-between border-b border-surface-border bg-surface/50 px-8 py-6 backdrop-blur-sm">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
      </div>
      <div className="flex items-center gap-3">
        {me?.is_admin && <Badge tone="success">admin</Badge>}
        {me?.is_support && !me?.is_admin && <Badge>support</Badge>}
        <span className="hidden text-sm text-ink-muted sm:inline">{roleLabel(me)}</span>
        <Button variant="ghost" onClick={handleLogout}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
