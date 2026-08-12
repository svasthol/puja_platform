"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { fetchBookings } from "@/lib/api/bookings";

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

export default function BookingsPage() {
  const [phone, setPhone] = useState("");
  const [bookingId, setBookingId] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState<{
    phone?: string;
    booking_id?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
  }>({});

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["admin", "bookings", search],
    queryFn: () =>
      fetchBookings({
        phone: search.phone,
        booking_id: search.booking_id,
        status: search.status,
        date_from: search.date_from,
        date_to: search.date_to,
        limit: 50,
      }),
    enabled: Object.keys(search).length > 0,
  });

  return (
    <>
      <Header
        title="Bookings"
        description="Search customer bookings — PII reads are audited (Sprint 4C)."
      />
      <PageContent>
        <Card>
          <CardTitle className="text-base">Search</CardTitle>
          <CardDescription className="mt-1">
            Filter by phone, booking ID, status, or scheduled date range. Submit to load results.
          </CardDescription>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch({
                phone: phone.trim() || undefined,
                booking_id: bookingId.trim() || undefined,
                status: status || undefined,
                date_from: dateFrom || undefined,
                date_to: dateTo || undefined,
              });
            }}
          >
            <div>
              <Label htmlFor="bk-phone">Customer phone</Label>
              <Input
                id="bk-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+910000000001"
                className="mt-1.5"
              />
            </div>
            <div>
              <Label htmlFor="bk-id">Booking ID</Label>
              <Input
                id="bk-id"
                value={bookingId}
                onChange={(e) => setBookingId(e.target.value)}
                placeholder="UUID"
                className="mt-1.5 font-mono text-xs"
              />
            </div>
            <div>
              <Label htmlFor="bk-status">Status</Label>
              <Select
                id="bk-status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="mt-1.5"
              >
                <option value="">All</option>
                <option value="payment_pending">payment_pending</option>
                <option value="requested">requested</option>
                <option value="confirmed">confirmed</option>
                <option value="in_progress">in_progress</option>
                <option value="completed">completed</option>
                <option value="cancelled">cancelled</option>
                <option value="disputed">disputed</option>
                <option value="failed_no_pujari">failed_no_pujari</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="bk-from">Scheduled from</Label>
              <Input
                id="bk-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="mt-1.5"
              />
            </div>
            <div>
              <Label htmlFor="bk-to">Scheduled to</Label>
              <Input
                id="bk-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="mt-1.5"
              />
            </div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-1">
              <Button type="submit">Search</Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setPhone("");
                  setBookingId("");
                  setStatus("");
                  setDateFrom("");
                  setDateTo("");
                  setSearch({});
                }}
              >
                Clear
              </Button>
            </div>
          </form>
        </Card>

        <Card className="mt-6">
          <CardTitle className="text-base">Results</CardTitle>
          {Object.keys(search).length === 0 ? (
            <p className="mt-3 text-sm text-ink-muted">Enter filters and click Search.</p>
          ) : isLoading || isFetching ? (
            <p className="mt-3 text-sm text-ink-muted">Loading…</p>
          ) : !data?.bookings.length ? (
            <p className="mt-3 text-sm text-ink-muted">No bookings match.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-ink-faint">
                    <th className="py-2 pr-3">Status</th>
                    <th className="py-2 pr-3">Customer</th>
                    <th className="py-2 pr-3">Puja</th>
                    <th className="py-2 pr-3">Schedule</th>
                    <th className="py-2 pr-3">Pujari</th>
                    <th className="py-2 pr-3">Area</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody>
                  {data.bookings.map((b) => (
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
                      <td className="py-2.5 pr-3 text-ink-muted">
                        {b.assigned_pujari_name ?? "—"}
                      </td>
                      <td className="py-2.5 pr-3 text-ink-muted">{b.area_label ?? "—"}</td>
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
          )}
        </Card>
      </PageContent>
    </>
  );
}
