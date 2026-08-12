"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchAdvanceAmount, updateAdvanceAmount } from "@/lib/api/admin";
import { canEditAdvanceAmount } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function AdvanceSettingsPage() {
  const { data: me } = useAdminMe();
  const qc = useQueryClient();
  const canEdit = canEditAdvanceAmount(me);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "advance"],
    queryFn: fetchAdvanceAmount,
  });

  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data?.amount != null) setAmount(String(data.amount));
  }, [data?.amount]);

  const mutation = useMutation({
    mutationFn: () =>
      updateAdvanceAmount({
        amount: Number(amount),
        change_reason: reason.trim() || undefined,
      }),
    onSuccess: async () => {
      setMessage("Saved — next customer quote will use the new advance amount.");
      await qc.invalidateQueries({ queryKey: ["admin", "advance"] });
    },
    onError: (err: Error) => setMessage(err.message),
  });

  return (
    <>
      <Header
        title="Advance booking amount"
        description="Platform-wide default for advance_balance payment mode. Changes are audited."
      />
      <div className="max-w-xl p-8">
        <Card>
          <CardTitle>Current setting</CardTitle>
          <CardDescription>
            {canEdit
              ? "Admin role required to update. Support can read via API only."
              : "You have read-only access (support role)."}
          </CardDescription>

          {isLoading && <p className="mt-4 text-sm text-ink-muted">Loading…</p>}
          {error && (
            <p className="mt-4 text-sm text-red-300">{(error as Error).message}</p>
          )}

          {data && (
            <div className="mt-6 space-y-4">
              <p className="text-3xl font-semibold text-brand-glow">
                ₹{data.amount}{" "}
                <span className="text-base font-normal text-ink-muted">{data.currency}</span>
              </p>
              {data.updated_at && (
                <p className="text-xs text-ink-faint">Last updated: {data.updated_at}</p>
              )}

              {canEdit && (
                <form
                  className="space-y-4 border-t border-surface-border pt-6"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setMessage(null);
                    mutation.mutate();
                  }}
                >
                  <label className="block text-sm text-ink-muted">
                    New amount (INR)
                    <Input
                      className="mt-1"
                      type="number"
                      min={1}
                      max={10000}
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      required
                    />
                  </label>
                  <label className="block text-sm text-ink-muted">
                    Change reason (audit trail)
                    <Input
                      className="mt-1"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="e.g. festival season adjustment"
                      maxLength={300}
                    />
                  </label>
                  <Button type="submit" disabled={mutation.isPending}>
                    {mutation.isPending ? "Saving…" : "Save changes"}
                  </Button>
                </form>
              )}

              {message && (
                <p className="rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink-muted">
                  {message}
                </p>
              )}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
