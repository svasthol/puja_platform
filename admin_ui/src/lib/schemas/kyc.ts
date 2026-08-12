import { z } from "zod";

import { verificationStatusSchema } from "@/lib/schemas/partners";

export const docStatusSchema = z.enum(["pending", "verified", "rejected"]);

export const kycPendingItemSchema = z.object({
  id: z.string().uuid(),
  pujari_id: z.string().uuid(),
  pujari_name: z.string(),
  pujari_phone: z.string(),
  pujari_verification_status: verificationStatusSchema,
  doc_type: z.string(),
  doc_type_label: z.string(),
  version: z.number(),
  uploaded_at: z.string(),
  view_url: z.string().nullable().optional(),
  view_url_expires_in: z.number().nullable().optional(),
});

export const kycPendingListSchema = z.object({
  items: z.array(kycPendingItemSchema),
  next_cursor: z.string().nullable().optional(),
  required_doc_types: z.array(z.string()),
});

export const kycReviewResponseSchema = z.object({
  document_id: z.string().uuid(),
  document_status: docStatusSchema,
  pujari_id: z.string().uuid(),
  pujari_verification_status: verificationStatusSchema,
  all_required_verified: z.boolean(),
});

export type KycPendingItem = z.infer<typeof kycPendingItemSchema>;
export type KycPendingList = z.infer<typeof kycPendingListSchema>;
export type KycReviewResponse = z.infer<typeof kycReviewResponseSchema>;
