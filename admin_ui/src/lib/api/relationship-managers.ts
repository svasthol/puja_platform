import { apiFetch } from "@/lib/api/client";
import {
  defaultRmSchema,
  relationshipManagerListSchema,
  relationshipManagerSchema,
  type RelationshipManager,
  type RelationshipManagerList,
} from "@/lib/schemas/relationship-managers";

export async function fetchRelationshipManagers(): Promise<RelationshipManagerList> {
  return apiFetch("/admin/relationship-managers", {
    schema: relationshipManagerListSchema,
  });
}

export async function fetchDefaultRelationshipManager() {
  return apiFetch("/admin/relationship-managers/default", { schema: defaultRmSchema });
}

export async function createRelationshipManager(input: {
  name: string;
  phone: string;
  city?: string;
  is_active?: boolean;
  set_as_default?: boolean;
}): Promise<RelationshipManager> {
  return apiFetch("/admin/relationship-managers", {
    method: "POST",
    body: JSON.stringify(input),
    schema: relationshipManagerSchema,
  });
}

export async function updateRelationshipManager(
  id: string,
  input: {
    name?: string;
    phone?: string;
    city?: string | null;
    is_active?: boolean;
    set_as_default?: boolean;
    change_reason?: string;
  },
): Promise<RelationshipManager> {
  return apiFetch(`/admin/relationship-managers/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
    schema: relationshipManagerSchema,
  });
}

export async function setDefaultRelationshipManager(input: {
  relationship_manager_id: string | null;
  change_reason?: string;
}) {
  return apiFetch("/admin/relationship-managers/default", {
    method: "PUT",
    body: JSON.stringify(input),
    schema: defaultRmSchema,
  });
}
