import { z } from "zod";

export const bookingSummarySchema = z.object({
  id: z.string().uuid(),
  status: z.string(),
  customer_phone: z.string(),
  customer_name: z.string(),
  puja_name: z.string(),
  scheduled_date: z.string(),
  scheduled_time: z.string(),
  total_amount: z.string(),
  amount_due_online: z.string(),
  payment_mode: z.string(),
  paid_at: z.string().nullable().optional(),
  assigned_pujari_name: z.string().nullable().optional(),
  area_label: z.string().nullable().optional(),
  created_at: z.string(),
});

export const bookingListSchema = z.object({
  bookings: z.array(bookingSummarySchema),
  next_cursor: z.string().nullable().optional(),
});

export const bookingCustomerSchema = z.object({
  user_id: z.string().uuid(),
  full_name: z.string(),
  phone: z.string(),
});

export const bookingAddressSchema = z.object({
  line1: z.string(),
  line2: z.string().nullable().optional(),
  city: z.string(),
  pincode: z.string().nullable().optional(),
  latitude: z.number().nullable().optional(),
  longitude: z.number().nullable().optional(),
  area_label: z.string().nullable().optional(),
});

export const bookingPujariSchema = z.object({
  id: z.string().uuid(),
  full_name: z.string(),
  phone: z.string(),
  rating_avg: z.string(),
  rating_count: z.number(),
});

export const bookingStatusEventSchema = z.object({
  status: z.string(),
  changed_at: z.string(),
  changed_by_user_id: z.string().uuid().nullable().optional(),
  changed_by_name: z.string().nullable().optional(),
});

export const bookingAssignmentSchema = z.object({
  id: z.string().uuid(),
  pujari_id: z.string().uuid(),
  pujari_name: z.string(),
  pujari_phone: z.string(),
  status: z.string(),
  offered_at: z.string(),
  expires_at: z.string(),
  responded_at: z.string().nullable().optional(),
});

export const bookingPaymentSchema = z.object({
  id: z.string().uuid(),
  amount: z.string(),
  status: z.string(),
  gateway_txn_id: z.string().nullable().optional(),
  idempotency_key: z.string(),
  created_at: z.string(),
});

export const bookingRefundSchema = z.object({
  id: z.string().uuid(),
  amount: z.string(),
  status: z.string(),
  reason: z.string(),
  gateway_refund_id: z.string().nullable().optional(),
  created_at: z.string(),
});

export const bookingDispatchSchema = z.object({
  dispatch_mode: z.string(),
  dispatch_starts_at: z.string().nullable().optional(),
  dispatch_deadline: z.string().nullable().optional(),
  intended_pujari_id: z.string().uuid().nullable().optional(),
});

export const bookingDetailSchema = z.object({
  id: z.string().uuid(),
  status: z.string(),
  puja_name: z.string(),
  scheduled_date: z.string(),
  scheduled_time: z.string(),
  duration_minutes: z.number(),
  payment_mode: z.string(),
  total_amount: z.string(),
  amount_due_online: z.string(),
  amount_due_offline: z.string(),
  balance_collected_at: z.string().nullable().optional(),
  paid_at: z.string().nullable().optional(),
  razorpay_order_id: z.string().nullable().optional(),
  cancelled_at: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  customer: bookingCustomerSchema,
  address: bookingAddressSchema,
  pujari: bookingPujariSchema.nullable().optional(),
  dispatch: bookingDispatchSchema,
  history: z.array(bookingStatusEventSchema),
  assignments: z.array(bookingAssignmentSchema),
  payments: z.array(bookingPaymentSchema),
  refunds: z.array(bookingRefundSchema),
  relationship_manager: z
    .object({
      name: z.string(),
      phone: z.string(),
    })
    .nullable()
    .optional(),
});

export type BookingSummary = z.infer<typeof bookingSummarySchema>;
export type BookingDetail = z.infer<typeof bookingDetailSchema>;
