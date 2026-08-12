import { z } from "zod";

export const refundOverrideResponseSchema = z.object({
  refund_id: z.string().uuid(),
  payment_id: z.string().uuid(),
  booking_id: z.string().uuid(),
  amount: z.string(),
  status: z.string(),
});

export const refundQueueItemSchema = z.object({
  id: z.string().uuid(),
  booking_id: z.string().uuid(),
  payment_id: z.string().uuid(),
  amount: z.string(),
  status: z.string(),
  reason: z.string(),
  last_error: z.string().nullable().optional(),
  attempt_count: z.number(),
  created_at: z.string(),
  customer_phone: z.string().nullable().optional(),
  customer_name: z.string().nullable().optional(),
});

export const refundListSchema = z.object({
  refunds: z.array(refundQueueItemSchema),
  next_cursor: z.string().nullable().optional(),
});

export type RefundQueueItem = z.infer<typeof refundQueueItemSchema>;
