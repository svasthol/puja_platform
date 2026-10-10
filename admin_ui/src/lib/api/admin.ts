import { apiFetch } from "@/lib/api/client";
import {
  advanceAmountSchema,
  advanceUpdateSchema,
  bookingFeeSchema,
  bookingFeeUpdateSchema,
  tdsFacilitationSchema,
  tdsFacilitationUpdateSchema,
  credentialProvisionSchema,
  roleAssignSchema,
  userRolesSchema,
  type AdvanceAmount,
  type BookingFee,
  type TdsFacilitation,
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

export async function fetchBookingFee(): Promise<BookingFee> {
  return apiFetch("/admin/settings/booking-fee", {
    schema: bookingFeeSchema,
  });
}

export async function updateBookingFee(input: {
  amount: number;
  label?: string;
  change_reason?: string;
}): Promise<BookingFee> {
  const body = bookingFeeUpdateSchema.parse(input);
  return apiFetch("/admin/settings/booking-fee", {
    method: "PUT",
    body: JSON.stringify(body),
    schema: bookingFeeSchema,
  });
}

export async function fetchTdsFacilitation(): Promise<TdsFacilitation> {
  return apiFetch("/admin/settings/tds-facilitation", {
    schema: tdsFacilitationSchema,
  });
}

export async function updateTdsFacilitation(input: {
  no_pan_rate_pct: number;
  pan_entity_rate_pct: number;
  individual_fy_threshold_inr: number;
  fy_turnover_warn_inr: number;
  fy_turnover_block_inr: number;
  always_taxed_entity_types: string[];
  change_reason?: string;
}): Promise<TdsFacilitation> {
  const body = tdsFacilitationUpdateSchema.parse(input);
  return apiFetch("/admin/settings/tds-facilitation", {
    method: "PUT",
    body: JSON.stringify(body),
    schema: tdsFacilitationSchema,
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
