import { z } from "zod";

export const adminLoginSchema = z.object({
  phone: z.string().min(8).max(15),
  code: z.string().min(6).max(8).regex(/^\d+$/, "Digits only"),
});

export const tokenPairSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string().optional(),
});

export const adminMeSchema = z.object({
  user_id: z.string().uuid(),
  phone: z.string(),
  roles: z.array(z.string()),
  is_admin: z.boolean(),
  is_support: z.boolean(),
});

export type AdminLoginInput = z.infer<typeof adminLoginSchema>;
export type TokenPair = z.infer<typeof tokenPairSchema>;
export type AdminMe = z.infer<typeof adminMeSchema>;
