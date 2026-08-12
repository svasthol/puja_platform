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
export type UserRoles = z.infer<typeof userRolesSchema>;
export type CredentialProvision = z.infer<typeof credentialProvisionSchema>;
