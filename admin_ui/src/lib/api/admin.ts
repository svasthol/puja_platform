import { apiFetch } from "@/lib/api/client";
import {
  advanceAmountSchema,
  advanceUpdateSchema,
  credentialProvisionSchema,
  roleAssignSchema,
  userRolesSchema,
  type AdvanceAmount,
  type CredentialProvision,
  type UserRoles,
} from "@/lib/schemas/admin";
import { adminLoginSchema, adminMeSchema, tokenPairSchema, type AdminLoginInput, type AdminMe, type TokenPair } from "@/lib/schemas/auth";

export async function adminLogin(payload: AdminLoginInput): Promise<TokenPair> {
  const body = adminLoginSchema.parse(payload);
  return apiFetch("/admin/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
    auth: false,
    schema: tokenPairSchema,
  });
}

export async function fetchAdminMe(): Promise<AdminMe> {
  return apiFetch("/admin/me", { schema: adminMeSchema });
}

export async function fetchAdvanceAmount(): Promise<AdvanceAmount> {
  return apiFetch("/admin/settings/advance-booking-amount", {
    schema: advanceAmountSchema,
  });
}

export async function updateAdvanceAmount(input: {
  amount: number;
  change_reason?: string;
}): Promise<AdvanceAmount> {
  const body = advanceUpdateSchema.parse(input);
  return apiFetch("/admin/settings/advance-booking-amount", {
    method: "PUT",
    body: JSON.stringify(body),
    schema: advanceAmountSchema,
  });
}

export async function fetchUserRoles(userId: string): Promise<UserRoles> {
  return apiFetch(`/admin/users/${userId}/roles`, { schema: userRolesSchema });
}

export async function assignUserRole(
  userId: string,
  input: { role: "admin" | "support"; change_reason?: string },
): Promise<UserRoles> {
  const body = roleAssignSchema.parse(input);
  return apiFetch(`/admin/users/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify(body),
    schema: userRolesSchema,
  });
}

export async function revokeUserRole(userId: string, role: string): Promise<UserRoles> {
  return apiFetch(`/admin/users/${userId}/roles/${role}`, {
    method: "DELETE",
    schema: userRolesSchema,
  });
}

export async function provisionCredential(userId: string): Promise<CredentialProvision> {
  return apiFetch(`/admin/users/${userId}/credential`, {
    method: "POST",
    schema: credentialProvisionSchema,
  });
}

export async function logout(): Promise<void> {
  const refresh = typeof window !== "undefined" ? sessionStorage.getItem("mg_admin_refresh") : null;
  if (refresh) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
        auth: false,
      });
    } catch {
      /* idempotent */
    }
  }
}
