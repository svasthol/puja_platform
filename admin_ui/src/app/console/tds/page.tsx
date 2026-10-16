"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api/client";

type BacklogSummary = {
  parked_count: number;
  pending_count: number;
  failed_count: number;
};

type ReconcileSummary = {
  green: boolean;
};

const LINKS = [
  {
    href: "/console/settings/tds",
    title: "Policy slabs",
    description:
      "FY threshold (₹5L), warn band, entity rates, G2 turnover warn/block. Changes apply to accrual and partner gates.",
  },
  {
    href: "/console/partners/fy-earnings",
    title: "Partner FY earnings",
    description:
      "Who collected how much this Indian FY; gate tier (ok / warn / block) uses operative PAN like the partner app.",
  },
  {
    href: "/console/tds/backlog",
    title: "Accrual backlog",
    description:
      "Parked, pending, or failed TDS accrual intents — fix PAN/entity or data; Celery retries on sweep.",
  },
  {
    href: "/console/tds/reconcile",
    title: "FY ledger reconcile",
    description:
      "Accumulator vs facilitation ledger drift. Use before month-end; run scripts/check_tds_readiness.py --strict for sign-off.",
  },
  {
    href: "/console/partners/kyc",
    title: "KYC & PAN review",
    description: "Setu verification and operative PAN — required before ₹5L FY facilitation block clears.",
  },
] as const;

export default function TdsHubPage() {
  const backlog = useQuery({
    queryKey: ["admin", "tds", "backlog-summary"],
    queryFn: () =>
      apiFetch<BacklogSummary>("/admin/tds/compliance-backlog?limit=1"),
    staleTime: 60_000,
  });

  const reconcile = useQuery({
    queryKey: ["admin", "tds", "reconcile-summary"],
    queryFn: () => apiFetch<ReconcileSummary>("/admin/tds/fy-reconcile"),
    staleTime: 60_000,
  });

  const needsAttention =
    (backlog.data?.failed_count ?? 0) > 0 ||
    (backlog.data?.parked_count ?? 0) > 0 ||
    reconcile.data?.green === false;

  return (
    <>
      <Header
        title="TDS hub"
        description="Compliance and facilitation ops — read-only views that do not block partner or customer apps."
      />
      <PageContent className="space-y-6">
        <Card>
          <CardTitle className="text-base">Health snapshot</CardTitle>
          <CardDescription className="mt-1">
            Refreshes at most once per minute. For CA handoff, always run server scripts too.
          </CardDescription>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-ink-muted">Accrual failed</dt>
              <dd className="text-lg font-semibold text-ink">
                {backlog.isLoading ? "…" : backlog.data?.failed_count ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">Accrual parked</dt>
              <dd className="text-lg font-semibold text-ink">
                {backlog.isLoading ? "…" : backlog.data?.parked_count ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">Accrual pending</dt>
              <dd className="text-lg font-semibold text-ink">
                {backlog.isLoading ? "…" : backlog.data?.pending_count ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-ink-muted">FY ledger</dt>
              <dd className="mt-0.5">
                {reconcile.isLoading ? (
                  "…"
                ) : reconcile.data?.green ? (
                  <Badge tone="success">green</Badge>
                ) : (
                  <Badge tone="error">drift</Badge>
                )}
              </dd>
            </div>
          </dl>
          {needsAttention && !backlog.isLoading && (
            <p className="mt-4 text-sm text-amber-200/90">
              Something needs ops attention — open backlog or reconcile below.
            </p>
          )}
        </Card>

        <div className="grid gap-4 md:grid-cols-2">
          {LINKS.map((item) => (
            <Link key={item.href} href={item.href} className="block">
              <Card className="h-full transition hover:border-brand/40">
                <CardTitle className="text-base">{item.title}</CardTitle>
                <CardDescription className="mt-2">{item.description}</CardDescription>
                <p className="mt-3 text-xs text-brand-glow">Open →</p>
              </Card>
            </Link>
          ))}
        </div>

        <Card>
          <CardTitle className="text-base">Month-end scripts (host)</CardTitle>
          <CardDescription className="mt-1 font-mono text-xs">
            python scripts/check_tds_readiness.py --strict
            <br />
            python scripts/export_tds_26q.py --month=YYYY-MM
          </CardDescription>
        </Card>
      </PageContent>
    </>
  );
}
