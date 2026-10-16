"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";

type IntentRow = {
  intent_id: string;
  booking_id: string;
  pujari_id: string;
  status: string;
  park_reason: string | null;
  gross_amount: string;
  collected_at: string;
  attempt_count: number;
  last_error: string | null;
};

type ReadinessRow = {
  pujari_id: string;
  entity_type: string | null;
  pan_on_file: boolean;
  pan_status: string;
  parked_intents: number;
  pending_intents: number;
};

type BacklogResponse = {
  parked_count: number;
  pending_count: number;
  failed_count: number;
  intents: IntentRow[];
  pujari_readiness: ReadinessRow[];
};

function statusTone(status: string): "error" | "warning" | "default" {
  if (status === "failed") return "error";
  if (status === "parked") return "warning";
  return "default";
}

export default function TdsBacklogPage() {
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["admin", "tds", "compliance-backlog"],
    queryFn: () =>
      apiFetch<BacklogResponse>("/admin/tds/compliance-backlog?limit=100"),
    staleTime: 60_000,
  });

  return (
    <>
      <Header
        title="TDS accrual backlog"
        description="Parked, pending, and failed intents (max 100 rows). Worker drains on sweep — do not auto-refresh rapidly."
      />
      <PageContent>
        <div className="mb-4 flex flex-wrap items-center gap-3">
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
          <div className="space-y-6">
            <div className="flex flex-wrap gap-3 text-sm">
              <Badge tone="warning">parked {data?.parked_count}</Badge>
              <Badge tone="default">pending {data?.pending_count}</Badge>
              <Badge tone="error">failed {data?.failed_count}</Badge>
            </div>

            <Card>
              <CardTitle className="text-base">Intents</CardTitle>
              <CardDescription>Failed first, then parked, then pending.</CardDescription>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-ink-faint">
                      <th className="py-2 pr-3">Status</th>
                      <th className="py-2 pr-3">Booking</th>
                      <th className="py-2 pr-3">Gross</th>
                      <th className="py-2 pr-3">Park reason</th>
                      <th className="py-2 pr-3">Error</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.intents ?? []).map((row) => (
                      <tr key={row.intent_id} className="border-b border-surface-border/50">
                        <td className="py-2.5 pr-3">
                          <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-xs">{row.booking_id.slice(0, 8)}…</td>
                        <td className="py-2.5 pr-3">₹{row.gross_amount}</td>
                        <td className="py-2.5 pr-3 text-ink-muted">{row.park_reason ?? "—"}</td>
                        <td className="max-w-xs truncate py-2.5 pr-3 text-xs text-red-300/90">
                          {row.last_error ?? "—"}
                        </td>
                        <td className="py-2.5 text-right">
                          <Link
                            href={`/console/bookings/${row.booking_id}`}
                            className="text-brand-glow hover:underline text-xs"
                          >
                            Booking
                          </Link>
                          <span className="mx-1 text-ink-faint">·</span>
                          <Link
                            href={`/console/partners/${row.pujari_id}`}
                            className="text-brand-glow hover:underline text-xs"
                          >
                            Partner
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {(data?.intents?.length ?? 0) === 0 && (
                  <p className="mt-4 text-sm text-ink-muted">No open intents.</p>
                )}
              </div>
            </Card>

            <Card>
              <CardTitle className="text-base">Partner readiness</CardTitle>
              <CardDescription>
                Partners with parked/pending intents or missing entity / PAN on file.
              </CardDescription>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-ink-faint">
                      <th className="py-2 pr-3">Partner</th>
                      <th className="py-2 pr-3">Entity</th>
                      <th className="py-2 pr-3">PAN status</th>
                      <th className="py-2 pr-3">Parked</th>
                      <th className="py-2 pr-3">Pending</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.pujari_readiness ?? []).map((r) => (
                      <tr key={r.pujari_id} className="border-b border-surface-border/50">
                        <td className="py-2.5 pr-3">
                          <Link
                            href={`/console/partners/${r.pujari_id}`}
                            className="font-mono text-xs text-brand-glow hover:underline"
                          >
                            {r.pujari_id.slice(0, 8)}…
                          </Link>
                        </td>
                        <td className="py-2.5 pr-3">{r.entity_type ?? "—"}</td>
                        <td className="py-2.5 pr-3">{r.pan_status}</td>
                        <td className="py-2.5 pr-3">{r.parked_intents}</td>
                        <td className="py-2.5 pr-3">{r.pending_intents}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
      </PageContent>
    </>
  );
}
