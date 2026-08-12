"use client";

import Link from "next/link";

import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

export default function ConsoleHomePage() {
  const { data: me } = useAdminMe();

  return (
    <>
      <Header
        title="Overview"
        description="Mana Guruji ops console — catalogue, partners, and booking operations."
      />
      <PageContent className="grid gap-6 md:grid-cols-2 xl:grid-cols-3 !space-y-0">
        <Card>
          <CardTitle>Session</CardTitle>
          <CardDescription>Signed in via TOTP (P-ADMIN-AUTH)</CardDescription>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">Phone</dt>
              <dd className="font-mono text-ink">{me?.phone}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">User ID</dt>
              <dd className="truncate font-mono text-xs text-ink">{me?.user_id}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-ink-muted">Roles</dt>
              <dd className="flex gap-1">
                {me?.roles.map((r) => (
                  <Badge key={r} tone={r === "admin" ? "success" : "default"}>
                    {r}
                  </Badge>
                ))}
              </dd>
            </div>
          </dl>
        </Card>

        <Card>
          <CardTitle>Available now</CardTitle>
          <CardDescription>Backed by live Sprint 4-0 / 4B APIs</CardDescription>
          <ul className="mt-4 space-y-2 text-sm text-ink-muted">
            <li>
              <Link href="/console/partners" className="text-brand-glow hover:underline">
                Partners & pricing
              </Link>{" "}
              — directory + pujari_pricing matrix
            </li>
            <li>
              <Link href="/console/catalog" className="text-brand-glow hover:underline">
                Catalogue builder
              </Link>{" "}
              — categories, pujas, content, addons, media
            </li>
            <li>
              <Link href="/console/settings/advance" className="text-brand-glow hover:underline">
                Advance booking amount
              </Link>{" "}
              — platform setting (admin write)
            </li>
            <li>
              <Link href="/console/team/roles" className="text-brand-glow hover:underline">
                Team roles
              </Link>{" "}
              — assign admin / support
            </li>
            <li>
              <Link href="/console/team/credentials" className="text-brand-glow hover:underline">
                TOTP credentials
              </Link>{" "}
              — provision authenticator for staff
            </li>
          </ul>
        </Card>

        <Card>
          <CardTitle>Booking operations</CardTitle>
          <CardDescription>Sprint 4C — search, reassign, refunds, disputes</CardDescription>
          <ul className="mt-4 space-y-2 text-sm text-ink-muted">
            <li>
              <Link href="/console/bookings" className="text-brand-glow hover:underline">
                Bookings
              </Link>{" "}
              — search + 360° detail (PII reads audited)
            </li>
            <li>
              <Link href="/console/refunds" className="text-brand-glow hover:underline">
                Failed refunds
              </Link>{" "}
              — permanent gateway failures queue
            </li>
            <li>
              <Link href="/console/promos" className="text-brand-glow hover:underline">
                Promos
              </Link>{" "}
              — create and manage promo codes
            </li>
            <li>
              <Link href="/console/partners/kyc" className="text-brand-glow hover:underline">
                KYC review
              </Link>{" "}
              — approve partner documents
            </li>
          </ul>
        </Card>
      </PageContent>
    </>
  );
}
