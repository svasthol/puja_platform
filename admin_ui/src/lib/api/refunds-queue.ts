import { apiFetch } from "@/lib/api/client";

export async function fetchRefunds(status: string) {
  return apiFetch<{ refunds: Array<{
    id: string;
    booking_id: string;
    amount: string;
    reason: string;
    customer_name: string;
    customer_phone: string;
  }> }>(`/admin/refunds?status=${encodeURIComponent(status)}`);
}
