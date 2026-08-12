import { z } from "zod";

export const relationshipManagerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  phone: z.string(),
  city: z.string().nullable().optional(),
  is_active: z.boolean(),
  is_default: z.boolean(),
});

export const relationshipManagerListSchema = z.object({
  items: z.array(relationshipManagerSchema),
  next_cursor: z.string().nullable().optional(),
});

export const defaultRmSchema = z.object({
  relationship_manager_id: z.string().uuid().nullable(),
  name: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
});

export type RelationshipManager = z.infer<typeof relationshipManagerSchema>;
export type RelationshipManagerList = z.infer<typeof relationshipManagerListSchema>;
