"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createPromo, fetchPromos, updatePromo } from "@/lib/api/promos";
import { canManagePromos } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

function toIsoLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function PromosPage() {
  const { data: me } = useAdminMe();
  const canEdit = canManagePromos(me);
  const qc = useQueryClient();

  const [code, setCode] = useState("");
  const [discountPct, setDiscountPct] = useState("10");
  const [maxUses, setMaxUses] = useState("1");
  const [validFrom, setValidFrom] = useState(() => toIsoLocalInput(new Date()));
  const [validUntil, setValidUntil] = useState(() =>
    toIsoLocalInput(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)),
  );
  const [message, setMessage] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "promos"],
    queryFn: () => fetchPromos(),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createPromo({
        code: code.trim().toUpperCase(),
        discount_pct: Number(discountPct),
        max_uses_per_user: Number(maxUses),
        valid_from: new Date(validFrom).toISOString(),
        valid_until: new Date(validUntil).toISOString(),
        is_active: true,
      }),
    onSuccess: async () => {
      setCode("");
      setMessage("Promo created.");
      await qc.invalidateQueries({ queryKey: ["admin", "promos"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updatePromo(id, { is_active }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "promos"] });
    },
    onError: (e: Error) => setMessage(e.message),
  });

  return (
    <>
      <Header
        title="Promo codes"
        description="Create and manage checkout discount codes (admin only)."
      />
      <PageContent>
        {message ? (
          <p className="mb-4 rounded-lg border border-surface-border bg-surface-raised/80 px-3 py-2 text-sm text-ink-muted">
            {message}
          </p>
        ) : null}

        {canEdit ? (
          <Card className="mb-6">
            <CardTitle className="text-base">New promo</CardTitle>
            <CardDescription className="mt-1">
              valid_until must be after valid_from (enforced in API + DB).
            </CardDescription>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="code">Code</Label>
                <Input
                  id="code"
                  className="mt-1 font-mono uppercase"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="DIWALI10"
                />
              </div>
              <div>
                <Label htmlFor="discount">Discount %</Label>
                <Input
                  id="discount"
                  type="number"
                  min={1}
                  max={100}
                  className="mt-1"
                  value={discountPct}
                  onChange={(e) => setDiscountPct(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="max-uses">Max uses per user</Label>
                <Input
                  id="max-uses"
                  type="number"
                  min={1}
                  className="mt-1"
                  value={maxUses}
                  onChange={(e) => setMaxUses(e.target.value)}
                />
              </div>
              <div />
              <div>
                <Label htmlFor="valid-from">Valid from</Label>
                <Input
                  id="valid-from"
                  type="datetime-local"
                  className="mt-1"
                  value={validFrom}
                  onChange={(e) => setValidFrom(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="valid-until">Valid until</Label>
                <Input
                  id="valid-until"
                  type="datetime-local"
                  className="mt-1"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                />
              </div>
            </div>
            <Button
              type="button"
              className="mt-4"
              disabled={!code.trim() || createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              {createMutation.isPending ? "Creating…" : "Create promo"}
            </Button>
          </Card>
        ) : (
          <p className="mb-6 text-sm text-ink-muted">Promo management requires admin role.</p>
        )}

        <Card>
          <CardTitle className="text-base">Active promos</CardTitle>
          {isLoading ? (
            <p className="mt-3 text-sm text-ink-muted">Loading…</p>
          ) : !data?.promos.length ? (
            <p className="mt-3 text-sm text-ink-muted">No promo codes yet.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-ink-faint">
                    <th className="py-2 pr-3">Code</th>
                    <th className="py-2 pr-3">Discount</th>
                    <th className="py-2 pr-3">Window</th>
                    <th className="py-2 pr-3">Redemptions</th>
                    <th className="py-2 pr-3">Status</th>
                    {canEdit ? <th className="py-2">Actions</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {data.promos.map((p) => (
                    <tr key={p.id} className="border-b border-surface-border/50">
                      <td className="py-2 pr-3 font-mono">{p.code}</td>
                      <td className="py-2 pr-3">{p.discount_pct}%</td>
                      <td className="py-2 pr-3 whitespace-nowrap text-xs">
                        {new Date(p.valid_from).toLocaleDateString()} →{" "}
                        {new Date(p.valid_until).toLocaleDateString()}
                      </td>
                      <td className="py-2 pr-3">{p.redemption_count}</td>
                      <td className="py-2 pr-3">
                        <Badge tone={p.is_active ? "success" : "default"}>
                          {p.is_active ? "active" : "inactive"}
                        </Badge>
                      </td>
                      {canEdit ? (
                        <td className="py-2">
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            disabled={toggleMutation.isPending}
                            onClick={() =>
                              toggleMutation.mutate({ id: p.id, is_active: !p.is_active })
                            }
                          >
                            {p.is_active ? "Deactivate" : "Activate"}
                          </Button>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </PageContent>
    </>
  );
}
