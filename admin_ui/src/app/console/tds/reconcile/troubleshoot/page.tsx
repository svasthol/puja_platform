"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/client";

type TroubleshootResponse = {
  pujari_id: string;
  fy_start: string;
  fy_end_exclusive: string;
  accrual_enabled: boolean;
  tax: {
    card_tds_accrued_inr: string;
    ledger_tds_net_inr: string;
    drift_inr: string;
    status: string;
    green: boolean;
  };
  gross: {
    card_gross_facilitation_inr: string;
    ledger_taxable_base_net_inr: string;
    drift_inr: string;
    turnover_at_accept_from_bookings_inr: string;
    collected_gross_inr: string;
    status: string;
    informational_only: boolean;
  };
  booking_findings: Array<{
    booking_id: string;
    issue_code: string;
    total_amount_inr: string;
    tds_liability_inr: string;
    intent_status?: string | null;
    park_reason?: string | null;
    last_error?: string | null;
  }>;
  messages: string[];
  action_required: boolean;
  safe_fix_available: boolean;
};

export default function TdsReconcileTroubleshootPage() {
  const params = useSearchParams();
  const pujariId = params.get("pujari_id");
  const fyStart = params.get("fy_start");
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const queryKey = ["admin", "tds", "troubleshoot", pujariId, fyStart];

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey,
    enabled: Boolean(pujariId),
    queryFn: () => {
      const q = new URLSearchParams({ pujari_id: pujariId! });
      if (fyStart) q.set("fy_start", fyStart);
      return apiFetch<TroubleshootResponse>(
        `/admin/tds/fy-reconcile/troubleshoot?${q.toString()}`,
      );
    },
    staleTime: 30_000,
  });

  const fixMutation = useMutation({
    mutationFn: async () => {
      const q = new URLSearchParams({ pujari_id: pujariId! });
      if (fyStart) q.set("fy_start", fyStart);
      return apiFetch<TroubleshootResponse & { worker_stats?: Record<string, number> }>(
        `/admin/tds/fy-reconcile/troubleshoot/fix?${q.toString()}`,
        {
          method: "POST",
          body: JSON.stringify({ change_reason: reason.trim() }),
        },
      );
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["admin", "tds", "fy-reconcile"] });
      await refetch();
    },
  });

  if (!pujariId) {
    return (
      <PageContent>
        <p className="text-sm text-red-400">Missing pujari_id in URL.</p>
      </PageContent>
    );
  }

  return (
    <>
      <Header
        title="Reconcile troubleshoot"
        description="Compares tax card, tax diary, and bookings for one partner — no customer PII."
      />
      <PageContent className="space-y-6">
        <p className="text-sm text-ink-muted">
          <Link href="/console/tds/reconcile" className="text-brand-glow hover:underline">
            ← FY reconcile
          </Link>
          {" · "}
          <Link href={`/console/partners/${pujariId}`} className="text-brand-glow hover:underline">
            Partner
          </Link>
        </p>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-ink-muted hover:bg-surface-border/40"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-400">{(error as Error).message}</p>
        ) : data ? (
          <>
            <Card>
              <CardTitle className="text-base">Summary</CardTitle>
              <CardDescription className="mt-1 font-mono text-xs">
                Partner {pujariId.slice(0, 8)}… · FY {data.fy_start} → {data.fy_end_exclusive}
              </CardDescription>
              <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-ink-muted">
                {data.messages.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap gap-2">
                {data.tax.green ? (
                  <Badge tone="success">Tax green</Badge>
                ) : (
                  <Badge tone="error">Tax: {data.tax.status}</Badge>
                )}
                {data.gross.informational_only ? (
                  <Badge tone="warning">Gross: expected v3</Badge>
                ) : data.gross.status === "match" ? (
                  <Badge tone="success">Gross match</Badge>
                ) : (
                  <Badge tone="error">Gross: {data.gross.status}</Badge>
                )}
              </div>
            </Card>

            <div className="grid gap-4 md:grid-cols-2">
              <Card>
                <CardTitle className="text-base">Tax (TDS)</CardTitle>
                <dl className="mt-3 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-ink-muted">Yearly card</dt>
                    <dd>₹{data.tax.card_tds_accrued_inr}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-ink-muted">Diary net</dt>
                    <dd>₹{data.tax.ledger_tds_net_inr}</dd>
                  </div>
                  <div className="flex justify-between font-medium">
                    <dt>Drift</dt>
                    <dd>₹{data.tax.drift_inr}</dd>
                  </div>
                </dl>
              </Card>
              <Card>
                <CardTitle className="text-base">Business (gross)</CardTitle>
                <dl className="mt-3 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-ink-muted">Yearly card (turnover)</dt>
                    <dd>₹{data.gross.card_gross_facilitation_inr}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-ink-muted">Diary (tax base)</dt>
                    <dd>₹{data.gross.ledger_taxable_base_net_inr}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-ink-muted">From accepts (bookings)</dt>
                    <dd>₹{data.gross.turnover_at_accept_from_bookings_inr}</dd>
                  </div>
                  <div className="flex justify-between font-medium">
                    <dt>Drift</dt>
                    <dd>₹{data.gross.drift_inr}</dd>
                  </div>
                </dl>
              </Card>
            </div>

            {data.booking_findings.length > 0 && (
              <Card>
                <CardTitle className="text-base">Booking issues (sample)</CardTitle>
                <CardDescription>Booking IDs only — open in Bookings for full detail.</CardDescription>
                <ul className="mt-3 space-y-2 text-sm">
                  {data.booking_findings.map((f) => (
                    <li key={f.booking_id} className="rounded border border-surface-border/60 px-3 py-2">
                      <Link
                        href={`/console/bookings/${f.booking_id}`}
                        className="font-mono text-xs text-brand-glow hover:underline"
                      >
                        {f.booking_id.slice(0, 8)}…
                      </Link>
                      <span className="text-ink-muted"> — {f.issue_code}</span>
                      {f.last_error && (
                        <p className="mt-1 text-xs text-red-300/90">{f.last_error}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {data.safe_fix_available && (
              <Card>
                <CardTitle className="text-base">Safe fix</CardTitle>
                <CardDescription>
                  Re-queues accrual for collected bookings missing diary lines (max 25). Does not
                  edit yearly card totals directly. Requires admin role.
                </CardDescription>
                <label className="mt-4 block text-sm">
                  Change reason (audit)
                  <Input
                    className="mt-1"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. Re-run accrual after operative PAN"
                    maxLength={500}
                  />
                </label>
                <Button
                  className="mt-3"
                  disabled={fixMutation.isPending || reason.trim().length < 3}
                  onClick={() => fixMutation.mutate()}
                >
                  {fixMutation.isPending ? "Running…" : "Run safe fix"}
                </Button>
                {fixMutation.isError && (
                  <p className="mt-2 text-sm text-red-400">{(fixMutation.error as Error).message}</p>
                )}
                {fixMutation.isSuccess && (
                  <p className="mt-2 text-sm text-ink-muted">
                    Done — review tax status above. If still manual, contact engineering.
                  </p>
                )}
              </Card>
            )}

            {data.action_required && !data.safe_fix_available && (
              <p className="text-sm text-amber-200/90">
                Manual intervention required — safe fix cannot resolve this automatically.
              </p>
            )}
          </>
        ) : null}
      </PageContent>
    </>
  );
}
