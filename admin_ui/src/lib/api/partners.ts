import { apiFetch } from "@/lib/api/client";
import {
  pujariListSchema,
  pujariPricingSchema,
  type PujariPricing,
} from "@/lib/schemas/partners";

export async function fetchPujaris(params?: {
  q?: string;
  verification_status?: string;
  cursor?: string;
  limit?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.verification_status) sp.set("verification_status", params.verification_status);
  if (params?.cursor) sp.set("cursor", params.cursor);
  if (params?.limit) sp.set("limit", String(params.limit));
  const q = sp.toString();
  return apiFetch(`/admin/pujaris${q ? `?${q}` : ""}`, { schema: pujariListSchema });
}

export async function fetchPujariPricing(pujariId: string): Promise<PujariPricing> {
  return apiFetch(`/admin/pujaris/${pujariId}/pricing`, { schema: pujariPricingSchema });
}

export async function replacePujariPricing(
  pujariId: string,
  input: {
    items: { puja_id: string; base_price: string }[];
    change_reason?: string;
  },
): Promise<PujariPricing> {
  return apiFetch(`/admin/pujaris/${pujariId}/pricing`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: pujariPricingSchema,
  });
}
