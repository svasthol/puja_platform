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
export type TdsFacilitation = z.infer<typeof tdsFacilitationSchema>;
export type UserRoles = z.infer<typeof userRolesSchema>;
export type CredentialProvision = z.infer<typeof credentialProvisionSchema>;
