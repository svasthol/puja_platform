"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PartnerReadOnlyBanner } from "@/components/partners/read-only-banner";
import { Header } from "@/components/layout/header";
import { PageContent } from "@/components/layout/page-content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { fetchPujaris } from "@/lib/api/partners";
import { useAdminMe } from "@/lib/hooks/use-admin-me";

const STATUS_TONE = {
  verified: "success",
  pending: "warning",
  rejected: "warning",
} as const;

export default function PartnersPage() {
  const { data: me } = useAdminMe();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "pujaris", search, status],
    queryFn: () =>
      fetchPujaris({
        q: search || undefined,
        verification_status: status || undefined,
        limit: 50,
      }),
  });

  return (
    <>
      <Header
        title="Partners"
        description="Pujari directory, KYC review, and per-puja pricing."
      />
      <PageContent>
        <PartnerReadOnlyBanner me={me} />

        <div className="flex flex-wrap gap-3">
          <Link href="/console/partners/kyc">
            <Button type="button" variant="secondary">
              KYC review queue →
            </Button>
          </Link>
        </div>

        <Card>
          <CardTitle className="text-base">Search</CardTitle>
          <form
            className="mt-4 grid gap-4 sm:grid-cols-[1fr_160px_auto]"
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(q.trim());
            }}
          >
            <div>
              <Label htmlFor="partner-q">Phone or name</Label>
              <Input
                id="partner-q"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="+9198… or Rama"
                className="mt-1.5"
              />
            </div>
            <div>
              <Label htmlFor="partner-status">Verification</Label>
              <Select
                id="partner-status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                className="mt-1.5"
              >
                <option value="">All</option>
                <option value="verified">Verified</option>
                <option value="pending">Pending</option>
                <option value="rejected">Rejected</option>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button type="submit">Search</Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setQ("");
                  setSearch("");
                  setStatus("");
                }}
              >
                Clear
              </Button>
            </div>
          </form>
        </Card>

        <Card className="overflow-hidden !p-0">
          <div className="border-b border-surface-border px-5 py-4">
            <CardTitle className="text-base">Pujaris</CardTitle>
            <CardDescription className="!mt-0.5">
              {data?.pujaris.length ?? 0} shown · click to edit pricing
            </CardDescription>
          </div>
          {isLoading && <p className="p-5 text-sm text-ink-muted">Loading…</p>}
          <ul className="divide-y divide-surface-border">
            {(data?.pujaris ?? []).length === 0 && !isLoading && (
              <li className="px-5 py-10 text-center text-sm text-ink-muted">No pujaris found.</li>
            )}
            {(data?.pujaris ?? []).map((pj) => (
              <li key={pj.id}>
                <Link
                  href={`/console/partners/${pj.id}`}
                  className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-surface"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-ink">{pj.full_name}</p>
                    <p className="text-xs text-ink-faint">
                      {pj.phone}
                      {pj.years_experience != null ? ` · ${pj.years_experience} yrs` : ""}
                      {pj.pricing_count > 0 ? ` · ${pj.pricing_count} priced` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <Badge tone={STATUS_TONE[pj.verification_status]}>
                      {pj.verification_status}
                    </Badge>
                    <span className="text-sm text-brand-glow">Pricing →</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </PageContent>
    </>
  );
}
