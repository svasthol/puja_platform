import { apiFetch } from "@/lib/api/client";
import { promoListSchema, promoSchema } from "@/lib/schemas/promos";

export async function fetchPromos(params?: { is_active?: boolean; cursor?: string }) {
  const sp = new URLSearchParams();
  if (params?.is_active !== undefined) sp.set("is_active", String(params.is_active));
  if (params?.cursor) sp.set("cursor", params.cursor);
  const q = sp.toString();
  return apiFetch(`/admin/promos${q ? `?${q}` : ""}`, { schema: promoListSchema });
}

export async function createPromo(body: {
  code: string;
  discount_pct: number;
  max_uses_per_user?: number;
  valid_from: string;
  valid_until: string;
  is_active?: boolean;
}) {
  return apiFetch("/admin/promos", {
    method: "POST",
    body: JSON.stringify(body),
    schema: promoSchema,
  });
}

export async function updatePromo(
  promoId: string,
  body: {
    discount_pct?: number;
    max_uses_per_user?: number;
    valid_from?: string;
    valid_until?: string;
    is_active?: boolean;
  },
) {
  return apiFetch(`/admin/promos/${promoId}`, {
    method: "PUT",
    body: JSON.stringify(body),
    schema: promoSchema,
  });
}
