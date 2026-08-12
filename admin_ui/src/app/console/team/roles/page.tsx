"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { assignUserRole, fetchUserRoles, revokeUserRole } from "@/lib/api/admin";
import { canManageRoles } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function TeamRolesPage() {
  const { data: me } = useAdminMe();
  const canEdit = canManageRoles(me);
  const qc = useQueryClient();

  const [userId, setUserId] = useState("");
  const [role, setRole] = useState<"admin" | "support">("support");
  const [reason, setReason] = useState("");

  const rolesQuery = useQuery({
    queryKey: ["admin", "user-roles", userId],
    queryFn: () => fetchUserRoles(userId.trim()),
    enabled: false,
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      assignUserRole(userId.trim(), { role, change_reason: reason.trim() || undefined }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "user-roles", userId] }),
  });

  const revokeMutation = useMutation({
    mutationFn: (r: string) => revokeUserRole(userId.trim(), r),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "user-roles", userId] }),
  });

  return (
    <>
      <Header
        title="Team roles"
        description="Assign admin or support roles. Requires admin role. Last-admin guard enforced by API."
      />
      <div className="max-w-2xl space-y-6 p-8">
        {!canEdit && (
          <p className="rounded-lg border border-amber-800/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
            Your account has the <strong>support</strong> role — role management is admin-only.
          </p>
        )}

        <Card>
          <CardTitle>Lookup user</CardTitle>
          <CardDescription>
            Enter the user&apos;s UUID (from bootstrap output or database). Phone search lands in Sprint 4B (
            A-SEARCH).
          </CardDescription>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row">
            <Input
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
              className="font-mono text-xs"
            />
            <Button
              variant="secondary"
              onClick={() => rolesQuery.refetch()}
              disabled={!userId.trim()}
            >
              Load roles
            </Button>
          </div>

          {rolesQuery.data && (
            <div className="mt-4 flex flex-wrap gap-2">
              {rolesQuery.data.roles.length ? (
                rolesQuery.data.roles.map((r) => (
                  <Badge key={r} tone={r === "admin" ? "success" : "default"}>
                    {r}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-ink-muted">No roles assigned</span>
              )}
            </div>
          )}
        </Card>

        {canEdit && (
          <Card>
            <CardTitle>Assign role</CardTitle>
            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                assignMutation.mutate();
              }}
            >
              <label className="block text-sm text-ink-muted">
                Role
                <select
                  className="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2.5 text-sm"
                  value={role}
                  onChange={(e) => setRole(e.target.value as "admin" | "support")}
                >
                  <option value="support">support</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <label className="block text-sm text-ink-muted">
                Change reason
                <Input
                  className="mt-1"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="onboarding"
                />
              </label>
              <Button type="submit" disabled={!userId.trim() || assignMutation.isPending}>
                Assign role
              </Button>
            </form>

            {rolesQuery.data?.roles.map((r) => (
              <div key={r} className="mt-4 flex items-center justify-between border-t border-surface-border pt-4">
                <span className="text-sm text-ink-muted">Revoke {r}</span>
                <Button
                  variant="danger"
                  type="button"
                  disabled={revokeMutation.isPending}
                  onClick={() => revokeMutation.mutate(r)}
                >
                  Revoke
                </Button>
              </div>
            ))}
          </Card>
        )}
      </div>
    </>
  );
}
