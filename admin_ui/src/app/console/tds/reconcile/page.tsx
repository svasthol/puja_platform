"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";

type ReconcileRow = {
  pujari_id: string;
  fy_start: string;
  kind: "gross_facilitation" | "tds_accrued";
  accumulator_gross: string;
  ledger_net: string;
  drift: string;
};

type ReconcileResponse = {
  green: boolean;
  rows: ReconcileRow[];
};

export default function TdsReconcilePage() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["admin", "tds", "fy-reconcile"],
    queryFn: () => apiFetch<ReconcileResponse>("/admin/tds/fy-reconcile"),
    staleTime: 60_000,
  });

  return (
    <>
      <Header
        title="FY ledger reconcile"
        description="Tax-year accumulator vs facilitation ledger net. Drift rows only — green means no mismatch returned."
      />
      <PageContent>
        <div className="mb-4">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-lg border border-surface-border px-3 py-1.5 text-sm text-ink-muted hover:bg-surface-border/40"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <p className="mb-4 text-sm text-ink-muted">
          <Link href="/console/tds" className="text-brand-glow hover:underline">
            ← TDS hub
          </Link>
        </p>
        {isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-400">{(error as Error).message}</p>
        ) : (
          <Card>
            <div className="flex items-center gap-3">
              <CardTitle className="text-base">Status</CardTitle>
              {data?.green ? (
                <Badge tone="success">green</Badge>
              ) : (
                <Badge tone="error">{data?.rows.length ?? 0} drift row(s)</Badge>
              )}
            </div>
            <CardDescription className="mt-2">
              Authoritative check:{" "}
              <code className="text-xs">python scripts/check_tds_readiness.py --strict</code>
            </CardDescription>
            {!data?.green && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-ink-faint">
                      <th className="py-2 pr-3">Kind</th>
                      <th className="py-2 pr-3">FY start</th>
                      <th className="py-2 pr-3">Partner</th>
                      <th className="py-2 pr-3">Accumulator</th>
                      <th className="py-2 pr-3">Ledger net</th>
                    <th className="py-2 pr-3">Drift</th>
                    <th className="py-2" />
                  </tr>
                  </thead>
                  <tbody>
                    {(data?.rows ?? []).map((r) => (
                      <tr
                        key={`${r.kind}-${r.pujari_id}-${r.fy_start}`}
                        className="border-b border-surface-border/50"
                      >
                        <td className="py-2.5 pr-3 text-xs text-ink-muted">{r.kind}</td>
                        <td className="py-2.5 pr-3">{r.fy_start}</td>
                        <td className="py-2.5 pr-3">
                          <Link
                            href={`/console/partners/${r.pujari_id}`}
                            className="font-mono text-xs text-brand-glow hover:underline"
                          >
                            {r.pujari_id.slice(0, 8)}…
                          </Link>
                        </td>
                        <td className="py-2.5 pr-3">₹{r.accumulator_gross}</td>
                        <td className="py-2.5 pr-3">₹{r.ledger_net}</td>
                        <td className="py-2.5 pr-3 font-medium text-amber-200">₹{r.drift}</td>
                        <td className="py-2.5 text-right">
                          <Link
                            href={`/console/tds/reconcile/troubleshoot?pujari_id=${r.pujari_id}&fy_start=${r.fy_start}`}
                            className="text-brand-glow hover:underline text-xs"
                          >
                            Troubleshoot
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {data?.green && (
              <p className="mt-4 text-sm text-ink-muted">No accumulator vs ledger gross drift in this view.</p>
            )}
          </Card>
        )}
      </PageContent>
    </>
  );
}
