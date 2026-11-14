import { z } from "zod";

export const advanceAmountSchema = z.object({
  amount: z.union([z.string(), z.number()]),
  currency: z.string(),
  updated_at: z.string().nullable().optional(),
});

export const advanceUpdateSchema = z.object({
  amount: z.coerce.number().min(1).max(10000),
  change_reason: z.string().max(300).optional().nullable(),
});

export const bookingFeeSchema = z.object({
  amount: z.union([z.string(), z.number()]),
  currency: z.string(),
  label: z.string(),
  updated_at: z.string().nullable().optional(),
});

export const bookingFeeUpdateSchema = z.object({
  amount: z.coerce.number().min(1).max(10000),
  label: z.string().max(120).optional().nullable(),
  change_reason: z.string().max(300).optional().nullable(),
});

export const tdsFacilitationSchema = z.object({
  no_pan_rate_pct: z.union([z.string(), z.number()]),
  pan_entity_rate_pct: z.union([z.string(), z.number()]),
  individual_fy_threshold_inr: z.union([z.string(), z.number()]),
  fy_turnover_warn_inr: z.union([z.string(), z.number()]),
  fy_turnover_block_inr: z.union([z.string(), z.number()]),
  always_taxed_entity_types: z.array(z.string()),
  updated_at: z.string().nullable().optional(),
});

export const tdsFacilitationUpdateSchema = z.object({
  no_pan_rate_pct: z.coerce.number().min(0).max(100),
  pan_entity_rate_pct: z.coerce.number().min(0).max(100),
  individual_fy_threshold_inr: z.coerce.number().min(0).max(100_000_000),
  fy_turnover_warn_inr: z.coerce.number().min(0).max(100_000_000),
  fy_turnover_block_inr: z.coerce.number().min(0).max(100_000_000),
  always_taxed_entity_types: z.array(z.string()).min(1),
  change_reason: z.string().max(300).optional().nullable(),
});

export const userRolesSchema = z.object({
  user_id: z.string().uuid(),
  roles: z.array(z.string()),
});

export const roleAssignSchema = z.object({
  role: z.enum(["admin", "support"]),
  change_reason: z.string().max(300).optional().nullable(),
});

export const credentialProvisionSchema = z.object({
  user_id: z.string().uuid(),
  provisioning_uri: z.string(),
  secret: z.string(),
  note: z.string().optional(),
});

export type AdvanceAmount = z.infer<typeof advanceAmountSchema>;
export type BookingFee = z.infer<typeof bookingFeeSchema>;
export const dispatchPolicySchema = z.object({
  instant_lead_hours: z.number(),
  instant_dispatch_minutes: z.number(),
  advance_dispatch_start_hours: z.number(),
  advance_dispatch_fail_hours: z.number(),
  reoffer_cooldown_minutes: z.number(),
  dispatch_buffer_minutes: z.number(),
  immediate_dispatch_on_payment: z.boolean(),
  instant_offer_ttl_seconds: z.number(),
  advance_offer_ttl_hours: z.number(),
  max_live_advance_offers_per_pujari: z.number(),
  rm_escalation_hours_no_accept: z.number(),
  rm_escalation_t24_hours: z.number(),
  night_bookings_enabled: z.boolean(),
  reconfirm_quiet_hours_start: z.string(),
  reconfirm_quiet_hours_end: z.string(),
  updated_at: z.string().nullable().optional(),
});

export const dispatchPolicyUpdateSchema = z.object({
  instant_lead_hours: z.coerce.number().min(1).max(48),
  instant_dispatch_minutes: z.coerce.number().min(5).max(180),
  advance_dispatch_start_hours: z.coerce.number().min(1).max(48),
  advance_dispatch_fail_hours: z.coerce.number().min(1).max(24),
  reoffer_cooldown_minutes: z.coerce.number().min(0).max(240),
  dispatch_buffer_minutes: z.coerce.number().min(0).max(180),
  immediate_dispatch_on_payment: z.boolean(),
  instant_offer_ttl_seconds: z.coerce.number().min(30).max(900),
  advance_offer_ttl_hours: z.coerce.number().min(1).max(72),
  max_live_advance_offers_per_pujari: z.coerce.number().min(1).max(50),
  rm_escalation_hours_no_accept: z.coerce.number().min(1).max(72),
  rm_escalation_t24_hours: z.coerce.number().min(1).max(72),
  night_bookings_enabled: z.boolean(),
  reconfirm_quiet_hours_start: z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/),
  reconfirm_quiet_hours_end: z.string().regex(/^([01]?\d|2[0-3]):[0-5]\d$/),
  change_reason: z.string().max(300).optional().nullable(),
});

export type TdsFacilitation = z.infer<typeof tdsFacilitationSchema>;
export type DispatchPolicy = z.infer<typeof dispatchPolicySchema>;
export type UserRoles = z.infer<typeof userRolesSchema>;
export type CredentialProvision = z.infer<typeof credentialProvisionSchema>;
