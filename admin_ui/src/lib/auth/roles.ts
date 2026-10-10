import type { AdminMe } from "@/lib/schemas/auth";

export function hasAdminRole(me: AdminMe | undefined): boolean {
  return Boolean(me?.is_admin);
}

export function hasSupportRole(me: AdminMe | undefined): boolean {
  return Boolean(me?.is_support || me?.is_admin);
}

/** RBAC matrix (ADMIN.md) — admin-only writes for Sprint 4A surfaces. */
export function canManageRoles(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canProvisionCredentials(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditAdvanceAmount(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditTdsFacilitation(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditCatalog(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditPartnerPricing(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canApproveKyc(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditServiceAreas(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canEditRelationshipManagers(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canReassignBooking(me: AdminMe | undefined): boolean {
  return hasSupportRole(me);
}

export function canRefundOverride(me: AdminMe | undefined): boolean {
  return hasSupportRole(me);
}

export function canManagePromos(me: AdminMe | undefined): boolean {
  return hasAdminRole(me);
}

export function canDisputeBooking(me: AdminMe | undefined): boolean {
  return hasSupportRole(me);
}

export function roleLabel(me: AdminMe | undefined): string {
  if (!me?.roles.length) return "No role";
  return me.roles.join(", ");
}
