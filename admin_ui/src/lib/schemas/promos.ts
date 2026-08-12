import { z } from "zod";

export const promoSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  discount_pct: z.number(),
  max_uses_per_user: z.number(),
  valid_from: z.string(),
  valid_until: z.string(),
  is_active: z.boolean(),
  redemption_count: z.number(),
});

export const promoListSchema = z.object({
  promos: z.array(promoSchema),
  next_cursor: z.string().nullable().optional(),
});

export type Promo = z.infer<typeof promoSchema>;
