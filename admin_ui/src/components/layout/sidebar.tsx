"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { useAdminMe } from "@/lib/hooks/use-admin-me";
import { cn } from "@/lib/utils/cn";

type NavItem = {
  href: string;
  label: string;
  section?: string;
  adminOnly?: boolean;
  comingSoon?: boolean;
};

const NAV: NavItem[] = [
  { href: "/console", label: "Overview", section: "Main" },
  { href: "/console/settings/advance", label: "Booking fee", section: "Settings" },
  { href: "/console/tds", label: "TDS hub", section: "TDS & compliance" },
  { href: "/console/settings/tds", label: "TDS policy slabs", section: "TDS & compliance" },
  { href: "/console/tds/backlog", label: "TDS accrual backlog", section: "TDS & compliance" },
  { href: "/console/tds/reconcile", label: "TDS FY reconcile", section: "TDS & compliance" },
  { href: "/console/settings/areas", label: "Service areas", section: "Settings" },
  { href: "/console/settings/relationship-managers", label: "Relationship managers", section: "Settings" },
  { href: "/console/team/roles", label: "Roles", section: "Team", adminOnly: true },
  { href: "/console/team/credentials", label: "TOTP credentials", section: "Team", adminOnly: true },
  { href: "/console/catalog", label: "Catalogue", section: "Phase 4B" },
  { href: "/console/partners", label: "Partners", section: "Phase 4B" },
  { href: "/console/partners/kyc", label: "KYC review", section: "Phase 4B" },
  { href: "/console/bookings", label: "Bookings search", section: "Phase 4C" },
  { href: "/console/bookings/ops", label: "Bookings ops", section: "Phase 4C" },
  { href: "/console/partners/fy-earnings", label: "Partner FY earnings", section: "TDS & compliance" },
  { href: "/console/refunds", label: "Failed refunds", section: "Phase 4C" },
  { href: "/console/promos", label: "Promos", section: "Phase 4C" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: me } = useAdminMe();

  let lastSection = "";

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-surface-border bg-surface-raised/60">
      <div className="border-b border-surface-border px-5 py-5">
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand/15 text-lg">🪔</span>
          <div>
            <p className="font-semibold text-ink">Mana Guruji</p>
            <p className="text-xs text-ink-faint">Ops Console</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {NAV.map((item) => {
          const showSection = item.section && item.section !== lastSection;
          if (item.section) lastSection = item.section;

          if (item.adminOnly && !me?.is_admin) return null;

          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const disabled = item.comingSoon;

          return (
            <div key={item.href}>
              {showSection && (
                <p className="mb-2 mt-4 px-2 text-[10px] font-semibold uppercase tracking-widest text-ink-faint first:mt-0">
                  {item.section}
                </p>
              )}
              {disabled ? (
                <div
                  className="flex items-center justify-between rounded-lg px-3 py-2 text-sm text-ink-faint opacity-60"
                  title="Coming in Sprint 4B/4C"
                >
                  {item.label}
                  <Badge tone="warning">Soon</Badge>
                </div>
              ) : (
                <Link
                  href={item.href}
                  className={cn(
                    "mb-0.5 block rounded-lg px-3 py-2 text-sm transition",
                    active
                      ? "bg-brand/15 font-medium text-brand-glow"
                      : "text-ink-muted hover:bg-surface-border/40 hover:text-ink",
                  )}
                >
                  {item.label}
                </Link>
              )}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-surface-border p-4 text-xs text-ink-faint">
        <p className="truncate font-mono">{me?.phone ?? "—"}</p>
        <p className="mt-1">{me?.roles.join(" · ") ?? "—"}</p>
      </div>
    </aside>
  );
}
