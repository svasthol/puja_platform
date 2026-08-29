import { z } from "zod";

export const contentKindSchema = z.enum([
  "inclusion",
  "exclusion",
  "insight",
  "requirement",
  "faq_q",
  "faq_a",
]);

export const pujaCategorySchema = z.object({
  id: z.number(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable().optional(),
  display_order: z.number(),
  is_active: z.boolean(),
  image_media_id: z.string().uuid().nullable().optional(),
});

export const pujaCategoryListSchema = z.object({
  categories: z.array(pujaCategorySchema),
});

export const pujaSchema = z.object({
  id: z.string().uuid(),
  category_id: z.number(),
  name: z.string(),
  slug: z.string(),
  tagline: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  duration_minutes: z.number().nullable().optional(),
  default_price: z.string(),
  price_max: z.string().nullable().optional(),
  display_order: z.number(),
  is_active: z.boolean(),
  hero_media_id: z.string().uuid().nullable().optional(),
});

export const pujaListSchema = z.object({
  pujas: z.array(pujaSchema),
});

export const pujaImpactSchema = z.object({
  puja_id: z.string().uuid(),
  active_future_bookings: z.number(),
  active_holds_unscoped: z.number(),
  note: z.string().optional(),
});

export const catalogLocaleSchema = z.enum(["te", "en"]);

export const pujaI18nSchema = z.object({
  puja_id: z.string().uuid(),
  locale: catalogLocaleSchema,
  name: z.string(),
  tagline: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
});

export const contentItemSchema = z.object({
  id: z.string().uuid(),
  kind: contentKindSchema,
  position: z.number(),
  text: z.string(),
  is_active: z.boolean(),
});

export const contentListSchema = z.object({
  kind: contentKindSchema,
  items: z.array(contentItemSchema),
});

export const pujaAddonSchema = z.object({
  id: z.string().uuid(),
  puja_id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable().optional(),
  price: z.string(),
  display_order: z.number(),
  is_active: z.boolean(),
  image_media_id: z.string().uuid().nullable().optional(),
});

export const pujaAddonListSchema = z.object({
  addons: z.array(pujaAddonSchema),
});

export const mediaSchema = z.object({
  id: z.string().uuid(),
  entity_type: z.enum(["puja", "category", "gallery", "addon"]),
  entity_id: z.string().uuid(),
  s3_key: z.string(),
  alt_text: z.string().nullable().optional(),
  position: z.number(),
  upload_status: z.enum(["pending", "ready", "failed"]),
  is_active: z.boolean(),
  public_url: z.string().nullable().optional(),
  created_at: z.string(),
  confirmed_at: z.string().nullable().optional(),
});

export const mediaListSchema = z.object({
  items: z.array(mediaSchema),
});

export const mediaPresignSchema = z.object({
  media_id: z.string().uuid(),
  upload_url: z.string(),
  upload_method: z.literal("PUT"),
  upload_headers: z.record(z.string()),
  expires_in: z.number(),
  s3_key: z.string(),
});

export type PujaCategory = z.infer<typeof pujaCategorySchema>;
export type Puja = z.infer<typeof pujaSchema>;
export type PujaImpact = z.infer<typeof pujaImpactSchema>;
export type ContentKind = z.infer<typeof contentKindSchema>;
export type ContentItem = z.infer<typeof contentItemSchema>;
export type PujaAddon = z.infer<typeof pujaAddonSchema>;
export type MediaItem = z.infer<typeof mediaSchema>;

export const CONTENT_KIND_LABELS: Record<ContentKind, string> = {
  inclusion: "Inclusions",
  exclusion: "Exclusions",
  insight: "Insights",
  requirement: "Requirements",
  faq_q: "FAQ questions",
  faq_a: "FAQ answers",
};
