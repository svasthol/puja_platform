import { canEditPartnerPricing } from "@/lib/auth/roles";
import type { AdminMe } from "@/lib/schemas/auth";

export function PartnerReadOnlyBanner({ me }: { me: AdminMe | undefined }) {
  if (canEditPartnerPricing(me)) return null;
  return (
    <p className="rounded-lg border border-amber-800/40 bg-amber-950/30 px-4 py-3 text-sm text-amber-100">
      <strong>Support</strong> role: read-only. Pricing writes require <strong>admin</strong>.
    </p>
  );
}
