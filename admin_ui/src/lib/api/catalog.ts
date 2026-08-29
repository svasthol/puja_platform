import { apiFetch, ApiError } from "@/lib/api/client";
import { getAccessToken, getApiBase } from "@/lib/auth/tokens";
import {
  contentListSchema,
  mediaListSchema,
  mediaPresignSchema,
  mediaSchema,
  pujaAddonListSchema,
  pujaAddonSchema,
  pujaCategoryListSchema,
  pujaCategorySchema,
  pujaImpactSchema,
  pujaI18nSchema,
  pujaListSchema,
  pujaSchema,
  type ContentKind,
  type Puja,
  type PujaAddon,
  type PujaCategory,
} from "@/lib/schemas/catalog";

// ---- Categories ------------------------------------------------------------
export async function fetchCategories() {
  return apiFetch("/admin/catalog/categories", { schema: pujaCategoryListSchema });
}

export async function createCategory(input: {
  name: string;
  description?: string;
  change_reason?: string;
}): Promise<PujaCategory> {
  return apiFetch("/admin/catalog/categories", {
    method: "POST",
    body: JSON.stringify(input),
    schema: pujaCategorySchema,
  });
}

export async function updateCategory(
  id: number,
  input: {
    name?: string;
    description?: string | null;
    is_active?: boolean;
    image_media_id?: string | null;
    change_reason?: string;
  },
): Promise<PujaCategory> {
  return apiFetch(`/admin/catalog/categories/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: pujaCategorySchema,
  });
}

// ---- Pujas -----------------------------------------------------------------
export async function fetchPujas(categoryId?: number) {
  const q = categoryId != null ? `?category_id=${categoryId}` : "";
  return apiFetch(`/admin/catalog/pujas${q}`, { schema: pujaListSchema });
}

export async function createPuja(input: {
  category_id: number;
  name: string;
  tagline?: string;
  description?: string;
  duration_minutes?: number;
  default_price: string;
  price_max?: string;
  change_reason?: string;
}): Promise<Puja> {
  return apiFetch("/admin/catalog/pujas", {
    method: "POST",
    body: JSON.stringify(input),
    schema: pujaSchema,
  });
}

export async function fetchPujaI18n(pujaId: string, locale: "te" | "en") {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/i18n/${locale}`, {
    schema: pujaI18nSchema,
  });
}

export async function upsertPujaI18n(
  pujaId: string,
  locale: "te" | "en",
  input: {
    name: string;
    tagline?: string | null;
    description?: string | null;
    change_reason?: string;
  },
) {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/i18n/${locale}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: pujaI18nSchema,
  });
}

export async function updatePuja(
  id: string,
  input: {
    name?: string;
    tagline?: string | null;
    description?: string | null;
    duration_minutes?: number | null;
    default_price?: string;
    price_max?: string | null;
    is_active?: boolean;
    hero_media_id?: string | null;
    change_reason?: string;
  },
): Promise<Puja> {
  return apiFetch(`/admin/catalog/pujas/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: pujaSchema,
  });
}

export async function fetchPujaImpact(pujaId: string) {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/impact`, { schema: pujaImpactSchema });
}

// ---- Content ---------------------------------------------------------------
export async function fetchContent(
  pujaId: string,
  kind: ContentKind,
  locale: "te" | "en" = "en",
) {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/content?kind=${kind}&locale=${locale}`, {
    schema: contentListSchema,
  });
}

export async function replaceContent(
  pujaId: string,
  input: {
    kind: ContentKind;
    items: { text: string; position: number }[];
    change_reason?: string;
  },
  locale: "te" | "en" = "en",
) {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/content?locale=${locale}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: contentListSchema,
  });
}

// ---- Addons ----------------------------------------------------------------
export async function fetchAddons(pujaId: string) {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/addons`, { schema: pujaAddonListSchema });
}

export async function createAddon(
  pujaId: string,
  input: { name: string; price: string; description?: string; change_reason?: string },
): Promise<PujaAddon> {
  return apiFetch(`/admin/catalog/pujas/${pujaId}/addons`, {
    method: "POST",
    body: JSON.stringify(input),
    schema: pujaAddonSchema,
  });
}

export async function reorderCategories(input: {
  ordered_ids: number[];
  change_reason?: string;
}) {
  return apiFetch("/admin/catalog/categories/reorder", {
    method: "PATCH",
    body: JSON.stringify(input),
    schema: pujaCategoryListSchema,
  });
}

export async function reorderPujas(input: {
  category_id: number;
  ordered_ids: string[];
  change_reason?: string;
}) {
  return apiFetch("/admin/catalog/pujas/reorder", {
    method: "PATCH",
    body: JSON.stringify(input),
    schema: pujaListSchema,
  });
}

export async function updateAddon(
  addonId: string,
  input: {
    name?: string;
    description?: string | null;
    price?: string;
    is_active?: boolean;
    image_media_id?: string | null;
    change_reason?: string;
  },
): Promise<PujaAddon> {
  return apiFetch(`/admin/catalog/addons/${addonId}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: pujaAddonSchema,
  });
}

// ---- Media -----------------------------------------------------------------
export async function fetchMedia(entityType: string, entityId: string) {
  return apiFetch(
    `/admin/catalog/media?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`,
    { schema: mediaListSchema },
  );
}

export async function presignMedia(input: {
  entity_type: "puja" | "category" | "gallery" | "addon";
  entity_id: string;
  content_type: string;
  content_length: number;
  alt_text?: string;
  change_reason?: string;
}) {
  return apiFetch("/admin/catalog/media/presign", {
    method: "POST",
    body: JSON.stringify(input),
    schema: mediaPresignSchema,
  });
}

export async function uploadMediaBody(mediaId: string, file: File): Promise<void> {
  const token = getAccessToken();
  const url = `${getApiBase()}/admin/catalog/media/${mediaId}/upload`;
  const res = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": file.type,
    },
    body: file,
  });
  if (!res.ok) {
    const body = await res.text();
    let detail = res.statusText;
    try {
      detail = String(JSON.parse(body).detail ?? detail);
    } catch {
      detail = body.slice(0, 200) || detail;
    }
    throw new ApiError(detail, res.status);
  }
}

export async function confirmMedia(mediaId: string) {
  return apiFetch(`/admin/catalog/media/${mediaId}/confirm`, {
    method: "POST",
    body: JSON.stringify({}),
    schema: mediaSchema,
  });
}

/** Presign → API proxy upload → confirm (Wave 2). */
export async function uploadCatalogImage(
  entityType: "puja" | "category" | "gallery" | "addon",
  entityId: string,
  file: File,
  altText?: string,
) {
  const presign = await presignMedia({
    entity_type: entityType,
    entity_id: entityId,
    content_type: file.type,
    content_length: file.size,
    alt_text: altText,
    change_reason: "admin-ui",
  });
  await uploadMediaBody(presign.media_id, file);
  return confirmMedia(presign.media_id);
}
