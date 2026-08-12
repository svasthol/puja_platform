"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { fetchFailedRefunds } from "@/lib/api/refunds";

export default function FailedRefundsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "refunds", "failed_permanent"],
    queryFn: () => fetchFailedRefunds(),
  });

  return (
    <>
      <Header
        title="Failed refunds"
        description="Permanent gateway failures — resolve manually or retry from Razorpay dashboard."
      />
      <PageContent>
        {isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-400">{(error as Error).message}</p>
        ) : (
          <Card>
            <CardTitle className="text-base">failed_permanent queue</CardTitle>
            <CardDescription className="mt-1">
              {data?.refunds.length ?? 0} item(s) need ops attention.
            </CardDescription>
            {data?.refunds.length === 0 ? (
              <p className="mt-4 text-sm text-ink-muted">Queue is empty.</p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-surface-border text-ink-faint">
                      <th className="py-2 pr-3">Booking</th>
                      <th className="py-2 pr-3">Customer</th>
                      <th className="py-2 pr-3">Amount</th>
                      <th className="py-2 pr-3">Reason</th>
                      <th className="py-2 pr-3">Attempts</th>
                      <th className="py-2">Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.refunds.map((r) => (
                      <tr key={r.id} className="border-b border-surface-border/50">
                        <td className="py-2 pr-3">
                          <Link
                            href={`/console/bookings/${r.booking_id}`}
                            className="font-mono text-xs text-brand-glow hover:underline"
                          >
                            {r.booking_id.slice(0, 8)}…
                          </Link>
                          <div className="text-xs text-ink-faint">{r.created_at.slice(0, 10)}</div>
                        </td>
                        <td className="py-2 pr-3">
                          {r.customer_name ?? "—"}
                          {r.customer_phone ? (
                            <div className="font-mono text-xs text-ink-muted">{r.customer_phone}</div>
                          ) : null}
                        </td>
                        <td className="py-2 pr-3">₹{r.amount}</td>
                        <td className="py-2 pr-3">
                          <Badge>{r.reason}</Badge>
                        </td>
                        <td className="py-2 pr-3">{r.attempt_count}</td>
                        <td className="py-2 max-w-xs truncate text-xs text-red-400">
                          {r.last_error ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-4">
              <Link href="/console/bookings">
                <Button type="button" variant="secondary">
                  Search bookings
                </Button>
              </Link>
            </div>
          </Card>
        )}
      </PageContent>
    </>
  );
}
