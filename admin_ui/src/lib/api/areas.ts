import { apiFetch } from "@/lib/api/client";
import {
  serviceAreaListSchema,
  serviceAreaSchema,
  type ServiceArea,
  type ServiceAreaList,
} from "@/lib/schemas/areas";

export async function fetchServiceAreas(params?: {
  city?: string;
  is_active?: boolean;
}): Promise<ServiceAreaList> {
  const sp = new URLSearchParams();
  if (params?.city) sp.set("city", params.city);
  if (params?.is_active !== undefined) sp.set("is_active", String(params.is_active));
  const q = sp.toString();
  return apiFetch(`/admin/service-areas${q ? `?${q}` : ""}`, {
    schema: serviceAreaListSchema,
  });
}

export async function createServiceArea(input: {
  city: string;
  zone_name: string;
  pincode?: string;
  is_active?: boolean;
}): Promise<ServiceArea> {
  return apiFetch("/admin/service-areas", {
    method: "POST",
    body: JSON.stringify(input),
    schema: serviceAreaSchema,
  });
}

export async function updateServiceArea(
  id: number,
  input: {
    city?: string;
    zone_name?: string;
    pincode?: string | null;
    is_active?: boolean;
    force_deactivate?: boolean;
    change_reason?: string;
  },
): Promise<ServiceArea> {
  return apiFetch(`/admin/service-areas/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: serviceAreaSchema,
  });
}
