import { z } from "zod";

export const bookingTdsSchema = z.object({
  booking_id: z.string(),
  pujari_id: z.string().nullable(),
  accrual_enabled: z.boolean(),
  balance_collected_at: z.string().nullable(),
  balance_collected_amount_inr: z.string().nullable().optional(),
  accept_tds_snapshot_at: z.string().nullable(),
  tds_liability_inr: z.string().nullable().optional(),
  tds_taxable_base_inr: z.string().nullable().optional(),
  tds_rate_applied: z.string().nullable().optional(),
  tds_collected_online_inr: z.string().nullable().optional(),
  ledger_accrual_present: z.boolean(),
  ledger_fy_start: z.string().nullable(),
  ledger_taxable_base_inr: z.string().nullable().optional(),
  ledger_tds_amount_inr: z.string().nullable().optional(),
  accrual_intent_status: z.string().nullable(),
  accrual_intent_park_reason: z.string().nullable(),
  accrual_intent_last_error: z.string().nullable(),
  accrual_intent_attempt_count: z.number().nullable().optional(),
  ops_status: z.string(),
  hints: z.array(z.string()),
});

export type BookingTds = z.infer<typeof bookingTdsSchema>;
