import { z } from "zod";

export const serviceAreaSchema = z.object({
  id: z.number(),
  city: z.string(),
  zone_name: z.string(),
  pincode: z.string().nullable().optional(),
  is_active: z.boolean(),
  pujari_count: z.number(),
  active_booking_count: z.number(),
});

export const serviceAreaListSchema = z.object({
  areas: z.array(serviceAreaSchema),
  next_cursor: z.string().nullable().optional(),
});

export type ServiceArea = z.infer<typeof serviceAreaSchema>;
export type ServiceAreaList = z.infer<typeof serviceAreaListSchema>;
