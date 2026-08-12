import { apiFetch } from "@/lib/api/client";
import { refundListSchema, refundOverrideResponseSchema } from "@/lib/schemas/refunds";

export async function createRefundOverride(body: {
  booking_id?: string;
  payment_id?: string;
  amount: number;
  change_reason?: string;
}) {
  return apiFetch("/admin/refunds/override", {
    method: "POST",
    body: JSON.stringify(body),
    schema: refundOverrideResponseSchema,
  });
}

export async function fetchFailedRefunds(params?: { cursor?: string; limit?: number }) {
  const sp = new URLSearchParams({ status: "failed_permanent" });
  if (params?.cursor) sp.set("cursor", params.cursor);
  if (params?.limit) sp.set("limit", String(params.limit));
  return apiFetch(`/admin/refunds?${sp.toString()}`, { schema: refundListSchema });
}
