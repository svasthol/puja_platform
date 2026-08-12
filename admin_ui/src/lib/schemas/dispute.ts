import { z } from "zod";

export const disputeResponseSchema = z.object({
  booking_id: z.string().uuid(),
  previous_status: z.string(),
  status: z.string(),
  dispute_type: z.string(),
  disputed_at: z.string(),
  offline_balance_note: z.string().nullable().optional(),
});
