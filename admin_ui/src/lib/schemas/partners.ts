import { z } from "zod";

export const verificationStatusSchema = z.enum(["pending", "verified", "rejected"]);

export const pujariSummarySchema = z.object({
  id: z.string().uuid(),
  full_name: z.string(),
  phone: z.string(),
  verification_status: verificationStatusSchema,
  rating_avg: z.string(),
  rating_count: z.number(),
  years_experience: z.number().nullable().optional(),
  pricing_count: z.number(),
  created_at: z.string(),
});

export const pujariListSchema = z.object({
  pujaris: z.array(pujariSummarySchema),
  next_cursor: z.string().nullable().optional(),
});

export const pricingRowSchema = z.object({
  puja_id: z.string().uuid(),
  puja_name: z.string(),
  puja_slug: z.string(),
  default_price: z.string(),
  price_max: z.string().nullable().optional(),
  base_price: z.string().nullable().optional(),
});

export const pujariPricingSchema = z.object({
  pujari_id: z.string().uuid(),
  full_name: z.string(),
  phone: z.string(),
  verification_status: verificationStatusSchema,
  items: z.array(pricingRowSchema),
});

export type PujariSummary = z.infer<typeof pujariSummarySchema>;
export type PricingRow = z.infer<typeof pricingRowSchema>;
export type PujariPricing = z.infer<typeof pujariPricingSchema>;
