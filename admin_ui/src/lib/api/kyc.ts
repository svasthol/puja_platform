import { apiFetch } from "@/lib/api/client";
import {
  kycPendingListSchema,
  kycReviewResponseSchema,
  type KycPendingList,
  type KycReviewResponse,
} from "@/lib/schemas/kyc";

export async function fetchPendingKyc(params?: {
  cursor?: string;
  limit?: number;
  pujari_id?: string;
}): Promise<KycPendingList> {
  const sp = new URLSearchParams();
  if (params?.cursor) sp.set("cursor", params.cursor);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.pujari_id) sp.set("pujari_id", params.pujari_id);
  const q = sp.toString();
  return apiFetch(`/admin/kyc/pending${q ? `?${q}` : ""}`, { schema: kycPendingListSchema });
}

export async function approveKycDocument(
  docId: string,
  input?: { change_reason?: string; note?: string },
): Promise<KycReviewResponse> {
  return apiFetch(`/admin/kyc/${docId}/approve`, {
    method: "POST",
    body: JSON.stringify(input ?? {}),
    schema: kycReviewResponseSchema,
  });
}

export async function rejectKycDocument(
  docId: string,
  input: { change_reason?: string; note?: string },
): Promise<KycReviewResponse> {
  return apiFetch(`/admin/kyc/${docId}/reject`, {
    method: "POST",
    body: JSON.stringify(input),
    schema: kycReviewResponseSchema,
  });
}
