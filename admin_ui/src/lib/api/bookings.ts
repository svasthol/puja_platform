import { apiFetch } from "@/lib/api/client";
import {
  bookingDetailSchema,
  bookingListSchema,
  type BookingDetail,
} from "@/lib/schemas/bookings";
import { bookingMoneySchema } from "@/lib/schemas/money";
import { bookingTdsSchema } from "@/lib/schemas/booking-tds";
import { disputeResponseSchema } from "@/lib/schemas/dispute";

export async function fetchBookings(params?: {
  phone?: string;
  booking_id?: string;
  status?: string;
  booking_class?: string;
  date_from?: string;
  date_to?: string;
  cursor?: string;
  limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.phone) sp.set("phone", params.phone);
  if (params?.booking_id) sp.set("booking_id", params.booking_id);
  if (params?.status) sp.set("status", params.status);
  if (params?.booking_class) sp.set("booking_class", params.booking_class);
  if (params?.date_from) sp.set("date_from", params.date_from);
  if (params?.date_to) sp.set("date_to", params.date_to);
  if (params?.cursor) sp.set("cursor", params.cursor);
  if (params?.limit) sp.set("limit", String(params.limit));
  const q = sp.toString();
  return apiFetch(`/admin/bookings${q ? `?${q}` : ""}`, { schema: bookingListSchema });
}

export async function fetchBookingDetail(bookingId: string): Promise<BookingDetail> {
  return apiFetch(`/admin/bookings/${bookingId}`, { schema: bookingDetailSchema });
}

export async function reassignBooking(
  bookingId: string,
  body: { new_pujari_id: string; change_reason?: string },
) {
  return apiFetch(`/admin/bookings/${bookingId}/reassign`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchBookingMoney(bookingId: string) {
  return apiFetch(`/admin/bookings/${bookingId}/money`, { schema: bookingMoneySchema });
}

export async function fetchBookingTds(bookingId: string) {
  return apiFetch(`/admin/bookings/${bookingId}/tds`, { schema: bookingTdsSchema });
}

export async function disputeBooking(
  bookingId: string,
  body: { change_reason: string; dispute_type?: "service" | "offline_non_payment" },
) {
  return apiFetch(`/admin/bookings/${bookingId}/dispute`, {
    method: "POST",
    body: JSON.stringify(body),
    schema: disputeResponseSchema,
  });
}
