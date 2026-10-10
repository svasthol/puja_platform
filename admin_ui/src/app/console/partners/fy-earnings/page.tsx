"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";

type FyRow = {
  pujari_id: string;
  full_name: string;
  entity_type: string | null;
  pan_on_file: boolean;
  collections_count: number;
  fy_collected_gross_inr: string;
  fy_gross_facilitation_inr: string;
  fy_ledger_gross_inr: string;
  tds_accrued_inr: string;
  fy_pan_gate_level: string;
  pan_operative?: boolean;
  pan_status?: string | null;
};

type FyResponse = {
  fy_start: string;
  fy_end_exclusive: string;
  pujaris: FyRow[];
};

export default function PartnerFyEarningsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "pujaris", "fy-earnings"],
    queryFn: () => apiFetch<FyResponse>("/admin/pujaris/fy-earnings?limit=100"),
    staleTime: 60_000,
  });

  return (
    <>
      <Header
        title="Partner FY earnings"
        description="Puja value collected on platform per pujari (Indian FY). Gate uses operative PAN, same as partner app."
      />
      <PageContent>
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
            <CardTitle className="text-base">FY {data?.fy_start} → {data?.fy_end_exclusive}</CardTitle>
            <CardDescription className="mt-1">
              Sorted by collected gross. Ledger columns populate when TDS accrual is on.
            </CardDescription>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-ink-faint">
                    <th className="py-2 pr-3">Name</th>
                    <th className="py-2 pr-3">Collections</th>
                    <th className="py-2 pr-3">FY collected</th>
                    <th className="py-2 pr-3">FY facilitation</th>
                    <th className="py-2 pr-3">Gate</th>
                    <th className="py-2 pr-3">PAN (operative)</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {(data?.pujaris ?? []).map((r) => (
                    <tr key={r.pujari_id} className="border-b border-surface-border/50">
                      <td className="py-2.5 pr-3 font-medium">{r.full_name}</td>
                      <td className="py-2.5 pr-3">{r.collections_count}</td>
                      <td className="py-2.5 pr-3">₹{r.fy_collected_gross_inr}</td>
                      <td className="py-2.5 pr-3">₹{r.fy_gross_facilitation_inr}</td>
                      <td className="py-2.5 pr-3">
                        {r.fy_pan_gate_level === "block" ? (
                          <Badge tone="error">block</Badge>
                        ) : r.fy_pan_gate_level === "warn" ? (
                          <Badge tone="warning">warn</Badge>
                        ) : (
                          <span className="text-ink-faint">ok</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        {r.pan_operative ? "operative" : r.pan_on_file ? r.pan_status ?? "on file" : "no"}
                      </td>
                      <td className="py-2.5 text-right">
                        <Link
                          href={`/console/partners/${r.pujari_id}`}
                          className="text-brand-glow hover:underline text-xs"
                        >
                          Partner →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </PageContent>
    </>
  );
}
