import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { fetchBookings } from "@/lib/api/bookings";
import { fetchRefunds } from "@/lib/api/refunds-queue";

const OPS_QUEUES: {
  id: string;
  label: string;
  status?: string;
  booking_class?: string;
  refunds?: "pending" | "processing";
}[] = [
  { id: "payment_pending", label: "Payment pending", status: "payment_pending" },
  { id: "requested", label: "Requested", status: "requested" },
  { id: "confirmed", label: "Confirmed", status: "confirmed" },
  { id: "in_progress", label: "In progress", status: "in_progress" },
  { id: "failed_no_pujari", label: "Failed no pujari", status: "failed_no_pujari" },
  { id: "cancelled", label: "Cancelled", status: "cancelled" },
  { id: "disputed", label: "Disputed", status: "disputed" },
  { id: "instant", label: "Instant", booking_class: "instant" },
  { id: "advance", label: "Advance", booking_class: "advance" },
  { id: "refunds_pending", label: "Refunds pending", refunds: "pending" },
  { id: "refunds_processing", label: "Refunds processing", refunds: "processing" },
];

const STATUS_TONE: Record<string, "success" | "warning" | "default"> = {
  confirmed: "success",
  completed: "success",
  requested: "warning",
  payment_pending: "warning",
  in_progress: "default",
  cancelled: "default",
  disputed: "warning",
  failed_no_pujari: "warning",
};

export function BookingsOpsInner() {
  const [activeQueue, setActiveQueue] = useState<string>("payment_pending");

  const queue = useMemo(
    () => OPS_QUEUES.find((q) => q.id === activeQueue) ?? OPS_QUEUES[0],
    [activeQueue],
  );

  const bookingsQuery = useQuery({
    queryKey: ["admin", "bookings", "ops", queue.id],
    queryFn: () =>
      fetchBookings({
        status: queue.status,
        booking_class: queue.booking_class,
        limit: 50,
      }),
    enabled: !queue.refunds,
  });

  const refundsQuery = useQuery({
    queryKey: ["admin", "refunds", queue.refunds],
    queryFn: () => fetchRefunds(queue.refunds!),
    enabled: Boolean(queue.refunds),
  });

  const loading = queue.refunds ? refundsQuery.isLoading : bookingsQuery.isLoading;
  const error = queue.refunds ? refundsQuery.error : bookingsQuery.error;

  return (
    <>
      <Header
        title="Bookings ops"
        description="Queue tabs for daily monitoring — PII reads are audited."
      />
      <PageContent>
        <div className="flex flex-wrap gap-2">
          {OPS_QUEUES.map((q) => (
            <Button
              key={q.id}
              type="button"
              variant={activeQueue === q.id ? "default" : "secondary"}
              className="text-xs"
              onClick={() => setActiveQueue(q.id)}
            >
              {q.label}
            </Button>
          ))}
        </div>

        <Card className="mt-6">
          <CardTitle className="text-base">{queue.label}</CardTitle>
          <CardDescription className="mt-1">
            {queue.refunds
              ? "Refund queue (platform money)."
              : "Latest bookings matching this queue."}
          </CardDescription>
          {loading ? (
            <p className="mt-3 text-sm text-ink-muted">Loading…</p>
          ) : error ? (
            <p className="mt-3 text-sm text-red-400">{(error as Error).message}</p>
          ) : queue.refunds ? (
            <RefundTable rows={refundsQuery.data?.refunds ?? []} />
          ) : (
            <BookingTable rows={bookingsQuery.data?.bookings ?? []} />
          )}
        </Card>
      </PageContent>
    </>
  );
}

function BookingTable({
  rows,
}: {
  rows: Awaited<ReturnType<typeof fetchBookings>>["bookings"];
}) {
  if (!rows.length) {
    return <p className="mt-3 text-sm text-ink-muted">No bookings in this queue.</p>;
  }
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-surface-border text-ink-faint">
            <th className="py-2 pr-3">Status</th>
            <th className="py-2 pr-3">Customer</th>
            <th className="py-2 pr-3">Puja</th>
            <th className="py-2 pr-3">Schedule</th>
            <th className="py-2 pr-3">Pujari</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => (
            <tr key={b.id} className="border-b border-surface-border/60">
              <td className="py-2.5 pr-3">
                <Badge tone={STATUS_TONE[b.status] ?? "default"}>{b.status}</Badge>
              </td>
              <td className="py-2.5 pr-3">
                <div className="font-medium">{b.customer_name}</div>
                <div className="font-mono text-xs text-ink-muted">{b.customer_phone}</div>
              </td>
              <td className="py-2.5 pr-3">{b.puja_name}</td>
              <td className="py-2.5 pr-3 whitespace-nowrap">
                {b.scheduled_date} {b.scheduled_time.slice(0, 5)}
              </td>
              <td className="py-2.5 pr-3 text-ink-muted">{b.assigned_pujari_name ?? "—"}</td>
              <td className="py-2.5 text-right">
                <Link href={`/console/bookings/${b.id}`}>
                  <Button type="button" variant="secondary" className="text-xs">
                    360° →
                  </Button>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RefundTable({
  rows,
}: {
  rows: Awaited<ReturnType<typeof fetchRefunds>>["refunds"];
}) {
  if (!rows.length) {
    return <p className="mt-3 text-sm text-ink-muted">Queue is empty.</p>;
  }
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-surface-border text-ink-faint">
            <th className="py-2 pr-3">Booking</th>
            <th className="py-2 pr-3">Customer</th>
            <th className="py-2 pr-3">Amount</th>
            <th className="py-2 pr-3">Reason</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/50">
              <td className="py-2 pr-3 font-mono text-xs">{r.booking_id.slice(0, 8)}…</td>
              <td className="py-2.5 pr-3">{r.customer_name}</td>
              <td className="py-2.5 pr-3">₹{r.amount}</td>
              <td className="py-2.5 pr-3">{r.reason}</td>
              <td className="py-2.5 text-right">
                <Link href={`/console/bookings/${r.booking_id}`}>
                  <Button type="button" variant="secondary" className="text-xs">
                    360° →
                  </Button>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
