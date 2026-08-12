"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { use, useState } from "react";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { fetchBookingDetail, fetchBookingMoney, reassignBooking, disputeBooking } from "@/lib/api/bookings";
import { createRefundOverride } from "@/lib/api/refunds";
import { canDisputeBooking, canReassignBooking, canRefundOverride } from "@/lib/auth/roles";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-surface-border/50 py-2 sm:grid-cols-[140px_1fr]">
      <dt className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  );
}

export default function BookingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { data: me } = useAdminMe();
  const canReassign = canReassignBooking(me);
  const canRefund = canRefundOverride(me);
  const canDispute = canDisputeBooking(me);

  const [newPujariId, setNewPujariId] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [disputeReason, setDisputeReason] = useState("");
  const [disputeType, setDisputeType] = useState<"service" | "offline_non_payment">("service");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "booking", id],
    queryFn: () => fetchBookingDetail(id),
  });

  const { data: money } = useQuery({
    queryKey: ["admin", "booking", id, "money"],
    queryFn: () => fetchBookingMoney(id),
    enabled: Boolean(id),
  });

  const reassignMutation = useMutation({
    mutationFn: () =>
      reassignBooking(id, {
        new_pujari_id: newPujariId.trim(),
        change_reason: reassignReason.trim() || undefined,
      }),
    onSuccess: async () => {
      setActionMessage("Pujari reassigned — booking refreshed.");
      setNewPujariId("");
      setReassignReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "booking", id] });
    },
    onError: (err: Error) => setActionMessage(err.message),
  });

  const refundMutation = useMutation({
    mutationFn: () =>
      createRefundOverride({
        booking_id: id,
        amount: Number(refundAmount),
        change_reason: refundReason.trim() || undefined,
      }),
    onSuccess: async () => {
      setActionMessage("Refund queued — worker will process via Razorpay.");
      setRefundAmount("");
      setRefundReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "booking", id] });
    },
    onError: (err: Error) => setActionMessage(err.message),
  });

  const disputeMutation = useMutation({
    mutationFn: () =>
      disputeBooking(id, {
        change_reason: disputeReason.trim(),
        dispute_type: disputeType,
      }),
    onSuccess: async (resp: { offline_balance_note?: string | null }) => {
      setActionMessage(
        resp.offline_balance_note
          ? `Booking marked disputed. ${resp.offline_balance_note}`
          : "Booking marked disputed.",
      );
      setDisputeReason("");
      await qc.invalidateQueries({ queryKey: ["admin", "booking", id] });
    },
    onError: (err: Error) => setActionMessage(err.message),
  });

  const terminalStatuses = new Set([
    "in_progress",
    "completed",
    "cancelled",
    "disputed",
    "failed_no_pujari",
    "abandoned",
  ]);
  const showReassign =
    canReassign && data?.pujari && data.status && !terminalStatuses.has(data.status);
  const showDispute = canDispute && data?.status === "in_progress";

  return (
    <>
      <Header
        title="Booking detail"
        description="360° ops view — assignments, payments, dispatch, history."
      />
      <PageContent>
        <div className="mb-4">
          <Link href="/console/bookings">
            <Button type="button" variant="secondary">
              ← Back to search
            </Button>
          </Link>
        </div>

        {actionMessage ? (
          <p className="mb-4 rounded-lg border border-surface-border bg-surface-raised/80 px-3 py-2 text-sm text-ink-muted">
            {actionMessage}
          </p>
        ) : null}

        {isLoading ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-400">{(error as Error).message}</p>
        ) : data ? (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardTitle className="text-base">Summary</CardTitle>
              <dl className="mt-3">
                <Row label="ID">
                  <span className="font-mono text-xs">{data.id}</span>
                </Row>
                <Row label="Status">
                  <Badge>{data.status}</Badge>
                </Row>
                <Row label="Puja">{data.puja_name}</Row>
                <Row label="Schedule">
                  {data.scheduled_date} {data.scheduled_time.slice(0, 5)} ({data.duration_minutes}
                  min)
                </Row>
                <Row label="Payment">
                  {data.payment_mode} · ₹{data.total_amount} (online ₹{data.amount_due_online})
                </Row>
                <Row label="Customer">
                  {data.customer.full_name}
                  <span className="ml-2 font-mono text-xs text-ink-muted">
                    {data.customer.phone}
                  </span>
                </Row>
                <Row label="Address">
                  {data.address.line1}, {data.address.city}
                  {data.address.area_label ? ` · ${data.address.area_label}` : ""}
                </Row>
                <Row label="Pujari">
                  {data.pujari
                    ? `${data.pujari.full_name} (${data.pujari.phone})`
                    : "— unassigned —"}
                </Row>
                {data.relationship_manager ? (
                  <Row label="RM">
                    {data.relationship_manager.name} · {data.relationship_manager.phone}
                  </Row>
                ) : null}
              </dl>
            </Card>

            <Card>
              <CardTitle className="text-base">Dispatch</CardTitle>
              <CardDescription className="mt-1">Launch broadcast windows (§21.6)</CardDescription>
              <dl className="mt-3">
                <Row label="Mode">{data.dispatch.dispatch_mode}</Row>
                <Row label="Starts">
                  {data.dispatch.dispatch_starts_at
                    ? new Date(data.dispatch.dispatch_starts_at).toLocaleString()
                    : "—"}
                </Row>
                <Row label="Deadline">
                  {data.dispatch.dispatch_deadline
                    ? new Date(data.dispatch.dispatch_deadline).toLocaleString()
                    : "—"}
                </Row>
              </dl>

              {showReassign ? (
                <div className="mt-4 space-y-3 border-t border-surface-border pt-4">
                  <p className="text-sm font-medium text-ink">Manual reassign</p>
                  <div>
                    <Label htmlFor="new-pujari">New pujari ID</Label>
                    <Input
                      id="new-pujari"
                      className="mt-1 font-mono text-xs"
                      placeholder="UUID from Partners directory"
                      value={newPujariId}
                      onChange={(e) => setNewPujariId(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="reassign-reason">Reason (audited)</Label>
                    <Textarea
                      id="reassign-reason"
                      className="mt-1"
                      rows={2}
                      value={reassignReason}
                      onChange={(e) => setReassignReason(e.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={!newPujariId.trim() || reassignMutation.isPending}
                    onClick={() => reassignMutation.mutate()}
                  >
                    {reassignMutation.isPending ? "Reassigning…" : "Reassign pujari"}
                  </Button>
                  <p className="text-xs text-ink-faint">
                    Clears current assignment, revokes old offer, assigns new pujari in one
                    transaction.
                  </p>
                </div>
              ) : (
                <p className="mt-4 text-xs text-ink-faint">
                  {canReassign
                    ? "Reassign unavailable for this booking state."
                    : "Reassign requires support or admin role."}
                </p>
              )}
            </Card>

            <Card className="lg:col-span-2">
              <CardTitle className="text-base">Assignments</CardTitle>
              {data.assignments.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">No offers yet.</p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-surface-border text-ink-faint">
                        <th className="py-2 pr-3">Pujari</th>
                        <th className="py-2 pr-3">Status</th>
                        <th className="py-2 pr-3">Offered</th>
                        <th className="py-2 pr-3">Expires</th>
                        <th className="py-2">Responded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.assignments.map((a) => (
                        <tr key={a.id} className="border-b border-surface-border/50">
                          <td className="py-2 pr-3">
                            {a.pujari_name}
                            <div className="font-mono text-xs text-ink-muted">{a.pujari_phone}</div>
                            <div className="font-mono text-[10px] text-ink-faint">{a.pujari_id}</div>
                          </td>
                          <td className="py-2 pr-3">
                            <Badge>{a.status}</Badge>
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            {new Date(a.offered_at).toLocaleString()}
                          </td>
                          <td className="py-2 pr-3 whitespace-nowrap">
                            {new Date(a.expires_at).toLocaleString()}
                          </td>
                          <td className="py-2 whitespace-nowrap">
                            {a.responded_at ? new Date(a.responded_at).toLocaleString() : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card>
              <CardTitle className="text-base">Settlement (read-only)</CardTitle>
              <CardDescription className="mt-1">
                {money?.online_settlement_label ?? "Collected online — settlement pending"}
              </CardDescription>
              {money ? (
                <dl className="mt-3">
                  <Row label="Paid online">₹{money.total_paid_online}</Row>
                  <Row label="Refunded online">₹{money.total_refunded_online}</Row>
                  <Row label="Refundable">₹{money.refundable_remaining_online}</Row>
                  {money.offline_balance_note ? (
                    <Row label="Offline">{money.offline_balance_note}</Row>
                  ) : null}
                </dl>
              ) : (
                <p className="mt-3 text-sm text-ink-muted">Loading money view…</p>
              )}
            </Card>

            <Card>
              <CardTitle className="text-base">Payments</CardTitle>
              {data.payments.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">None</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {data.payments.map((p) => (
                    <li key={p.id} className="rounded border border-surface-border/60 p-2">
                      ₹{p.amount} · {p.status}
                      {p.gateway_txn_id ? (
                        <div className="font-mono text-xs text-ink-muted">{p.gateway_txn_id}</div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card>
              <CardTitle className="text-base">Refunds</CardTitle>
              {data.refunds.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">None</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {data.refunds.map((r) => (
                    <li key={r.id} className="rounded border border-surface-border/60 p-2">
                      ₹{r.amount} · {r.status} · {r.reason}
                    </li>
                  ))}
                </ul>
              )}

              {canRefund && data.payments.some((p) => p.status === "success") ? (
                <div className="mt-4 space-y-3 border-t border-surface-border pt-4">
                  <p className="text-sm font-medium text-ink">Refund override</p>
                  <div>
                    <Label htmlFor="refund-amount">Amount (₹)</Label>
                    <Input
                      id="refund-amount"
                      type="number"
                      min={1}
                      className="mt-1"
                      value={refundAmount}
                      onChange={(e) => setRefundAmount(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="refund-reason">Reason (audited)</Label>
                    <Textarea
                      id="refund-reason"
                      className="mt-1"
                      rows={2}
                      value={refundReason}
                      onChange={(e) => setRefundReason(e.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={!refundAmount || refundMutation.isPending}
                    onClick={() => refundMutation.mutate()}
                  >
                    {refundMutation.isPending ? "Queueing…" : "Queue refund"}
                  </Button>
                  <p className="text-xs text-ink-faint">
                    Inserts a pending refund row — Razorpay is called by the worker only.
                    {me?.is_support && !me?.is_admin
                      ? " Support role: per-action and daily caps apply."
                      : null}
                  </p>
                </div>
              ) : null}
            </Card>

            {showDispute ? (
              <Card>
                <CardTitle className="text-base">Dispute resolution</CardTitle>
                <CardDescription className="mt-1">
                  Marks an in_progress booking as disputed. Offline balance disputes do not
                  auto-refund via Razorpay.
                </CardDescription>
                <div className="mt-4 space-y-3">
                  <div>
                    <Label htmlFor="dispute-type">Type</Label>
                    <select
                      id="dispute-type"
                      className="mt-1 w-full rounded-md border border-surface-border bg-surface px-3 py-2 text-sm"
                      value={disputeType}
                      onChange={(e) =>
                        setDisputeType(e.target.value as "service" | "offline_non_payment")
                      }
                    >
                      <option value="service">Service issue</option>
                      <option value="offline_non_payment">Offline non-payment</option>
                    </select>
                  </div>
                  <div>
                    <Label htmlFor="dispute-reason">Reason (audited)</Label>
                    <Textarea
                      id="dispute-reason"
                      className="mt-1"
                      rows={2}
                      value={disputeReason}
                      onChange={(e) => setDisputeReason(e.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={disputeReason.trim().length < 3 || disputeMutation.isPending}
                    onClick={() => disputeMutation.mutate()}
                  >
                    {disputeMutation.isPending ? "Opening dispute…" : "Mark disputed"}
                  </Button>
                </div>
              </Card>
            ) : null}

            <Card className="lg:col-span-2">
              <CardTitle className="text-base">Status history</CardTitle>
              {data.history.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">No history rows.</p>
              ) : (
                <ol className="mt-3 space-y-2 text-sm">
                  {data.history.map((h, i) => (
                    <li key={`${h.status}-${h.changed_at}-${i}`} className="flex gap-3">
                      <Badge>{h.status}</Badge>
                      <span>{new Date(h.changed_at).toLocaleString()}</span>
                      {h.changed_by_name ? (
                        <span className="text-ink-muted">by {h.changed_by_name}</span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        ) : null}
      </PageContent>
    </>
  );
}
