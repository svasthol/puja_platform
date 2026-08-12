import { z } from "zod";

export const bookingMoneySchema = z.object({
  booking_id: z.string().uuid(),
  payment_mode: z.string(),
  total_amount: z.string(),
  amount_due_online: z.string(),
  amount_due_offline: z.string(),
  balance_collected_at: z.string().nullable().optional(),
  online_settlement_label: z.string(),
  offline_balance_note: z.string().nullable().optional(),
  total_paid_online: z.string(),
  total_refunded_online: z.string(),
  refundable_remaining_online: z.string(),
  payments: z.array(
    z.object({
      id: z.string().uuid(),
      amount: z.string(),
      status: z.string(),
      gateway_txn_id: z.string().nullable().optional(),
      created_at: z.string(),
      settlement_label: z.string(),
      split: z
        .object({
          platform_fee: z.string(),
          gst_amount: z.string(),
          net_pujari_amount: z.string(),
        })
        .nullable()
        .optional(),
    }),
  ),
  refunds: z.array(
    z.object({
      id: z.string().uuid(),
      payment_id: z.string().uuid(),
      amount: z.string(),
      status: z.string(),
      reason: z.string(),
      gateway_refund_id: z.string().nullable().optional(),
      created_at: z.string(),
    }),
  ),
});

export type BookingMoney = z.infer<typeof bookingMoneySchema>;
